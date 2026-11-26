"""Product questions: retrieval-augmented answers from the product guide, with conversational memory.

Questions about how CareerNova AI works ("How do I upload my resume?", "How is the score
calculated?") are answered from the product knowledge base (``backend.services.product_kb``):

1. Routing: a question is treated as a product question when it asks how/what/why about the
   product without referring to the student's own records, or when it was not recognised as a
   data question. Data questions ("show my matches") keep their existing tools.
2. Memory: a short follow-up right after a product answer ("and which file types?", "how long can
   it be?") is combined with the previous product question before retrieval, and the recent product
   turns are passed to the optional AI provider.
3. Retrieval: the question is embedded and the most similar guide chunks are retrieved.
4. Answer: without AI, the most relevant sentences of the retrieved chunks are returned (extractive,
   so nothing is invented). With AI (opt-in, with consent), the provider writes an answer from the
   retrieved excerpts only; it must cite them and every sentence must be supported by them,
   otherwise the extractive answer is shown.
5. Scope: below the relevance threshold the assistant says the guide does not cover the question
   (product topics) or that it only answers questions about CareerNova AI (anything else).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Conversation, Message
from backend.services import product_kb
from backend.services.assistant.facts import Source, ToolResult

ANSWER_THRESHOLD = 0.40        # calibrated with all-MiniLM-L6-v2: covered questions 0.47-0.87,
                               # uncovered product topics <= 0.30, unrelated questions <= 0.17
SUPPORT_MARGIN = 0.10          # other chunks this close to the best one also contribute sentences
MAX_CHUNKS = 2
MAX_SENTENCES = 4
HISTORY_TURNS = 3              # earlier product questions passed to the AI provider

QUESTION_RE = re.compile(r"^\s*(how|what|which|why|where|when|can|could|does|do|did|is|are|should|will|would|"
                         r"explain|tell me|describe)\b", re.IGNORECASE)
PERSONAL_RE = re.compile(r"\b(my|mine|me|am i|i've|i have|i am|i'm)\b", re.IGNORECASE)
USER_HOWTO_RE = re.compile(r"\b(how (do|can|should|would|could) i|can i|could i|where (do|can) i|how to|"
                           r"is it possible|am i able)\b", re.IGNORECASE)
# "this application/app/product" usually means CareerNova AI itself, unless the question is about the
# state of a job application ("what is the status of this application?").
SELF_REFERENCE_RE = re.compile(r"\b(this|the|your) (app|application|product|platform|website|site|tool|service)\b|"
                               r"\b(careernova( ai)?|ai career companion)\b", re.IGNORECASE)
RECORD_WORDS_RE = re.compile(r"\b(status|stage|update\w*|deadline|happen\w*|progress|offer|reject\w*|withdraw\w*|"
                             r"submitted|applied|interview date)\b", re.IGNORECASE)
FOLLOWUP_START_RE =re.compile(r"^\s*(and|also|then|what about|how about|ok(ay)?|so)\b", re.IGNORECASE)
PRONOUN_RE = re.compile(r"\b(it|its|that|this|they|them|those|these|there)\b", re.IGNORECASE)
PRODUCT_TERMS_RE = re.compile(
    r"\b(careernova|careernova ai|ai career companion|career companion|app|application|product|platform|website|site|feature|account|"
    r"sign ?(in|up)|log ?in|register|verif\w*|password|resume|cv|upload\w*|pars\w*|internship\w*|match\w*|"
    r"compatib\w*|score\w*|skill\w*|learning plan|cover letter|letter\w*|tailor\w*|document\w*|ats|"
    r"interview\w*|mock|practice|practis\w*|status\w*|reminder\w*|bookmark\w*|saved|trash|assistant|chat\w*|"
    r"conversation\w*|dashboard|admin\w*|privacy|private|data|ai|llm|consent|download\w*|docx|pdf|file\w*|"
    r"subscription\w*|pric\w*|premium|cost\w*|free|paid|mobile|offline)\b",
    re.IGNORECASE)


@dataclass
class ProductRoute:
    intent: str                # "product_help" (answered or not covered) | "unknown" (out of scope)
    result: ToolResult
    query: str                 # the text used for retrieval (includes the previous question for follow-ups)
    hits: list[product_kb.Hit] = field(default_factory=list)
    followup: bool = False
    threshold: float = ANSWER_THRESHOLD      # lower when the keyword fallback is in use


# ------------------------------------------------------------------
# Memory
# ------------------------------------------------------------------

def previous_product_turn(db: Session, conversation: Conversation) -> Message | None:
    """The assistant message of the last product answer, if it was the latest answer in the conversation."""
    pointer = (conversation.context or {}).get("product") or {}
    message_id = pointer.get("message_id")
    if not message_id:
        return None
    message = db.get(Message, message_id)
    if message is None or message.conversation_id != conversation.conversation_id:
        return None
    return message


def is_followup_text(text: str) -> bool:
    words = re.findall(r"[\w'-]+", text)
    return bool(FOLLOWUP_START_RE.search(text) or PRONOUN_RE.search(text) or len(words) <= 4)


def product_history(db: Session, conversation: Conversation, limit: int = HISTORY_TURNS) -> list[dict[str, str]]:
    """Recent product question/answer pairs in this conversation (oldest first)."""
    from sqlalchemy import select

    rows = list(db.scalars(
        select(Message).where(Message.conversation_id == conversation.conversation_id,
                              Message.intent == "product_help")
        .order_by(Message.message_id.desc()).limit(limit * 2)))
    rows.reverse()
    history, question = [], None
    for message in rows:
        if message.sender == "user":
            question = message.content
        elif question is not None:
            history.append({"question": question, "answer": message.content})
            question = None
    return history[-limit:]


# ------------------------------------------------------------------
# Routing
# ------------------------------------------------------------------

def is_self_reference(text: str) -> bool:
    """The question is about the product itself ("this app", "this product"), not a job application."""
    return bool(SELF_REFERENCE_RE.search(text)) and not RECORD_WORDS_RE.search(text) \
        and not PERSONAL_RE.search(text)


def is_unrelated_topic(text: str) -> bool:
    """A short message that names something of its own the product guide never mentions ("who is ronaldo",
    "what about messi?") and does not refer back with it/that/this... It is a new, unrelated topic - not a
    follow-up - so it must not be merged with the previous product question (that leaked guide text)."""
    words = _content_words(text)
    return bool(words) and not PRONOUN_RE.search(text) and not (words & guide_vocabulary())


def looks_like_product_question(text: str) -> bool:
    """"How do I upload my resume?" / "What is this app?" - a how-to or self-reference about CareerNova
    (used by the Interview Preparation Assistant to point such questions to the Application Assistant)."""
    return bool(USER_HOWTO_RE.search(text) or is_self_reference(text))


def is_product_question(text: str, intent: str, ordinal: int | None, referent: bool) -> bool:
    """How/what/why about the product, not about the student's own records."""
    if ordinal is None and is_self_reference(text):
        return True                                    # "what is this application?", "price of this product?"
    if ordinal is not None or referent:
        return False                                   # "why is the first one a good match?", "...this internship" -> data
    if USER_HOWTO_RE.search(text):
        return True                                    # "how do I upload my resume?"
    if QUESTION_RE.search(text) and not PERSONAL_RE.search(text) and not referent:
        return True                                    # "how does matching work?", "what is mock mode?"
    return intent == "unknown"


def route(db: Session, conversation: Conversation, text: str, intent: str, ordinal: int | None,
          referent: bool, embedder=None) -> ProductRoute | None:
    """Return a product answer (or a scope fallback), or None to let the data tools answer."""
    previous = previous_product_turn(db, conversation)
    # A follow-up continues the previous product answer: it must come right after one, look like a
    # follow-up, and not be a recognised data question ("show my matches" keeps the data tools).
    followup = (previous is not None and is_followup_text(text) and not is_unrelated_topic(text)
                and (intent in ("unknown", "followup", "help") or is_product_question(text, intent, None, False)))
    if not followup and not is_product_question(text, intent, ordinal, referent):
        return None

    # "What is this application?" -> "What is CareerNova AI?": the guide names the product, not "this app".
    about_product = is_self_reference(text)
    specific = ""
    if about_product:
        specific = SELF_REFERENCE_RE.sub(" ", text)           # what is asked about the product, if anything
        text = SELF_REFERENCE_RE.sub("CareerNova AI", text)
    query = text
    # The neural model, or the keyword fallback when the model cannot be loaded (own threshold).
    embedder = embedder or product_kb.default_embedder()
    threshold = product_kb.answer_threshold(embedder, ANSWER_THRESHOLD)
    hits = product_kb.retrieve(query, k=4, embedder=embedder)
    if about_product and not _content_words(specific) <= guide_vocabulary():
        # The product name alone matches the overview strongly, so "What is the price of this product?" must
        # also find "price" in the guide; otherwise it is not covered (instead of an unrelated overview).
        hits = [product_kb.Hit(h.chunk, 0.0) for h in hits]
    if followup and not (hits and hits[0].score >= threshold):
        # A short question that doesn't stand on its own ("how big can it be?") is read together with
        # the previous product question. One that retrieves well by itself ("Is my data private?") is
        # a new topic and is answered on its own.
        earlier = (previous.entities or {}).get("product_query") or ""
        query = f"{earlier} {text}".strip()
        hits = product_kb.retrieve(query, k=4, embedder=embedder)
    else:
        followup = False
    if hits and hits[0].score >= threshold:
        return ProductRoute("product_help", answer_from_guide(query, hits, embedder, latest=text, threshold=threshold),
                            query, hits, followup, threshold)
    # Below the threshold a recognised data question keeps its data tool ("what should I learn to qualify");
    # only follow-ups and unrecognised product-sounding questions get the "not covered" fallback.
    if followup or about_product or (intent in ("unknown", "help") and PRODUCT_TERMS_RE.search(text)):
        return ProductRoute("product_help", not_covered(), query, hits, followup, threshold)
    if intent == "unknown":
        return ProductRoute("unknown", out_of_scope(), query, hits, followup, threshold)
    return None                                        # a recognised data question: keep the data tools


# ------------------------------------------------------------------
# Answers
# ------------------------------------------------------------------

def _source(chunk: product_kb.Chunk) -> Source:
    return Source("product_doc", chunk.id, chunk.label)


def supporting_hits(hits: list[product_kb.Hit], threshold: float = ANSWER_THRESHOLD) -> list[product_kb.Hit]:
    best = hits[0].score
    return [h for h in hits[:MAX_CHUNKS] if h.score >= threshold and h.score >= best - SUPPORT_MARGIN]


def answer_from_guide(query: str, hits: list[product_kb.Hit], embedder=None, latest: str | None = None,
                      threshold: float = ANSWER_THRESHOLD) -> ToolResult:
    """Extractive answer: the guide sentences most similar to the question, in reading order.

    For a follow-up, ``query`` is the previous question plus the new one (it finds the right sections)
    and ``latest`` is the new question alone, which also counts when choosing sentences, so "can I
    download it?" picks the download sentence rather than repeating the previous answer.
    """
    import numpy as np

    chosen = supporting_hits(hits, threshold)
    candidates = [(h.chunk, n, s) for h in chosen for n, s in enumerate(product_kb.split_sentences(h.chunk.text))]
    index = product_kb.get_index(embedder)
    vectors = index.embed([s for _, _, s in candidates])
    scores = vectors @ index.embed([query])[0]
    if latest and latest != query:
        scores = scores + vectors @ index.embed([latest])[0]
    top = sorted(np.argsort(-scores)[:MAX_SENTENCES])  # keep the guide's own order
    result = ToolResult(status="ok", intro="Here is what the CareerNova AI guide says:")
    for i in top:
        chunk, _, sentence = candidates[i]
        result.add(sentence, _source(chunk))
    return result


def not_covered() -> ToolResult:
    result = ToolResult(status="empty")
    result.intro = ("The CareerNova AI guide doesn't cover that, so I can't answer it reliably. "
                    "Try asking about resume upload, internship matching, skill gaps, cover letters, interview "
                    "practice or tracking applications.")
    return result


def out_of_scope() -> ToolResult:
    from backend.services.assistant.tools import help_result

    result = help_result()
    result.intro = ("I'm not sure I understood that. I can only answer questions about CareerNova AI and "
                    "your career data in it, for example \"How do I upload my resume?\" or \"How does matching "
                    "work?\".\n" + result.intro)
    return result


# ------------------------------------------------------------------
# Optional AI answer (opt-in with consent), grounded in the retrieved excerpts
# ------------------------------------------------------------------

PRODUCT_SYSTEM = (
    "You are the product assistant for CareerNova AI, a web app that helps students find internships. "
    "Answer the student's question using ONLY the guide excerpts provided. Do not use outside knowledge, do "
    "not invent features, limits, prices or steps, and do not mention the excerpts themselves. Use the earlier "
    "conversation only to understand what a follow-up question refers to. If the excerpts do not contain the "
    'answer, return {"answer": null, "cited": []}. Otherwise return {"answer": str, "cited": [excerpt ids '
    'you used]}, at most 120 words, in plain sentences. Respond with JSON only.'
)
STOPWORDS = frozenset(
    "the a an and or but of to in on for with by from at as is are was were be been being it its this that these "
    "those you your yours i me my we our they them their can could will would should do does did not no yes "
    "if then than so such also only just more most very any each every all some there here when where which "
    "who whom what why how have has had into about after before over under up down out off again further once "
    "need needs using use used get gets one two".split())


def _content_words(text: str) -> set[str]:
    return {w[:6] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def guide_vocabulary() -> set[str]:
    """Content words used anywhere in the product guide (cached per guide version)."""
    fingerprint = product_kb.docs_fingerprint()
    if _vocabulary.get("fingerprint") != fingerprint:
        words: set[str] = set()
        for chunk in product_kb.load_chunks():
            words |= _content_words(f"{chunk.document} {chunk.heading} {chunk.text}")
        _vocabulary.update(fingerprint=fingerprint, words=words)
    return _vocabulary["words"]


_vocabulary: dict[str, Any] = {}


def grounded(answer: str, chunks: list[product_kb.Chunk], min_overlap: float = 0.6) -> bool:
    """Every sentence must be mostly made of words that appear in the cited excerpts."""
    vocabulary = set().union(*[_content_words(f"{c.document} {c.heading} {c.text}") for c in chunks])
    for sentence in product_kb.split_sentences(answer):
        words = _content_words(sentence)
        if words and len(words & vocabulary) / len(words) < min_overlap:
            return False
    return True


def llm_answer(provider, question: str, history: list[dict[str, str]], hits: list[product_kb.Hit],
               personal: dict[str, Any], threshold: float = ANSWER_THRESHOLD) -> tuple[ToolResult | None, dict[str, Any]]:
    """Ask the provider for an answer grounded in the excerpts. Returns (result or None, fact-check record)."""
    import json

    from backend.services.llm.base import LLMError
    from backend.services.llm_privacy import find_personal_data, scrub_personal

    chosen = supporting_hits(hits, threshold)
    record: dict[str, Any] = {"llm_used": False, "checked": 0, "accepted": 0, "rejected": 0, "warnings": []}
    payload = {
        "question": scrub_personal(question, personal)[:1000],
        "earlier_conversation": [{"question": scrub_personal(t["question"], personal)[:500],
                                  "answer": scrub_personal(t["answer"], personal)[:800]} for t in history],
        "excerpts": [{"id": h.chunk.id, "title": f"{h.chunk.document} - {h.chunk.heading}", "text": h.chunk.text}
                     for h in chosen],
    }
    leftovers = find_personal_data(json.dumps(payload, ensure_ascii=False), personal)
    if leftovers:
        record["warnings"].append({"code": "llm_blocked_personal_data",
                                   "detail": "The question still contained personal details, so it was not sent."})
        return None, record
    try:
        reply = provider.complete_json(PRODUCT_SYSTEM, json.dumps(payload, ensure_ascii=False))
    except LLMError as exc:
        record["warnings"].append({"code": "llm_unavailable", "detail": str(exc)})
        return None, record
    record["llm_used"], record["checked"] = True, 1

    answer = reply.get("answer") if isinstance(reply, dict) else None
    cited = reply.get("cited") if isinstance(reply, dict) else None
    by_id = {h.chunk.id: h.chunk for h in chosen}
    valid = (isinstance(answer, str) and 0 < len(answer.strip()) <= 1200 and isinstance(cited, list) and cited
             and all(isinstance(c, str) and c in by_id for c in cited))
    if not valid or not grounded(answer, [by_id[c] for c in cited]) or find_personal_data(answer, personal):
        record["rejected"] = 1
        record["warnings"].append({"code": "llm_unverified",
                                   "detail": "The AI answer was not supported by the product guide, so the standard "
                                             "answer is shown."})
        return None, record
    record["accepted"] = 1
    result = ToolResult(status="ok")
    result.add(answer.strip(), *[_source(by_id[c]) for c in dict.fromkeys(cited)])
    return result, record
