"""Study documents for document-based Q&A (HR assignment). Signed-in users; each sees only their own.

POST   /study-documents              upload a PDF/DOCX (multipart "file"); text is extracted and stored
GET    /study-documents              list my documents
GET    /study-documents/{id}         one document (metadata + preview + passage references)
DELETE /study-documents/{id}         delete it (its passages go with it)
POST   /study-documents/{id}/ask     ask one question without a chat (same engine as the assistant)
POST   /study-documents/ask          ask one question across several of my documents (document_ids)

Questions count towards the assistant's per-minute / per-day limits; AI answers also towards the hourly AI limit.
"""

import logging

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import StudyDocument, User
from backend.routes.resumes import validate_resume_file
from backend.services import study_documents
from backend.services.assistant import doc_agent, rate_limit
from backend.services.llm.base import get_llm_provider
from backend.utils.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/study-documents", tags=["Study Documents"])


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    use_llm: bool = False
    llm_consent: bool = False
    mode: Literal["auto", "standard", "agentic"] = "auto"


class MultiAskRequest(AskRequest):
    document_ids: list[int] = Field(min_length=1, max_length=5)


def error(exc: study_documents.DocumentError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message})


def owned_or_404(db: Session, user: User, document_id: int) -> StudyDocument:
    document = study_documents.owned(db, user.user_id, document_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...), db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    data = await file.read(study_documents.MAX_BYTES + 1)
    if len(data) > study_documents.MAX_BYTES:
        raise HTTPException(status_code=413, detail={"code": "too_large", "message": "The file is larger than 10 MB."})
    if not data:
        raise HTTPException(status_code=422, detail={"code": "empty", "message": "The file is empty."})
    filename = (file.filename or "document").replace("\\", "/").split("/")[-1][:255]
    file_type = validate_resume_file(filename, data)          # extension + real content (+ DOCX zip limits)
    try:
        document = study_documents.create(db, current_user.user_id, filename, file_type, data)
    except study_documents.DocumentError as exc:
        db.rollback()
        raise error(exc) from None
    logger.info("study document %s uploaded by user %s (%s, %s chunks)", document.document_id, current_user.user_id,
                file_type, document.chunk_count)
    return study_documents.summary(document)


@router.get("")
def list_documents(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = db.scalars(select(StudyDocument).where(StudyDocument.user_id == current_user.user_id)
                      .order_by(StudyDocument.created_at.desc(), StudyDocument.document_id.desc()))
    return [study_documents.summary(d, preview_chars=160) for d in rows]


@router.get("/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    document = owned_or_404(db, current_user, document_id)
    return {**study_documents.summary(document, preview_chars=1200),
            "passages": [{"position": c.position, "reference": study_documents.reference(c), "chars": len(c.text)}
                         for c in document.chunks]}


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.delete(owned_or_404(db, current_user, document_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _answer(documents: list[StudyDocument], body: AskRequest, db: Session, user: User) -> dict:
    if body.use_llm and not body.llm_consent:
        raise HTTPException(status_code=400, detail="AI answers need llm_consent=true after showing the disclosure.")
    try:
        rate_limit.hit(db.get_bind(), user.user_id, ("minute", "day"))
    except rate_limit.RateLimited as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                            detail=f"Too many questions. Try again in {exc.retry_after} seconds.",
                            headers={"Retry-After": str(exc.retry_after)}) from None
    provider = get_llm_provider() if body.use_llm else None
    if provider is not None:
        from backend.services.assistant.llm_rewrite import CountingProvider
        provider = CountingProvider(provider, db.get_bind(), user.user_id)   # hourly AI limit
    reply = doc_agent.reply(documents, body.question.strip(), provider, mode=body.mode)
    return {"document_ids": [d.document_id for d in documents], "task": reply.task, "found": reply.found,
            "content": reply.content, "sources": reply.sources, "generation_method": reply.method,
            "warnings": reply.warnings, "semantic_retrieval": reply.semantic, "llm": reply.llm_log}


@router.post("/ask")
def ask_many(body: MultiAskRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    documents = [owned_or_404(db, current_user, i) for i in dict.fromkeys(body.document_ids)]
    return _answer(documents, body, db, current_user)


@router.post("/{document_id}/ask")
def ask(document_id: int, body: AskRequest, db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user)):
    document = owned_or_404(db, current_user, document_id)
    return {"document_id": document.document_id, **_answer([document], body, db, current_user)}
