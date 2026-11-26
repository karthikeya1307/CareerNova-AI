"""Document Q&A inside the Interview Preparation Assistant (HR assignment).

A conversation can have up to 5 study documents attached (``conversation.context["study_document_ids"]``,
set through PUT /assistant/conversations/{id}/study-document). While documents are attached, questions are
answered from them only - except questions clearly about the student's resume or roles, which still go to
the preparation agent. Follow-up questions ("explain that more") reuse the previous question for retrieval.
Ownership is checked on every message: a deleted document simply stops being searched.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Conversation, StudyDocument, User
from backend.services import study_qa
from backend.services.assistant import prep_agent
from backend.services.assistant.facts import Source

MAX_ATTACHED = 5
FOLLOWUP = re.compile(r"\b(it|this|that|these|those|them|more|elaborate|example|examples|why|how so|again|simpler|"
                      r"further|detail|details)\b", re.I)
RESUME_TOPIC = re.compile(r"\b(my (resume|cv|skills?|profile|strengths?|weakness(es)?)|roles?|suitable for|am i)\b", re.I)


@dataclass
class DocReply:
    task: str
    found: bool
    content: str
    sources: list[dict[str, str]]
    method: str = "deterministic"
    warnings: list[dict[str, str]] = field(default_factory=list)
    semantic: bool = False
    llm_log: dict[str, Any] | None = None
    provider: str | None = None
    model: str | None = None


def source(library: study_qa.Library, chunk) -> dict[str, str]:
    return Source("study_document", f"{chunk.document_id}:{chunk.position}",
                  f"{chunk.document.filename} ({study_qa.reference(chunk)})").as_dict()


def render(library: study_qa.Library, base: study_qa.DocAnswer) -> tuple[str, list[dict[str, str]]]:
    lines, sources, seen = [base.intro], [], set()

    def cite(chunk) -> str:
        key = (chunk.document_id, chunk.position)
        if key not in seen:
            seen.add(key)
            sources.append(source(library, chunk))
        return library.ref(chunk)

    for point in base.points:
        lines.append(f"- {point.text} [{cite(point.chunk)}]")
    for heading, points in base.extra:
        lines.append(f"## {heading}")
        for point in points:
            lines.append(f"- {point.text} [{cite(point.chunk)}]")
    if base.outro:
        lines.append(base.outro)
    return "\n".join(lines).strip(), sources


def reply(documents, question: str, provider=None, previous: str | None = None, mode: str = "auto") -> DocReply:
    library = documents if isinstance(documents, study_qa.Library) else study_qa.Library(
        documents if isinstance(documents, list) else [documents])
    query = question
    if previous and len(question.split()) <= 8 and FOLLOWUP.search(question) and study_qa.detect_task(question) == "answer":
        query = f"{previous} {question}"
    base = study_qa.answer(library, query, mode)
    content, sources = render(library, base)
    result = DocReply(base.task, base.found, content, sources, semantic=base.semantic)
    if not base.semantic and base.task == "answer":
        result.warnings.append({"code": "keyword_retrieval",
                                "detail": "The semantic search model is not available, so passages were found by keywords."})
    if provider is None:
        return result
    text, cited, log = study_qa.ai_answer(provider, library, query, base)
    result.llm_log = log
    if text:
        refs = "; ".join(library.ref(c) for c in cited)
        where = f"\"{library.filename}\"" if not library.multiple else "your documents"
        result.content = f"{text}\n\nSources in {where}: {refs}."
        result.sources = [source(library, c) for c in cited]
        result.method, result.provider, result.model = "llm", provider.name, provider.model
    elif text == "" and not base.found:
        result.content = ("Your documents don't contain this, so I can't answer it from them. Try different words "
                          "or ask for a summary.")
    else:
        result.warnings.append({"code": "llm_unverified" if log.get("llm_used") else "llm_unavailable",
                                "detail": "The AI answer could not be checked against the document, so the answer quoted "
                                          "from the document is shown." if log.get("llm_used") else
                                          "AI assistance was not available, so the answer quoted from the document is shown."})
    return result


def attached_ids(conversation: Conversation) -> list[int]:
    context = conversation.context or {}
    ids = context.get("study_document_ids")
    if ids is None and context.get("study_document_id"):          # conversations from before multi-document support
        ids = [context["study_document_id"]]
    return [int(i) for i in (ids or [])][:MAX_ATTACHED]


def attached_documents(db: Session, user: User, conversation: Conversation) -> list[StudyDocument]:
    ids = attached_ids(conversation)
    if not ids:
        return []
    rows = db.scalars(select(StudyDocument).where(StudyDocument.document_id.in_(ids),
                                                  StudyDocument.user_id == user.user_id))   # owner check
    by_id = {d.document_id: d for d in rows}
    return [by_id[i] for i in ids if i in by_id]


def route(db: Session, user: User, conversation: Conversation, text: str, provider=None
          ) -> tuple[DocReply, list[StudyDocument]] | None:
    documents = attached_documents(db, user, conversation)
    if not documents:
        return None
    if prep_agent.detect(text) is not None and RESUME_TOPIC.search(text):
        return None                                     # resume/role questions keep the preparation agent
    previous = (conversation.context or {}).get("doc_last_query")
    return reply(documents, text, provider, previous), documents
