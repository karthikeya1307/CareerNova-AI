
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import (
    GeneratedDocument,
    GeneratedDocumentVersion,
    Internship,
    InternshipSkill,
    Resume,
    User,
)
from backend.schemas.document_schema import (
    CreateCoverLetterRequest,
    CreateResumeRequest,
    DocumentListItem,
    DocumentResponse,
    LLMStatusResponse,
    UpdateDocumentRequest,
    VersionItem,
)
from backend.services.ats import ats_report
from backend.services.cover_letter import (
    CoverLetterOptions,
    InvalidEmphasisError,
    generate_cover_letter,
    learning_skills_for,
)
from backend.services.document_renderer import download_filename, render_docx, render_text
from backend.services.documents_service import add_version, check_edited_content, warning_count
from backend.services.fact_base import NoExtractionError, build_fact_base
from backend.services.llm import get_llm_provider, llm_status
from backend.services.matching_agent import is_eligible
from backend.services.resume_customizer import ResumeOptions, customize_resume
from backend.utils.dependencies import get_current_user


router = APIRouter(
    prefix="/documents",
    tags=["Resume and Cover Letter Customization"]
)

DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


# ============================================================
# HELPERS
# ============================================================

def get_owned_resume(db: Session, resume_id: int, user: User) -> Resume:
    resume = db.scalar(select(Resume).where(Resume.resume_id == resume_id, Resume.user_id == user.user_id))
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


def get_available_internship(db: Session, internship_id: int) -> Internship:
    internship = db.scalar(
        select(Internship)
        .where(Internship.internship_id == internship_id)
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
    )
    if internship is None or not is_eligible(internship):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")
    return internship


def get_owned_document(db: Session, document_id: int, user: User) -> GeneratedDocument:
    document = db.scalar(
        select(GeneratedDocument)
        .where(GeneratedDocument.document_id == document_id, GeneratedDocument.user_id == user.user_id)
        .options(selectinload(GeneratedDocument.versions), selectinload(GeneratedDocument.internship))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


def facts_or_422(db: Session, resume: Resume):
    try:
        return build_fact_base(db, resume)
    except NoExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


def llm_provider_for(request) -> object | None:
    if not request.use_llm:
        return None
    if not request.llm_consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="AI-assisted writing requires llm_consent=true after showing the privacy disclosure "
                   "from GET /documents/llm-status.",
        )
    provider = get_llm_provider()
    if provider is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI-assisted writing is not configured on this server.",
        )
    return provider


def internship_ref(internship: Internship | None) -> dict | None:
    if internship is None:
        return None
    return {"internship_id": internship.internship_id, "title": internship.title,
            "company": internship.company, "is_active": internship.is_active}


def to_response(document: GeneratedDocument) -> DocumentResponse:
    return DocumentResponse(
        document_id=document.document_id,
        document_type=document.document_type,
        title=document.title,
        resume_id=document.resume_id,
        internship=internship_ref(document.internship),
        generation_method=document.generation_method,
        llm_provider=document.llm_provider,
        llm_model=document.llm_model,
        current_version=document.current_version,
        content=document.content,
        content_json=document.content_json,
        fact_check=document.fact_check,
        ats_report=document.ats_report,
        options=document.options,
        created_at=document.created_at,
        updated_at=document.updated_at,
    )


def save_new_document(db, user, resume, internship, kind, title, content, log, provider, options, ats):
    document = GeneratedDocument(
        user_id=user.user_id, resume_id=resume.resume_id, internship_id=internship.internship_id,
        document_type=kind, title=title, content="",
        generation_method="llm" if log.llm_used else "deterministic",
        llm_provider=provider.name if (provider and log.llm_used) else None,
        llm_model=provider.model if (provider and log.llm_used) else None,
        ats_report=ats, options=options,
    )
    db.add(document)
    add_version(db, document, content, "generated", log.as_dict())
    db.commit()
    return get_owned_document(db, document.document_id, user)


# ============================================================
# LLM STATUS AND PRIVACY DISCLOSURE
# GET /documents/llm-status
# ============================================================

@router.get("/llm-status", response_model=LLMStatusResponse)
def get_llm_status(current_user: User = Depends(get_current_user)):
    return llm_status()


# ============================================================
# ATS REPORT (read-only)
# GET /documents/resumes/{resume_id}/internships/{internship_id}/ats-report
# ============================================================

@router.get("/resumes/{resume_id}/internships/{internship_id}/ats-report")
def get_ats_report(
    resume_id: int,
    internship_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, resume_id, current_user)
    internship = get_available_internship(db, internship_id)
    return {"resume_id": resume.resume_id, "internship": internship_ref(internship),
            **ats_report(facts_or_422(db, resume), internship)}


# ============================================================
# CREATE CUSTOMIZED RESUME
# POST /documents/resume
# ============================================================

@router.post("/resume", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_resume_document(
    request: CreateResumeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, request.resume_id, current_user)
    internship = get_available_internship(db, request.internship_id)
    provider = llm_provider_for(request)
    candidate = facts_or_422(db, resume)

    options = ResumeOptions(**request.options.model_dump())
    content, log = customize_resume(candidate, internship, options, provider)
    document = save_new_document(
        db, current_user, resume, internship, "resume",
        f"Resume - {internship.title} at {internship.company}"[:255],
        content, log, provider, {**request.options.model_dump(), "use_llm": request.use_llm},
        ats_report(candidate, internship),
    )
    return to_response(document)


# ============================================================
# CREATE COVER LETTER
# POST /documents/cover-letter
# ============================================================

@router.post("/cover-letter", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
def create_cover_letter_document(
    request: CreateCoverLetterRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = get_owned_resume(db, request.resume_id, current_user)
    internship = get_available_internship(db, request.internship_id)
    provider = llm_provider_for(request)
    candidate = facts_or_422(db, resume)

    options = CoverLetterOptions(tone=request.tone, emphasize_skills=tuple(request.emphasize_skills))
    try:
        content, log = generate_cover_letter(
            candidate, internship, options,
            learning_skills_for(db, resume.resume_id, internship), provider,
        )
    except InvalidEmphasisError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))

    document = save_new_document(
        db, current_user, resume, internship, "cover_letter",
        f"Cover letter - {internship.title} at {internship.company}"[:255],
        content, log, provider,
        {"tone": request.tone, "emphasize_skills": request.emphasize_skills, "use_llm": request.use_llm},
        None,
    )
    return to_response(document)


# ============================================================
# LIST / DETAIL
# ============================================================

@router.get("", response_model=list[DocumentListItem])
def list_documents(
    document_type: str | None = Query(default=None, alias="type", pattern="^(resume|cover_letter)$"),
    resume_id: int | None = None,
    internship_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        select(GeneratedDocument)
        .where(GeneratedDocument.user_id == current_user.user_id)
        .options(selectinload(GeneratedDocument.internship))
        .order_by(GeneratedDocument.updated_at.desc(), GeneratedDocument.document_id.desc())
    )
    if document_type:
        query = query.where(GeneratedDocument.document_type == document_type)
    if resume_id is not None:
        query = query.where(GeneratedDocument.resume_id == resume_id)
    if internship_id is not None:
        query = query.where(GeneratedDocument.internship_id == internship_id)

    return [
        DocumentListItem(
            document_id=d.document_id, document_type=d.document_type, title=d.title,
            resume_id=d.resume_id, internship=internship_ref(d.internship),
            generation_method=d.generation_method, current_version=d.current_version,
            warning_count=warning_count(d.fact_check), created_at=d.created_at, updated_at=d.updated_at,
        )
        for d in db.scalars(query)
    ]


@router.get("/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return to_response(get_owned_document(db, document_id, current_user))


# ============================================================
# EDIT (creates a new version)
# PATCH /documents/{document_id}
# ============================================================

@router.patch("/{document_id}", response_model=DocumentResponse)
def update_document(
    document_id: int,
    request: UpdateDocumentRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_owned_document(db, document_id, current_user)
    content = request.content.model_dump()

    if content["type"] != document.document_type:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail=f"Content type must be '{document.document_type}'.")

    fact_check = check_edited_content(db, document, content)
    if request.title is not None:
        document.title = request.title
    add_version(db, document, content, "edited", fact_check)
    db.commit()
    return to_response(get_owned_document(db, document_id, current_user))


# ============================================================
# VERSIONS
# ============================================================

@router.get("/{document_id}/versions", response_model=list[VersionItem])
def list_versions(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_owned_document(db, document_id, current_user)
    return [
        VersionItem(version=v.version, source=v.source,
                    warning_count=warning_count(v.fact_check), created_at=v.created_at)
        for v in document.versions
    ]


@router.post("/{document_id}/versions/{version}/restore", response_model=DocumentResponse)
def restore_version(
    document_id: int,
    version: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_owned_document(db, document_id, current_user)
    snapshot = next((v for v in document.versions if v.version == version), None)
    if snapshot is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    add_version(db, document, dict(snapshot.content_json), "restored", snapshot.fact_check)
    db.commit()
    return to_response(get_owned_document(db, document_id, current_user))


# ============================================================
# DOWNLOAD
# GET /documents/{document_id}/download?format=docx|txt
# ============================================================

@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    file_format: str = Query(default="docx", alias="format", pattern="^(docx|txt)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_owned_document(db, document_id, current_user)
    company = document.internship.company if document.internship else None
    filename = download_filename(document.document_type, company, file_format)

    if file_format == "docx":
        body, media_type = render_docx(document.content_json or {}), DOCX_MEDIA_TYPE
    else:
        body, media_type = render_text(document.content_json or {}).encode("utf-8"), "text/plain; charset=utf-8"

    return Response(
        content=body,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


# ============================================================
# DELETE (permanent; the UI must ask for confirmation)
# DELETE /documents/{document_id}
# ============================================================

@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    document = get_owned_document(db, document_id, current_user)
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
