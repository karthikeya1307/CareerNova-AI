
import hashlib
import io
import json
import logging
import re
import zipfile
import uuid

from pathlib import Path
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status
)
from fastapi.responses import FileResponse

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db

from backend.models import (
    User,
    Resume,
    Internship,
    ResumeExtraction
)

from backend.utils.dependencies import get_current_user

from backend.schemas.resume_schema import (
    NormalizedSkillItem,
    ResumeParsedData,
    ResumeUploadResponse,
    ResumeDetailResponse,
    ResumeListItem,
    ResumeVersionUpdate,
    ResumeSkillsResponse,
    ResumeCorrection
)

from backend.services.resume_insights import analyze as analyze_resume
from backend.services.resume_parser import parse_resume_file
from backend.services.resume_readiness import score_resume
from backend.services.resume_skills import (
    get_resume_skill_rows,
    sync_resume_skills
)
from backend.services.skill_gap import detect_acquired_skills


logger = logging.getLogger(__name__)

# Server-generated stored filenames: 32 hex chars + extension.
STORED_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(pdf|docx|odt)$")

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
    "odt": "application/vnd.oasis.opendocument.text",
}


router = APIRouter(
    prefix="/resumes",
    tags=["Resume Parsing"]
)

# Maximum allowed resume size: 5 MB.
MAX_FILE_SIZE = 5 * 1024 * 1024

# Project root directory.
BASE_DIR = Path(__file__).resolve().parents[2]

# Resume storage directory.
UPLOAD_DIR = BASE_DIR / "uploads" / "resumes"


# ============================================================
# FILE VALIDATION
# ============================================================

def validate_resume_file(
    filename: str,
    file_bytes: bytes
) -> str:

    extension = filename.lower().rsplit(".", 1)[-1]

    if extension not in {"pdf", "docx", "odt"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF, DOCX and ODT files are supported."
        )

    if extension == "odt":
        # OpenDocument Text: ZIP with the ODT mimetype and content.xml (same size limits as DOCX).
        from backend.services.resume_parsers.common import ResumeFileError, detect_format
        try:
            detect_format(file_bytes, filename)
        except ResumeFileError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
        return extension

    if extension == "pdf":

        if not file_bytes.lstrip().startswith(b"%PDF-"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF file content."
            )

    elif extension == "docx":

        try:
            with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
                names = set(archive.namelist())

                if not {
                    "[Content_Types].xml",
                    "word/document.xml"
                }.issubset(names):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid DOCX file content."
                    )

                # Limit uncompressed content to reduce ZIP-bomb risk.
                total_uncompressed_size = sum(
                    item.file_size for item in archive.infolist()
                )

                if (
                    len(names) > 1000
                    or total_uncompressed_size > 20 * 1024 * 1024
                ):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="DOCX file contains excessive data."
                    )

        except zipfile.BadZipFile:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DOCX file content."
            )

    return extension


# ============================================================
# HELPERS
# ============================================================

def get_owned_resume(
    db: Session,
    resume_id: int,
    user: User
) -> Resume:
    """Return the user's resume or 404 (also for other users' resumes)."""

    resume = db.scalar(
        select(Resume).where(
            Resume.resume_id == resume_id,
            Resume.user_id == user.user_id
        )
    )

    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found"
        )

    return resume


def resolve_stored_path(resume: Resume) -> Path | None:
    """Rebuild the file location from trusted parts only.

    The path is always UPLOAD_DIR / <owner id> / <server filename>;
    the stored DB path is used only for its filename, which must match
    the server-generated pattern. Returns None if anything looks wrong.
    """

    stored_name = Path(resume.file_path or "").name

    if not STORED_FILENAME_PATTERN.fullmatch(stored_name):
        return None

    base_dir = UPLOAD_DIR.resolve()
    candidate = (base_dir / str(resume.user_id) / stored_name).resolve()

    if not candidate.is_relative_to(base_dir):
        return None

    return candidate


def latest_completed_extraction(
    db: Session,
    resume_id: int
) -> ResumeExtraction | None:
    """Newest successful extraction; failed re-parses are skipped."""

    return db.scalar(
        select(ResumeExtraction)
        .where(
            ResumeExtraction.resume_id == resume_id,
            ResumeExtraction.status == "completed"
        )
        .order_by(
            ResumeExtraction.created_at.desc(),
            ResumeExtraction.extraction_id.desc()
        )
        .limit(1)
    )


def skill_items(db: Session, resume_id: int) -> list[NormalizedSkillItem]:
    items = []

    for link, skill in get_resume_skill_rows(db, resume_id):
        source = None
        if link.evidence and ":" in link.evidence:
            source = link.evidence.split(":", 1)[0]

        items.append(NormalizedSkillItem(
            skill_id=skill.skill_id,
            name=skill.name,
            category=skill.category,
            source=source
        ))

    return items


def build_detail_response(
    db: Session,
    resume: Resume,
    extraction: ResumeExtraction
) -> dict:
    return {
        "resume_id": resume.resume_id,
        "filename": resume.filename,
        "file_type": resume.file_type,
        "status": resume.status,
        "uploaded_at": resume.uploaded_at,
        "extracted_data": ResumeParsedData.model_validate(
            extraction.extracted_data
        ),
        "normalized_skills": skill_items(db, resume.resume_id),
        "parser_type": extraction.parser_type,
        "corrected": extraction.parser_type == USER_CORRECTED,
    }


USER_CORRECTED = "user_corrected"
MAX_DUPLICATE_SCAN = 50


def content_fingerprint(data: dict) -> str:
    """Hash of the extracted content (case/whitespace-insensitive), to spot re-exported copies."""
    def norm(value):
        if isinstance(value, str):
            return " ".join(value.lower().split())
        if isinstance(value, list):
            return [norm(v) for v in value]
        if isinstance(value, dict):
            return {k: norm(v) for k, v in sorted(value.items())}
        return value
    return hashlib.sha256(json.dumps(norm(data), sort_keys=True).encode("utf-8")).hexdigest()


def find_duplicates(db: Session, user_id: int, file_bytes: bytes, data: dict) -> tuple[str | None, list[int]]:
    """Earlier resumes of this user with the identical file, or else the same extracted content.

    Informational only: the upload still succeeds (existing clients are unaffected)."""
    resumes = list(db.scalars(select(Resume).where(Resume.user_id == user_id)
                              .order_by(Resume.resume_id.desc()).limit(MAX_DUPLICATE_SCAN)))
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    same_file = []
    for resume in resumes:
        path = resolve_stored_path(resume)
        try:
            if path is not None and path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == file_hash:
                same_file.append(resume.resume_id)
        except OSError:
            continue
    if same_file:
        return "identical_file", sorted(same_file)
    fingerprint = content_fingerprint(data)
    same_content = []
    for resume in resumes:
        extraction = latest_completed_extraction(db, resume.resume_id)
        if extraction is not None and content_fingerprint(extraction.extracted_data or {}) == fingerprint:
            same_content.append(resume.resume_id)
    return ("same_content", sorted(same_content)) if same_content else (None, [])


# ============================================================
# API 1: UPLOAD AND PARSE RESUME
# POST /resumes/upload
# ============================================================

@router.post(
    "/upload",
    response_model=ResumeUploadResponse,
    status_code=status.HTTP_201_CREATED
)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Check original filename.
    original_filename = (file.filename or "").replace("\\", "/").split("/")[-1]

    if not original_filename or "." not in original_filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A valid filename is required."
        )

    # Read at most 5 MB plus one byte.
    file_bytes = await file.read(MAX_FILE_SIZE + 1)

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Resume file must not exceed 5 MB."
        )

    # Validate extension and actual file content.
    file_type = validate_resume_file(
        original_filename,
        file_bytes
    )

    # Parse resume content.
    try:
        parser_result = parse_resume_file(
            file_bytes,
            original_filename
        )

        parsed_data = ResumeParsedData.model_validate(
            parser_result["extracted_data"]
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc)
        )

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Unable to parse the uploaded resume."
        )

    # Earlier uploads of the same file/content (reported, not blocked).
    duplicate_kind, duplicate_of = find_duplicates(
        db, current_user.user_id, file_bytes, parsed_data.model_dump(mode="json")
    )

    # Create a private storage folder for this user.
    user_upload_dir = UPLOAD_DIR / str(current_user.user_id)

    # Generate a server-controlled filename.
    stored_filename = f"{uuid.uuid4().hex}.{file_type}"

    storage_path = user_upload_dir / stored_filename

    # Store relative path in PostgreSQL.
    relative_path = (
        Path("uploads")
        / "resumes"
        / str(current_user.user_id)
        / stored_filename
    ).as_posix()

    file_saved = False

    try:
        user_upload_dir.mkdir(
            parents=True,
            exist_ok=True
        )

        storage_path.write_bytes(file_bytes)
        file_saved = True

        # Create resume metadata.
        new_resume = Resume(
            user_id=current_user.user_id,
            filename=original_filename[:255],
            file_path=relative_path,
            file_type=file_type,
            status="completed"
        )

        db.add(new_resume)
        db.flush()

        # Save the extracted JSON.
        extraction = ResumeExtraction(
            resume_id=new_resume.resume_id,
            parser_type=parser_result["parser_type"],
            extracted_data=parsed_data.model_dump(mode="json"),
            status="completed"
        )

        db.add(extraction)

        # Normalize and link skills in the same transaction.
        skill_pairs = sync_resume_skills(
            db,
            new_resume.resume_id,
            parsed_data.model_dump(mode="json")
        )

        # Save all records in one transaction.
        db.commit()
        db.refresh(new_resume)

    except Exception:
        db.rollback()

        if file_saved:
            try:
                storage_path.unlink(missing_ok=True)
            except OSError:
                pass

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the resume. Please try again."
        )

    return ResumeUploadResponse(
        resume_id=new_resume.resume_id,
        filename=new_resume.filename,
        file_type=new_resume.file_type,
        status=new_resume.status,
        uploaded_at=new_resume.uploaded_at,
        extracted_data=parsed_data,
        normalized_skills=[
            NormalizedSkillItem(
                skill_id=skill.skill_id,
                name=skill.name,
                category=skill.category,
                source=item.source
            )
            for skill, item in skill_pairs
        ],
        duplicate_of=duplicate_of,
        duplicate_kind=duplicate_kind,
    )

# ============================================================
# API 2: GET ALL USER RESUMES
# GET /resumes/
# ============================================================

@router.get(
    "/",
    response_model=list[ResumeListItem],
    status_code=status.HTTP_200_OK
)
def get_user_resumes(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    resumes = db.scalars(
        select(Resume)
        .where(Resume.user_id == current_user.user_id)
        .order_by(Resume.uploaded_at.desc())
    ).all()
    # Version numbers follow upload order (V1 = first upload); they never change when newer versions arrive.
    order = sorted(resumes, key=lambda r: (r.uploaded_at, r.resume_id))
    version = {r.resume_id: i for i, r in enumerate(order, start=1)}

    return [
        {
            "resume_id": resume.resume_id,
            "filename": resume.filename,
            "file_type": resume.file_type,
            "status": resume.status,
            "uploaded_at": resume.uploaded_at,
            "version": version[resume.resume_id],
            "label": resume.label,
            "is_preferred": bool(resume.is_preferred),
        }
        for resume in resumes
    ]


# ============================================================
# RESUME VERSIONS: compare two versions, rename, mark preferred
# GET   /resumes/compare?a=&b=&role=&internship_id=
# PATCH /resumes/{resume_id}  {label?, is_preferred?}
# ============================================================

@router.get("/compare")
def compare_resumes(
    a: int = Query(..., ge=1, description="Older / first version"),
    b: int = Query(..., ge=1, description="Newer / second version"),
    role: str | None = Query(default=None, max_length=60, pattern="^[a-z0-9-]+$"),
    internship_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare two of MY resume versions with the same engines (readiness, role fit, ATS report)."""
    from backend.services import career_tracks, resume_compare

    if a == b:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Choose two different versions.")
    first, second = get_owned_resume(db, a, current_user), get_owned_resume(db, b, current_user)
    track = None
    if role:
        track = career_tracks.get_track(role)
        if track is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    internship = None
    if internship_id is not None:
        internship = db.get(Internship, internship_id)
        if internship is None or not internship.is_active:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")
    try:
        return resume_compare.compare(db, first, second, track, internship)
    except resume_compare.CompareError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from None


@router.patch("/{resume_id}", response_model=ResumeListItem)
def update_resume_version(
    resume_id: int,
    body: ResumeVersionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)
    provided = body.model_fields_set
    if not provided:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Provide label and/or is_preferred.")
    if "label" in provided:
        resume.label = body.label
    if "is_preferred" in provided and body.is_preferred is not None:
        if body.is_preferred:
            if resume.status != "completed":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                    detail="Only a successfully parsed resume can be your preferred version.")
            for other in db.scalars(select(Resume).where(Resume.user_id == current_user.user_id,
                                                         Resume.is_preferred.is_(True),
                                                         Resume.resume_id != resume.resume_id)):
                other.is_preferred = False
            db.flush()
        resume.is_preferred = body.is_preferred
    db.commit()
    db.refresh(resume)
    order = db.scalars(select(Resume.resume_id).where(Resume.user_id == current_user.user_id)
                       .order_by(Resume.uploaded_at, Resume.resume_id)).all()
    return {"resume_id": resume.resume_id, "filename": resume.filename, "file_type": resume.file_type,
            "status": resume.status, "uploaded_at": resume.uploaded_at, "version": list(order).index(resume.resume_id) + 1,
            "label": resume.label, "is_preferred": bool(resume.is_preferred)}


# ============================================================
# API 3: GET ONE RESUME WITH EXTRACTED DATA
# GET /resumes/{resume_id}
# ============================================================

@router.get(
    "/{resume_id}",
    response_model=ResumeDetailResponse,
    status_code=status.HTTP_200_OK
)
def get_resume_details(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # Find resume belonging to the logged-in user only.
    resume = get_owned_resume(db, resume_id, current_user)

    # Retrieve the most recent successful extraction.
    extraction = latest_completed_extraction(db, resume.resume_id)

    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed resume information not found"
        )

    return build_detail_response(db, resume, extraction)


# ============================================================
# API 4: GET NORMALIZED SKILLS OF A RESUME
# GET /resumes/{resume_id}/skills
# ============================================================

@router.get(
    "/{resume_id}/skills",
    response_model=ResumeSkillsResponse,
    status_code=status.HTTP_200_OK
)
def get_resume_skills(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = get_owned_resume(db, resume_id, current_user)

    return {
        "resume_id": resume.resume_id,
        "skills": skill_items(db, resume.resume_id)
    }


# ============================================================
# API 5: RE-PARSE A STORED RESUME
# POST /resumes/{resume_id}/reparse
# A new extraction row is added; earlier extractions are kept.
# ============================================================

@router.post(
    "/{resume_id}/reparse",
    response_model=ResumeDetailResponse,
    status_code=status.HTTP_200_OK
)
def reparse_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = get_owned_resume(db, resume_id, current_user)

    stored_path = resolve_stored_path(resume)

    if stored_path is None or not stored_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored resume file not found"
        )

    file_bytes = stored_path.read_bytes()

    try:
        parser_result = parse_resume_file(
            file_bytes,
            f"resume.{resume.file_type}"
        )
        parsed_data = ResumeParsedData.model_validate(
            parser_result["extracted_data"]
        )

    except Exception as exc:
        # Record the failed attempt; earlier data stays in use.
        error_message = (
            str(exc) if isinstance(exc, ValueError)
            else "Unable to parse the stored resume."
        )

        db.add(ResumeExtraction(
            resume_id=resume.resume_id,
            parser_type=resume.file_type,
            extracted_data={},
            status="failed",
            error_message=error_message[:1000]
        ))
        db.commit()

        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=error_message
        )

    try:
        extraction = ResumeExtraction(
            resume_id=resume.resume_id,
            parser_type=parser_result["parser_type"],
            extracted_data=parsed_data.model_dump(mode="json"),
            status="completed"
        )
        db.add(extraction)

        sync_resume_skills(
            db,
            resume.resume_id,
            parsed_data.model_dump(mode="json")
        )

        # Phase 4: skills that now appear on the resume complete any
        # open skill-gap recommendations for it (same transaction).
        detect_acquired_skills(db, resume.resume_id)

        resume.status = "completed"
        db.commit()
        db.refresh(extraction)

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the re-parsed resume."
        )

    return build_detail_response(db, resume, extraction)


# ============================================================
# API 6: DOWNLOAD ORIGINAL RESUME FILE
# GET /resumes/{resume_id}/download
# ============================================================

@router.get(
    "/{resume_id}/download",
    response_class=FileResponse,
    status_code=status.HTTP_200_OK
)
def download_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = get_owned_resume(db, resume_id, current_user)

    stored_path = resolve_stored_path(resume)

    if stored_path is None or not stored_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Stored resume file not found"
        )

    return FileResponse(
        path=stored_path,
        media_type=MEDIA_TYPES.get(
            resume.file_type, "application/octet-stream"
        ),
        filename=resume.filename,
        headers={"X-Content-Type-Options": "nosniff"}
    )


# ============================================================
# API 7: DELETE A RESUME (PERMANENT)
# DELETE /resumes/{resume_id}
# Removes the resume, its extractions and its resume_skills links,
# then the stored file. Shared skills rows are never deleted.
# Clients must ask the user for explicit confirmation first.
# ============================================================

@router.delete(
    "/{resume_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response
)
def delete_resume(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = get_owned_resume(db, resume_id, current_user)

    stored_path = resolve_stored_path(resume)

    try:
        db.delete(resume)
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to delete the resume."
        )

    # Remove the file only after the database change succeeded.
    if stored_path is not None:
        try:
            stored_path.unlink(missing_ok=True)
        except OSError:
            logger.warning(
                "Resume %s deleted but its file could not be removed",
                resume_id
            )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================
# PARSER COMPARISON (read-only: nothing is stored)
# POST /resumes/parse-preview?parser=regex|llm|hybrid   (upload a PDF/DOCX/ODT)
# GET  /resumes/{resume_id}/parse-preview?parser=...    (one of MY stored resumes)
# ============================================================

def _run_parser(parser: str, file_bytes: bytes, filename: str, consent: bool) -> dict:
    from backend.services import resume_parsers
    from backend.services.resume_parsers import llm_parser

    if parser in ("llm", "hybrid") and not consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="AI parsing sends the resume text (without name, email, phone and links) to the configured AI "
                   "provider. Add consent=true to allow it, or use parser=regex."
        )
    try:
        return resume_parsers.run(parser, file_bytes, filename).as_dict()
    except resume_parsers.ResumeFileError as exc:
        unsupported = str(exc).startswith("Unsupported")
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE if unsupported else status.HTTP_400_BAD_REQUEST,
            detail=str(exc)
        ) from None
    except llm_parser.LLMParserUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from None
    except llm_parser.LLMParserError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from None


@router.post("/parse-preview")
async def parse_preview_upload(
    parser: Literal["regex", "llm", "hybrid"] = Query(default="regex"),
    consent: bool = Query(default=False),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    """Run one of the three parsers on an uploaded file and return the common JSON schema. Nothing is saved."""
    original = (file.filename or "").replace("\\", "/").split("/")[-1]
    file_bytes = await file.read(MAX_FILE_SIZE + 1)
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File size must not exceed 5 MB.")
    return _run_parser(parser, file_bytes, original, consent)


@router.get("/{resume_id}/parse-preview")
def parse_preview_stored(
    resume_id: int,
    parser: Literal["regex", "llm", "hybrid"] = Query(default="regex"),
    consent: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run a parser on one of my stored resume files. The stored extraction (and any corrections) is not changed."""
    resume = get_owned_resume(db, resume_id, current_user)
    path = resolve_stored_path(resume)
    if path is None or not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="The original file is not available.")
    return _run_parser(parser, path.read_bytes(), f"resume.{resume.file_type}", consent)


# ============================================================
# P2: ANALYSIS, READINESS AND CORRECTIONS
# GET /resumes/{resume_id}/analysis     parsing confidence, missing fields, dates
# GET /resumes/{resume_id}/readiness    general resume readiness score (0-100)
# PUT /resumes/{resume_id}/extracted-data   the student's corrections
# ============================================================

def require_extraction(db: Session, resume: Resume) -> ResumeExtraction:
    extraction = latest_completed_extraction(db, resume.resume_id)
    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This resume has no successful extraction yet. Re-parse it first."
        )
    return extraction


@router.get("/{resume_id}/analysis")
def get_resume_analysis(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    resume = get_owned_resume(db, resume_id, current_user)
    extraction = require_extraction(db, resume)
    return {
        "resume_id": resume.resume_id,
        "parser_type": extraction.parser_type,
        "corrected": extraction.parser_type == USER_CORRECTED,
        **analyze_resume(extraction.extracted_data or {}),
    }


@router.get("/{resume_id}/readiness")
def get_resume_readiness(
    resume_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """General resume readiness (not job-specific). Recalculated from the latest data on every call.

    Also says which version was scored and which of the student's other versions have identical extracted
    content - those always get the same score, which explains a score that "doesn't change" after
    uploading the same resume again. Profile details are not an input."""
    resume = get_owned_resume(db, resume_id, current_user)
    extraction = require_extraction(db, resume)
    data = extraction.extracted_data or {}
    mine = list(db.scalars(select(Resume).where(Resume.user_id == current_user.user_id)))
    order = sorted(mine, key=lambda r: (r.uploaded_at, r.resume_id))
    version = {r.resume_id: i for i, r in enumerate(order, start=1)}
    fingerprint = content_fingerprint(data)
    same_content = []
    for other in order:
        if other.resume_id == resume.resume_id:
            continue
        other_extraction = latest_completed_extraction(db, other.resume_id)
        if other_extraction is not None and content_fingerprint(other_extraction.extracted_data or {}) == fingerprint:
            same_content.append({"resume_id": other.resume_id, "version": version[other.resume_id]})
    return {
        "resume_id": resume.resume_id,
        "version": version[resume.resume_id],
        "filename": resume.filename,
        "version_label": resume.label,   # the student's name for the version ("label" is the score's label)
        "is_preferred": bool(resume.is_preferred),
        "corrected": extraction.parser_type == USER_CORRECTED,
        "scored_at": extraction.created_at,
        "basis": "resume_content",       # only the extracted resume content; profile details are not used
        "same_content_as": same_content,
        **score_resume(data),
    }


@router.put(
    "/{resume_id}/extracted-data",
    response_model=ResumeDetailResponse
)
def correct_extracted_data(
    resume_id: int,
    correction: ResumeCorrection,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Save the student's corrected data as a new extraction (the parser's version is kept).

    Matching, documents, skill gaps and the assistant all read the newest extraction, so the
    correction applies everywhere. A later re-parse replaces it with the parser's output again.
    """
    resume = get_owned_resume(db, resume_id, current_user)
    data = ResumeParsedData.model_validate(correction.model_dump()).model_dump(mode="json")
    try:
        extraction = ResumeExtraction(
            resume_id=resume.resume_id,
            parser_type=USER_CORRECTED,
            extracted_data=data,
            status="completed"
        )
        db.add(extraction)
        sync_resume_skills(db, resume.resume_id, data)
        detect_acquired_skills(db, resume.resume_id)
        resume.status = "completed"
        db.commit()
        db.refresh(extraction)
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to save the corrections."
        )
    return build_detail_response(db, resume, extraction)
