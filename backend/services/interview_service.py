"""Interview sessions: creation, answers, completion and progress (Phase 6)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    Internship,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    Resume,
    Skill,
    SkillGapRecommendation,
)
from backend.services.answer_evaluator import default_semantic_matcher, evaluate_answer, label_for
from backend.services.document_common import FactCheckLog, call_llm, context_texts
from backend.services.fact_base import CandidateFacts
from backend.services.llm_privacy import REMOVED, personal_details, scrub_personal
from backend.services.fact_check import check_statement, skill_mentions
from backend.services.interview_generator import GenerationRequest, generate_questions, generation_notices
from backend.services.internship_text import internship_skill_names
from backend.services.llm.base import LLMProvider

MAX_LLM_QUESTIONS = 2
MAX_LLM_FEEDBACK_CHARS = 1500


class SessionClosedError(ValueError):
    """The session is completed or abandoned."""


def session_seed(user_id: int, resume_id: int, internship_id: int | None, sequence: int) -> int:
    digest = hashlib.sha256(f"{user_id}:{resume_id}:{internship_id}:{sequence}".encode()).hexdigest()
    return int(digest[:12], 16)


def recent_behavioral_ids(db: Session, user_id: int, sessions: int = 3) -> frozenset[str]:
    recent = db.scalars(
        select(InterviewSession.session_id).where(InterviewSession.user_id == user_id)
        .order_by(InterviewSession.started_at.desc()).limit(sessions)
    ).all()
    if not recent:
        return frozenset()
    return frozenset(i for i in db.scalars(
        select(InterviewQuestion.bank_question_id).where(
            InterviewQuestion.session_id.in_(recent), InterviewQuestion.category == "behavioral")
    ) if i)


# ------------------------------------------------------------------
# Optional LLM-tailored questions
# ------------------------------------------------------------------

QUESTION_SYSTEM = (
    "You write interview questions for an internship candidate. STRICT RULES: use ONLY the candidate "
    "facts and internship details provided; never assume experience, employers, numbers or skills that "
    "are not in the cited facts; every question must cite the fact ids it is based on (or 'internship'). "
    'Return {"questions": [{"category": "project"|"internship", "text": str, "fact_ids": [str]}]} '
    f"with at most {MAX_LLM_QUESTIONS} questions. Respond with JSON only."
)


def llm_tailored_questions(
    provider: LLMProvider, candidate: CandidateFacts, internship: Internship | None, log: FactCheckLog,
    existing: set[str],
) -> list[dict[str, Any]]:
    from backend.services.document_common import internship_context, ranked_facts
    from backend.services.fact_base import Fact

    facts = candidate.of_kind("experience", "internship", "project")
    if internship is not None:
        facts = ranked_facts(facts, internship)
    payload = {
        "internship": internship_context(internship) if internship else None,
        "candidate": {"skills": candidate.skills,
                      "facts": [{"id": f.id, "kind": f.kind, "text": f.text} for f in facts[:4]]},
    }
    result = call_llm(provider, QUESTION_SYSTEM, payload, candidate, log)
    if not result:
        return []

    pseudo = {"internship": Fact("internship", "internship_record",
                                 " ".join(context_texts(internship)) if internship else "")}
    by_id = {**candidate.by_id, **pseudo}
    allowed_skills = list(candidate.skills)
    if internship is not None:
        required, preferred = internship_skill_names(internship)
        allowed_skills += [*required, *preferred]

    accepted = []
    for index, item in enumerate(result.get("questions") or []):
        log.checked += 1
        location = f"llm question {index + 1}"
        if not isinstance(item, dict) or item.get("category") not in ("project", "internship"):
            log.rejected.append({"location": location, "text": str(item)[:200],
                                 "problems": [{"code": "invalid_output", "detail": "Unsupported category."}]})
            continue
        text, fact_ids = item.get("text"), item.get("fact_ids")
        if not isinstance(text, str) or not 15 <= len(text) <= 300 or not text.rstrip().endswith("?"):
            log.rejected.append({"location": location, "text": str(text)[:200],
                                 "problems": [{"code": "invalid_output", "detail": "Not a well-formed question."}]})
            continue
        if REMOVED in text:
            log.rejected.append({"location": location, "text": text[:200],
                                 "problems": [{"code": "privacy_placeholder",
                                               "detail": "Question repeats a removed personal detail."}]})
            continue
        if not isinstance(fact_ids, list) or not fact_ids:
            log.rejected.append({"location": location, "text": text[:200],
                                 "problems": [{"code": "no_citation", "detail": "Question cites no facts."}]})
            continue
        problems = check_statement(text, fact_ids, by_id, allowed_skills,
                                   context_texts(internship) if internship else [])
        if problems or text in existing:
            log.rejected.append({"location": location, "text": text[:200],
                                 "problems": problems or [{"code": "duplicate", "detail": "Duplicate question."}]})
            continue
        log.llm_accepted += 1
        cited_skills = sorted(skill_mentions(" ".join(by_id[f].text for f in fact_ids if f in by_id)))
        accepted.append({
            "category": item["category"],
            "text": text.strip(),
            "difficulty": "medium",
            "skill": None,
            "bank_question_id": None,
            "key_points": [
                {"point": "Answer the question specifically", "keywords": [w.lower() for w in cited_skills] or ["i "]},
                {"point": "Explain your own role and actions", "keywords": ["i ", "my role", "i built", "responsib"]},
                {"point": "Share the result or what you learned", "keywords": ["result", "outcome", "learn", "improv"]},
            ],
            "explanation": "AI-suggested question grounded in your resume or the internship.",
            "source_fact_ids": [f for f in fact_ids if f != "internship"],
            "context": {"fact_skills": cited_skills, "generated_by": "llm", "kind": "llm",
                        "title": internship.title if internship else None,
                        "company": internship.company if internship else None},
            "suggested_answer": {"type": "outline", "points": [
                "Context", "Your role and actions", "Outcome or what you learned"]},
        })
    return accepted[:MAX_LLM_QUESTIONS]


# ------------------------------------------------------------------
# Create
# ------------------------------------------------------------------

def create_session(
    db: Session,
    user_id: int,
    resume: Resume,
    internship: Internship | None,
    candidate: CandidateFacts,
    mode: str,
    mix: dict[str, int],
    difficulty: str,
    time_limit_seconds: int | None,
    provider: LLMProvider | None,
) -> tuple[InterviewSession, FactCheckLog]:
    sequence = db.scalar(select(func.count()).select_from(InterviewSession)
                         .where(InterviewSession.user_id == user_id)) or 0
    request = GenerationRequest(
        mix=mix, difficulty=difficulty,
        seed=session_seed(user_id, resume.resume_id, internship.internship_id if internship else None, sequence),
        exclude_behavioral=recent_behavioral_ids(db, user_id),
    )
    specs = generate_questions(candidate, internship, request)
    notices = generation_notices(candidate, internship, request, specs)

    log = FactCheckLog()
    if provider is not None:
        specs += llm_tailored_questions(provider, candidate, internship, log, {s["text"] for s in specs})

    skill_ids = {s.name.casefold(): s.skill_id for s in db.scalars(
        select(Skill).where(func.lower(Skill.name).in_([q["skill"].casefold() for q in specs if q.get("skill")]))
    )} if any(q.get("skill") for q in specs) else {}

    title = (f"{'Mock' if mode == 'mock' else 'Practice'} interview - "
             + (f"{internship.title} at {internship.company}" if internship else "general"))[:255]
    session = InterviewSession(
        user_id=user_id, resume_id=resume.resume_id,
        internship_id=internship.internship_id if internship else None,
        status="started", mode=mode, title=title, question_mix=mix, difficulty=difficulty,
        generation_method="llm" if log.llm_accepted else "deterministic",
        llm_provider=provider.name if (provider and log.llm_accepted) else None,
        llm_model=provider.model if (provider and log.llm_accepted) else None,
        total_questions=len(specs), answered_count=0,
        summary={"generation": log.as_dict(), "requested_questions": sum(int(v) for v in mix.values()),
                 "notices": notices},
    )
    db.add(session)
    db.flush()

    for position, spec in enumerate(specs, start=1):
        db.add(InterviewQuestion(
            session_id=session.session_id,
            question_text=spec["text"],
            question_type=spec["category"],
            category=spec["category"],
            position=position,
            skill_id=skill_ids.get(spec["skill"].casefold()) if spec.get("skill") else None,
            bank_question_id=spec.get("bank_question_id"),
            source_fact_ids=spec.get("source_fact_ids") or [],
            difficulty=spec["difficulty"],
            key_points=spec["key_points"],
            explanation=spec["explanation"],
            suggested_answer=spec["suggested_answer"],
            context={**(spec.get("context") or {}), "skill": spec.get("skill")},
            time_limit_seconds=time_limit_seconds if mode == "mock" else None,
        ))
    db.commit()
    db.refresh(session)
    return session, log


def question_spec(question: InterviewQuestion) -> dict[str, Any]:
    return {
        "category": question.category,
        "key_points": question.key_points or [],
        "context": question.context or {},
        "skill": (question.context or {}).get("skill"),
    }


# ------------------------------------------------------------------
# Answer
# ------------------------------------------------------------------

FEEDBACK_SYSTEM = (
    "You are an interview coach. Give constructive, specific feedback on the candidate's answer to the "
    "question, based only on the question, its key points and the answer. Do not invent facts about the "
    'candidate. Return {"feedback": str, "tips": [str]} as JSON only, at most 120 words.'
)


def submit_answer(
    db: Session,
    session: InterviewSession,
    question: InterviewQuestion,
    answer_text: str,
    time_taken_seconds: int | None,
    candidate: CandidateFacts | None,
    provider: LLMProvider | None,
) -> InterviewAnswer:
    if session.status in ("completed", "abandoned"):
        raise SessionClosedError("This interview session is closed.")

    skills = candidate.skills if candidate else []
    evaluation = evaluate_answer(question_spec(question), answer_text, skills, default_semantic_matcher())
    feedback, source = evaluation["feedback"], "rubric"

    if provider is not None and candidate is None:
        evaluation["llm_warnings"] = [{
            "code": "resume_unavailable",
            "detail": "AI feedback needs the resume this session was created from, which has been deleted or "
                      "has no parsed content. Rubric feedback is shown instead."}]
    elif provider is not None:
        log = FactCheckLog()
        payload = {
            "question": question.question_text,
            "category": question.category,
            "key_points": [p["point"] for p in (question.key_points or [])],
            # Free text written by the student: scrub before call_llm's checks (which also scrub and
            # re-check every candidate string and refuse to send if anything personal remains).
            "answer": scrub_personal(answer_text, personal_details(candidate))[:5000],
        }
        result = call_llm(provider, FEEDBACK_SYSTEM, payload, candidate, log)
        text = result.get("feedback") if isinstance(result, dict) else None
        tips = result.get("tips") if isinstance(result, dict) else None
        if isinstance(text, str) and text.strip() and len(text) <= MAX_LLM_FEEDBACK_CHARS:
            extra = [t for t in tips if isinstance(t, str)][:5] if isinstance(tips, list) else []
            feedback = "\n".join([text.strip(), *extra,
                                  f"Rubric score: {evaluation['score']}/100 ({evaluation['label']})."])
            source = "llm"
        else:
            evaluation["llm_warnings"] = log.warnings or [{"code": "llm_invalid",
                                                           "detail": "AI feedback was unusable; rubric feedback shown."}]

    attempt = len(question.answers) + 1
    answer = InterviewAnswer(
        question_id=question.question_id, attempt=attempt, answer_text=answer_text,
        time_taken_seconds=time_taken_seconds, score=evaluation["score"],
        evaluation=evaluation, feedback=feedback, feedback_source=source,
    )
    question.answers.append(answer)

    now = datetime.now(timezone.utc)
    question.user_answer = answer_text
    question.score = evaluation["score"]
    question.feedback = feedback
    question.evaluation = evaluation
    question.answered_at = now
    if time_taken_seconds is not None and question.time_limit_seconds:
        evaluation["over_time_limit"] = time_taken_seconds > question.time_limit_seconds

    session.status = "in_progress"
    session.answered_count = sum(1 for q in session.questions if q.answered_at is not None)
    db.commit()
    db.refresh(answer)
    return answer


# ------------------------------------------------------------------
# Complete and progress
# ------------------------------------------------------------------

def complete_session(db: Session, session: InterviewSession) -> InterviewSession:
    if session.status in ("completed", "abandoned"):
        raise SessionClosedError("This interview session is already closed.")

    questions = list(session.questions)
    answered = [q for q in questions if q.score is not None]
    overall = round(sum(q.score or 0.0 for q in questions) / len(questions), 1) if questions else 0.0

    by_category: dict[str, list[float]] = {}
    for q in answered:
        by_category.setdefault(q.category, []).append(q.score)
    category_avg = {c: round(mean(v), 1) for c, v in by_category.items()}

    strengths = [f"{q.category}: {q.question_text}" for q in answered if q.score >= 65][:5]
    improvements = []
    for q in answered:
        if q.score < 65:
            missed = [p["point"] for p in (q.evaluation or {}).get("missed_points", [])][:2]
            improvements.append({"question": q.question_text, "score": q.score,
                                 "focus": missed or (q.evaluation or {}).get("tips", [])[:2]})

    question_skills = {(q.context or {}).get("skill") for q in questions if (q.context or {}).get("skill")}
    related = []
    if session.resume_id and question_skills:
        for rec in db.scalars(select(SkillGapRecommendation).where(
                SkillGapRecommendation.resume_id == session.resume_id,
                SkillGapRecommendation.is_current.is_(True))):
            if rec.skill.name in question_skills:
                related.append({"recommendation_id": rec.recommendation_id, "skill": rec.skill.name,
                                "status": rec.status, "priority_score": rec.priority_score})

    session.status = "completed"
    session.completed_at = datetime.now(timezone.utc)
    session.score = overall
    session.summary = {
        **(session.summary or {}),
        "overall_score": overall,
        "label": label_for(overall),
        "answered": len(answered),
        "total": len(questions),
        "unanswered_count_as_zero": True,
        "average_answered_score": round(mean(q.score for q in answered), 1) if answered else None,
        "by_category": category_avg,
        "strengths": strengths,
        "improvements": improvements[:6],
        "related_skill_gaps": related,
    }
    db.commit()
    db.refresh(session)
    return session


def progress(db: Session, user_id: int) -> dict[str, Any]:
    sessions = db.scalars(select(InterviewSession).where(InterviewSession.user_id == user_id)
                          .order_by(InterviewSession.started_at)).all()
    completed = [s for s in sessions if s.status == "completed"]

    questions = db.scalars(
        select(InterviewQuestion).join(InterviewSession)
        .where(InterviewSession.user_id == user_id, InterviewQuestion.score.is_not(None))
    ).all()
    by_category: dict[str, list[float]] = {}
    by_skill: dict[str, list[float]] = {}
    for q in questions:
        by_category.setdefault(q.category, []).append(q.score)
        skill = (q.context or {}).get("skill")
        if skill and q.category == "technical":
            by_skill.setdefault(skill, []).append(q.score)

    improvements = []
    for q in questions:
        if len(q.answers) >= 2:
            improvements.append(q.answers[-1].score - q.answers[0].score)

    return {
        "sessions_total": len(sessions),
        "sessions_completed": len(completed),
        "questions_answered": len(questions),
        "answers_total": sum(len(q.answers) for q in questions),
        "average_score": round(mean(q.score for q in questions), 1) if questions else None,
        "by_category": {c: round(mean(v), 1) for c, v in sorted(by_category.items())},
        "by_skill": {s: round(mean(v), 1) for s, v in sorted(by_skill.items())},
        "retry_improvement": {"questions_retried": len(improvements),
                              "average_change": round(mean(improvements), 1) if improvements else None},
        "trend": [{"session_id": s.session_id, "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                   "score": s.score} for s in completed][-10:],
    }


__all__ = ["create_session", "submit_answer", "complete_session", "progress", "SessionClosedError",
           "question_spec", "json"]
