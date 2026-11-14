
import io
import zipfile
import uuid

from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status
)

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
    ResumeParsedData,
    ResumeUploadResponse,
    ResumeDetailResponse,
    ResumeListItem
)

from backend.services.resume_parser import parse_resume_file


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

        # Save both records in one transaction.
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
        extracted_data=parsed_data
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
    resume = db.scalar(
        select(Resume).where(
            Resume.resume_id == resume_id,
            Resume.user_id == current_user.user_id
        )
    )

    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found"
        )

    # Retrieve the most recent extraction.
    extraction = db.scalar(
        select(ResumeExtraction)
        .where(ResumeExtraction.resume_id == resume.resume_id)
        .order_by(ResumeExtraction.created_at.desc())
        .limit(1)
    )

    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Parsed resume information not found"
        )

    parsed_data = ResumeParsedData.model_validate(
        extraction.extracted_data
    )

    return {
        "resume_id": resume.resume_id,
        "filename": resume.filename,
        "file_type": resume.file_type,
        "status": resume.status,
        "uploaded_at": resume.uploaded_at,
        "extracted_data": parsed_data
    }
