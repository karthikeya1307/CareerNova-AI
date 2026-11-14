
import io
import logging
import re
import zipfile
import uuid

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
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
    ResumeExtraction
)

from backend.utils.dependencies import get_current_user

from backend.schemas.resume_schema import (
    NormalizedSkillItem,
    ResumeParsedData,
    ResumeUploadResponse,
    ResumeDetailResponse,
    ResumeListItem,
    ResumeSkillsResponse
)

from backend.services.resume_parser import parse_resume_file
from backend.services.resume_skills import (
    get_resume_skill_rows,
    sync_resume_skills
)


logger = logging.getLogger(__name__)

# Server-generated stored filenames: 32 hex chars + extension.
STORED_FILENAME_PATTERN = re.compile(r"^[0-9a-f]{32}\.(pdf|docx)$")

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
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

    if extension not in {"pdf", "docx"}:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PDF and DOCX files are supported."
        )

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
        "normalized_skills": skill_items(db, resume.resume_id)
    }


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
        ]
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

    return [
        {
            "resume_id": resume.resume_id,
            "filename": resume.filename,
            "file_type": resume.file_type,
            "status": resume.status,
            "uploaded_at": resume.uploaded_at
        }
        for resume in resumes
    ]


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
