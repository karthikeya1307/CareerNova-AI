"""Intent detection and entity extraction (pure functions, no database).

Stage 1 is rule-based (ordered regular expressions). Stage 2 (optional) uses
the local, pinned MiniLM model to compare the question with example phrases;
it only runs when the real model is configured, never sends anything off the
server, and is skipped in tests that use the hashing embedder.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from backend.services.fact_check import skill_mentions

INTENTS = (
    "help", "profile_summary", "internship_search", "internship_detail", "top_matches", "match_explain",
    "skill_gap", "learning_plan", "document_help", "interview_prep", "application_status",
    "upcoming_interviews", "reminders", "dashboard", "unknown",
)

# Ordered from most to least specific; ties go to the earlier intent.
RULES: list[tuple[str, list[str]]] = [
    ("upcoming_interviews", [r"\b(upcoming|next|scheduled|when is my|when are my) interviews?\b",
                             r"\binterviews? (this|next) (week|month)\b", r"\bmy (upcoming |next )?interviews\b"]),
    ("reminders", [r"\breminders?\b", r"\bfollow[- ]?ups?\b", r"\bto[- ]?dos?\b"]),
    ("dashboard", [r"\bdashboard\b", r"\b(statistics|stats)\b", r"\bsuccess rate\b",
                   r"\bhow many (applications|internships have i|times have i)\b",
                   r"\b(overview|summary) of my applications\b"]),
    ("interview_prep", [r"\binterview (prep|preparation|practice|questions?|tips)\b",
                        r"\bpractice (questions?|interview|for)\b", r"\bmock interview\b",
                        r"\bprepare (me )?for (an |the |my )?interview\b", r"\binterview (progress|scores?)\b",
                        r"\bmy interview (progress|practice|scores?|results?)\b",
                        r"\bask me (a |an |some )?questions?\b"]),
    ("document_help", [r"\bcover letters?\b", r"\btailor(ed)? (my )?resume\b", r"\bcustomi[sz]e (my )?resume\b",
                       r"\bats\b", r"\bresume (tips|help|review|feedback)\b", r"\bimprove my (resume|cv)\b",
                       r"\bmy documents?\b"]),
    ("learning_plan", [r"\bhow (do|can|should|would) i (learn|study|get better at|improve (at|in))\b",
                       r"\blearning (plan|path|roadmap)\b", r"\bstudy plan\b", r"\broadmap\b",
                       r"\bresources? (for|to learn)\b", r"\bteach me\b", r"\bwhere (do|should) i start\b"]),
    ("skill_gap", [r"\b(missing|lacking)\b", r"\bskill gaps?\b", r"\bgaps?\b",
                   r"\bwhat (skills )?(do|should) i (need|learn|improve)\b",
                   r"\bwhat (am i|do i) (missing|lack)\b", r"\bimprove my chances\b", r"\bneed to learn\b",
                   r"\b(don't|do not|dont) i (have|know)\b", r"\b(skills|abilities) i (don't|do not|dont) have\b"]),
    ("match_explain", [r"\bwhy\b.*\b(match|fit|score|good|suitable|recommended)\b",
                       r"\bhow (well|good)\b.*\b(match|fit)\b", r"\bexplain\b.*\b(match|score)\b",
                       r"\bmatch(ing)? score\b", r"\bcompatib"]),
    ("top_matches", [r"\b(top|best) (matches|internships for me|fits?)\b", r"\bmy (top |best )?matches\b",
                     r"\bwhich internships? (suit|fit|match)( me)?\b", r"\bbest suited\b",
                     r"\brecommended (internships|for me)\b"]),
    ("internship_detail", [r"\btell me (more )?about\b", r"\bdetails? (of|about|for|on)\b",
                           r"\bmore (info|information|details)\b", r"\bdescribe\b",
                           r"\bwhat does (it|that|this|the \w+ one) (involve|require|pay|offer)\b",
                           r"\b(deadline|stipend|duration|eligibility|requirements?) (of|for)\b"]),
    ("internship_search", [r"\b(find|search|show|look(ing)? for|recommend|suggest|any|list|get)\b.*"
                           r"\b(internships?|jobs?|roles?|openings?|positions?|opportunit(y|ies))\b",
                           r"\binternships? (in|for|about|related to|with|at|on)\b",
                           r"\b(remote|hybrid|onsite|on-site)\b.*\binternships?\b"]),
    ("profile_summary", [r"\bmy (skills|resume|cv|profile|education|degree|qualifications?|projects|experience)\b",
                         r"\bwhat (skills )?do i (have|know)\b", r"\bsummari[sz]e (me|my)\b",
                         r"\bwhat('s| is) on my (resume|cv)\b"]),
    ("application_status", [r"\b(my )?applications?\b", r"\bapplied\b", r"\bstatus\b",
                            r"\b(sent|submitted) my (cv|resume|application)s?\b",
                            r"\b(news|updates?|heard) (on|about|from)\b.*\b(jobs?|applications?|internships?|companies)\b",
                            r"\b(shortlisted|rejected|selected|withdrawn)\b", r"\bdid i (get|hear)\b"]),
    ("help", [r"^(hi|hello|hey|hii+|good (morning|afternoon|evening)|namaste)\b",
              r"\bhelp\b", r"\bwhat can you do\b", r"\bhow (do|does) (you|this) work\b", r"\bwhat do you know\b"]),
]
_COMPILED = [(intent, [re.compile(p) for p in patterns]) for intent, patterns in RULES]

ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
    "ninth": 9, "tenth": 10, "last": -1, "1st": 1, "2nd": 2, "3rd": 3, "4th": 4, "5th": 5, "6th": 6,
    "7th": 7, "8th": 8, "9th": 9, "10th": 10, "top": 1,
}
ORDINAL_RE = re.compile(
    r"\b(?:the\s+)?(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|last|1st|2nd|3rd|4th|"
    r"5th|6th|7th|8th|9th|10th)(?:\s+(?:one|option|result|internship|application|match|item|skill|interview|"
    r"reminder))?\b"
    r"|(?:\b(?:number|no\.?|option|result)|(?<![\w#])#)\s*(\d{1,2})\b"
    r"|\bthe\s+(\d{1,2})(?:st|nd|rd|th)?\s+one\b")
TOP_ONE_RE = re.compile(r"\b(?:the\s+)?top\s+(?:one|result|match|internship)\b")
EXPLICIT_INTERNSHIP_RE = re.compile(r"\binternship\s*(?:id|#|no\.?|number)\s*:?\s*(\d{1,9})\b")
EXPLICIT_APPLICATION_RE = re.compile(r"\bapplication\s*(?:id|#|no\.?|number)\s*:?\s*(\d{1,9})\b")
REFERENT_RE = re.compile(r"\b(it|that one|this one|that internship|this internship|that application|"
                         r"this application|that role|this role|that company|this company|that|this|them|"
                         r"the same one)\b")
FOLLOWUP_RE = re.compile(r"^(and |what about |how about |and what about |ok,? |okay,? |then )")

STATUS_WORDS = {
    "saved": "SAVED", "applied": "APPLIED", "shortlisted": "SHORTLISTED", "interview scheduled": "INTERVIEW_SCHEDULED",
    "interviewing": "INTERVIEW_SCHEDULED", "selected": "SELECTED", "offer": "SELECTED", "offers": "SELECTED",
    "rejected": "REJECTED", "rejections": "REJECTED", "withdrawn": "WITHDRAWN", "withdrew": "WITHDRAWN",
}
WORK_MODES = {"remote": "Remote", "work from home": "Remote", "wfh": "Remote", "hybrid": "Hybrid",
              "onsite": "Onsite", "on-site": "Onsite", "on site": "Onsite", "in office": "Onsite",
              "in-office": "Onsite"}

STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "in", "on", "at", "to", "of", "with", "about", "me", "my", "i", "is",
    "are", "any", "some", "find", "search", "show", "look", "looking", "list", "get", "give", "recommend",
    "suggest", "internship", "internships", "job", "jobs", "role", "roles", "opening", "openings", "position",
    "positions", "opportunity", "opportunities", "please", "can", "you", "could", "would", "want", "need",
    "related", "that", "this", "there", "what", "which", "where", "who", "remote", "hybrid", "onsite", "do",
    "have", "has", "new", "available", "good", "best", "top", "all", "be", "it", "from", "by", "as", "near",
    "one", "ones", "more", "tell", "why", "how", "when", "please", "number", "option", "result", "last",
    "first", "second", "third", "fourth", "fifth", "1st", "2nd", "3rd", "4th", "5th", "am", "were", "was",
    "will", "should", "they", "them", "those", "these", "like", "also", "just", "only", "work", "working",
}

MAX_QUESTION_CHARS = 2000


@dataclass
class Understanding:
    intent: str
    confidence: str                     # rule | semantic | followup | none
    ordinal: int | None = None          # 1-based, -1 = last
    referent: bool = False              # "it", "that one", ...
    internship_id: int | None = None    # explicit "internship #12"
    application_id: int | None = None   # explicit "application #5"
    skills: list[str] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)
    work_mode: str | None = None
    search_terms: list[str] = field(default_factory=list)
    text: str = ""
    matched: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"intent": self.intent, "confidence": self.confidence, "ordinal": self.ordinal,
                "referent": self.referent, "internship_id": self.internship_id,
                "application_id": self.application_id, "skills": self.skills, "statuses": self.statuses,
                "work_mode": self.work_mode, "search_terms": self.search_terms}


def normalize(text: str) -> str:
    text = (text or "").replace("’", "'").lower().strip()
    return re.sub(r"\s+", " ", text)


def rule_scores(text: str) -> dict[str, int]:
    return {intent: sum(1 for p in patterns if p.search(text)) for intent, patterns in _COMPILED}


def pick_intent(scores: dict[str, int]) -> str | None:
    best = max(scores.values(), default=0)
    if best == 0:
        return None
    return next(intent for intent, _ in RULES if scores[intent] == best)


def extract_ordinal(text: str) -> int | None:
    if TOP_ONE_RE.search(text):
        return 1
    match = ORDINAL_RE.search(text)
    if not match:
        return None
    word, number, nth = match.groups()
    if word:
        return ORDINAL_WORDS[word]
    value = int(number or nth)
    return value if value >= 1 else None


def extract_statuses(text: str) -> list[str]:
    found = []
    for word, status in STATUS_WORDS.items():
        if re.search(rf"\b{re.escape(word)}\b", text) and status not in found:
            found.append(status)
    return found


def extract_work_mode(text: str) -> str | None:
    for word, mode in WORK_MODES.items():
        if re.search(rf"\b{re.escape(word)}\b", text):
            return mode
    return None


def extract_search_terms(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9+#.]+", text)
    return [w for w in words if w not in STOPWORDS and len(w) >= 2 and not w.isdigit()][:12]


def understand(raw: str, semantic=None) -> Understanding:
    """Classify a question and extract entities. ``semantic`` is an optional SemanticIntent."""
    text = normalize(raw)[:MAX_QUESTION_CHARS]
    explicit_internship = EXPLICIT_INTERNSHIP_RE.search(text)
    explicit_application = EXPLICIT_APPLICATION_RE.search(text)
    stripped = EXPLICIT_APPLICATION_RE.sub(" ", EXPLICIT_INTERNSHIP_RE.sub(" ", text))

    scores = rule_scores(text)
    intent = pick_intent(scores)
    confidence = "rule" if intent else "none"
    if intent is None and semantic is not None:
        intent = semantic.classify(text)
        confidence = "semantic" if intent else "none"

    ordinal = extract_ordinal(stripped)
    referent = bool(REFERENT_RE.search(stripped)) and ordinal is None
    if intent is None and (ordinal is not None or referent or FOLLOWUP_RE.search(text)):
        intent, confidence = "followup", "followup"

    return Understanding(
        intent=intent or "unknown", confidence=confidence, ordinal=ordinal, referent=referent,
        internship_id=int(explicit_internship.group(1)) if explicit_internship else None,
        application_id=int(explicit_application.group(1)) if explicit_application else None,
        skills=sorted(skill_mentions(raw or "")), statuses=extract_statuses(text),
        work_mode=extract_work_mode(text), search_terms=extract_search_terms(stripped), text=text,
        matched={k: v for k, v in scores.items() if v})


# ------------------------------------------------------------------
# Optional stage 2: local semantic matching against example phrases
# ------------------------------------------------------------------

EXAMPLES: dict[str, list[str]] = {
    "profile_summary": ["what is on my resume", "summarise my profile", "which skills do I have"],
    "skill_gap": ["what skills am I lacking", "what should I learn to qualify", "which skills don't I have yet",
                  "what am I missing for these roles"],
    "internship_search": ["find internships for me", "show me data science openings",
                          "are there any web development roles", "do you have anything in machine learning for me"],
    "top_matches": ["which internships suit me best", "what are my best matches"],
    "match_explain": ["why am I a good fit for this internship", "explain my compatibility score"],
    "learning_plan": ["how can I get good at this skill", "give me a study roadmap",
                      "how would I go about learning a new technology"],
    "document_help": ["help me write a cover letter", "is my resume ready for applicant tracking systems"],
    "interview_prep": ["help me prepare for my interview", "give me practice questions"],
    "application_status": ["what happened with my application", "where do my applications stand",
                           "any updates on the jobs I applied to"],
    "upcoming_interviews": ["when is my next interview", "do I have interviews coming up"],
    "reminders": ["what do I need to follow up on", "show my pending reminders"],
    "dashboard": ["how am I doing overall with applications", "show my application statistics"],
    "help": ["what can you help me with", "how do I use you"],
}
SEMANTIC_THRESHOLD = 0.55
SEMANTIC_MARGIN = 0.05


class SemanticIntent:
    def __init__(self, embedder):
        import numpy as np

        self.embedder = embedder
        self.labels = [intent for intent, phrases in EXAMPLES.items() for _ in phrases]
        self.vectors = np.asarray(embedder.embed([p for phrases in EXAMPLES.values() for p in phrases]))

    def scores(self, text: str) -> dict[str, float]:
        import numpy as np

        vector = np.asarray(self.embedder.embed([text]))[0]
        sims = self.vectors @ vector
        best: dict[str, float] = {}
        for label, sim in zip(self.labels, sims):
            best[label] = max(best.get(label, -1.0), float(sim))
        return best

    def classify(self, text: str) -> str | None:
        ranked = sorted(self.scores(text).items(), key=lambda kv: kv[1], reverse=True)
        if not ranked or ranked[0][1] < SEMANTIC_THRESHOLD:
            return None
        if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < SEMANTIC_MARGIN:
            return None
        return ranked[0][0]


def default_semantic_intent() -> SemanticIntent | None:
    """Only with the configured local model (tests use a hashing embedder and stay rule-only)."""
    try:
        from backend.services import embeddings

        embedder = embeddings.get_embedder()
        if embedder.model_name != embeddings.embedding_settings()["model_name"]:
            return None
        return SemanticIntent(embedder)
    except Exception:
        return None
