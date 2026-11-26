"""Facts, sources and tool results.

Every factual line the assistant says is an ``AssistantFact`` with one or
more ``Source`` records (type, id, label) that identify exactly which
resume, internship, match result, recommendation, application, ... it came
from. Nothing outside the facts is ever presented as data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SOURCE_TYPES = (
    "resume", "resume_fact", "internship", "match_result", "skill_gap_recommendation", "learning_plan",
    "document", "interview_session", "interview_progress", "question_bank", "application",
    "application_interview", "application_reminder", "dashboard", "bookmark",
    "product_doc",                       # a chunk of the product guide (backend/data/product_docs)
    "career_track",                      # a curated role track (backend/data/career_tracks.json)
    "study_document",                    # a passage of a document the student uploaded for Q&A
)


@dataclass(frozen=True)
class Source:
    type: str
    id: str
    label: str

    def __post_init__(self):
        assert self.type in SOURCE_TYPES, self.type

    def as_dict(self) -> dict[str, str]:
        return {"type": self.type, "id": self.id, "label": self.label[:200]}


@dataclass
class AssistantFact:
    id: str                              # "F1", "F2", ... (per answer)
    text: str
    sources: list[Source]
    polarity: dict[str, str] = field(default_factory=dict)   # skill -> have | missing | partial
    # What may be sent to the optional AI provider. None = ``text``. Facts built from free text the
    # student typed (reminder titles, document titles, external company/job titles) get a version
    # without that text, because it can contain other people's names or contact details.
    llm_text: str | None = None

    @property
    def kind(self) -> str:               # compatibility with fact_check.check_statement
        return "assistant"

    def for_llm(self) -> "AssistantFact":
        return AssistantFact(self.id, self.llm_text if self.llm_text is not None else self.text, self.sources,
                             self.polarity)


@dataclass
class ResultItem:
    """One entry of an ordered list shown to the student (for "the second one" follow-ups)."""
    type: str                            # internship | application | skill | ...
    id: str
    label: str
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"type": self.type, "id": self.id, "label": self.label[:200], **({"extra": self.extra}
                                                                              if self.extra else {})}


@dataclass
class ToolResult:
    status: str = "ok"                   # ok | empty | not_found | clarify | needs_resume | unavailable
    intro: str = ""                      # non-factual framing ("Here is what I found:")
    facts: list[AssistantFact] = field(default_factory=list)
    outro: str = ""                      # non-factual guidance (never contains data)
    result_kind: str | None = None       # set when an ordered list is shown
    results: list[ResultItem] = field(default_factory=list)
    focus: ResultItem | None = None      # the single entity this answer was about
    actions: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    uses_resume_id: int | None = None    # set when the answer used resume data
    clarify_options: list[ResultItem] = field(default_factory=list)

    def add(self, text: str, *sources: Source, polarity: dict[str, str] | None = None,
            llm_text: str | None = None) -> AssistantFact:
        fact = AssistantFact(id=f"F{len(self.facts) + 1}", text=text, sources=list(sources),
                             polarity=polarity or {}, llm_text=llm_text)
        self.facts.append(fact)
        return fact

    def sources(self) -> list[dict[str, str]]:
        seen, out = set(), []
        for fact in self.facts:
            for source in fact.sources:
                key = (source.type, source.id)
                if key not in seen:
                    seen.add(key)
                    out.append(source.as_dict())
        return out


def action(label: str, method: str, endpoint: str, body: dict[str, Any] | None = None,
           requires_confirmation: bool = True) -> dict[str, Any]:
    """A suggestion for the frontend; the assistant itself never performs it."""
    return {"label": label, "method": method, "endpoint": endpoint, "body": body or {},
            "requires_confirmation": requires_confirmation}


def fmt_date(value) -> str:
    if value is None:
        return "not stated"
    from datetime import timezone
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d %b %Y")


def fmt_datetime(value) -> str:
    from datetime import timezone
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC")


def pct(value: float | None) -> str:
    return "not available" if value is None else f"{round(value * 100):d}%"
