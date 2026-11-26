
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.database import get_db
from backend.models import (
    Internship,
    InternshipSkill,
    InterviewAnswer,
    InterviewQuestion,
    InterviewSession,
    Resume,
    User,
)
from backend.schemas.interview_schema import (
    AnswerOut,
    AnswerRequest,
    CreateSessionRequest,
    PreviewQuestion,
    ProgressOut,
    QuestionOut,
    SessionListItem,
    SessionOut,
)
from backend.services.answer_evaluator import label_for
from backend.services.fact_base import NoExtractionError, build_fact_base
from backend.services.interview_generator import GenerationRequest, generate_questions
from backend.services.interview_service import (
    SessionClosedError,
    complete_session,
    create_session,
    progress,
    submit_answer,
)
from backend.services.llm import get_llm_provider
from backend.services.matching_agent import is_eligible
from backend.services.question_bank import bank_info
from backend.utils.dependencies import get_current_user


router = APIRouter(prefix="/interviews", tags=["Interview Preparation"])


# ============================================================
# HELPERS
# ============================================================

def owned_resume(db: Session, resume_id: int, user: User) -> Resume:
    resume = db.scalar(select(Resume).where(Resume.resume_id == resume_id, Resume.user_id == user.user_id))
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return resume


def available_internship(db: Session, internship_id: int | None) -> Internship | None:
    if internship_id is None:
        return None
    internship = db.scalar(
        select(Internship).where(Internship.internship_id == internship_id)
        .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
    )
    if internship is None or not is_eligible(internship):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internship not found")
    return internship


def facts_or_422(db: Session, resume: Resume):
    try:
        return build_fact_base(db, resume)
    except NoExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))


def llm_provider(use_llm: bool, consent: bool):
    if not use_llm:
        return None
    if not consent:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="AI assistance requires llm_consent=true after showing the privacy disclosure "
                   "from GET /documents/llm-status.")
    provider = get_llm_provider()
    if provider is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="AI assistance is not configured on this server.")
    return provider


def owned_session(db: Session, session_id: int, user: User) -> InterviewSession:
    session = db.scalar(
        select(InterviewSession)
        .where(InterviewSession.session_id == session_id, InterviewSession.user_id == user.user_id)
        .options(selectinload(InterviewSession.questions).selectinload(InterviewQuestion.answers))
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview session not found")
    return session


def session_question(session: InterviewSession, question_id: int) -> InterviewQuestion:
    question = next((q for q in session.questions if q.question_id == question_id), None)
    if question is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Question not found")
    return question


def question_out(session: InterviewSession, q: InterviewQuestion) -> QuestionOut:
    visible = session.mode != "mock" or q.answered_at is not None or q.revealed_at is not None
    context = q.context or {}
    return QuestionOut(
        question_id=q.question_id, position=q.position, category=q.category, difficulty=q.difficulty,
        text=q.question_text, skill=context.get("skill"), skill_status=context.get("skill_status"),
        source_fact_ids=q.source_fact_ids or [], time_limit_seconds=q.time_limit_seconds,
        answered=q.answered_at is not None, attempts=len(q.answers), latest_score=q.score,
        latest_feedback=q.feedback, evaluation=q.evaluation, revealed=q.revealed_at is not None,
        key_points=[p["point"] for p in (q.key_points or [])] if visible else None,
        explanation=q.explanation if visible else None,
        suggested_answer=q.suggested_answer if visible else None,
    )


def session_out(session: InterviewSession) -> SessionOut:
    return SessionOut(
        session_id=session.session_id, title=session.title, mode=session.mode, status=session.status,
        resume_id=session.resume_id, internship_id=session.internship_id, difficulty=session.difficulty,
        question_mix=session.question_mix, generation_method=session.generation_method,
        total_questions=session.total_questions, answered_count=session.answered_count,
        score=session.score, summary=session.summary, notices=(session.summary or {}).get("notices", []),
        started_at=session.started_at,
        completed_at=session.completed_at, questions=[question_out(session, q) for q in session.questions],
    )


def answer_out(answer: InterviewAnswer) -> AnswerOut:
    return AnswerOut(
        answer_id=answer.answer_id, question_id=answer.question_id, attempt=answer.attempt,
        answer_text=answer.answer_text, time_taken_seconds=answer.time_taken_seconds,
        score=answer.score, label=label_for(answer.score), evaluation=answer.evaluation,
        feedback=answer.feedback, feedback_source=answer.feedback_source, created_at=answer.created_at,
    )


# ============================================================
# QUESTION BANK INFO AND PREVIEW
# ============================================================

@router.get("/question-bank/version")
def question_bank_version(current_user: User = Depends(get_current_user)):
    return bank_info()


@router.get("/questions/preview", response_model=list[PreviewQuestion])
def preview_questions(
    resume_id: int,
    internship_id: int | None = None,
    technical: int = Query(default=3, ge=0, le=10),
    project: int = Query(default=2, ge=0, le=5),
    behavioral: int = Query(default=2, ge=0, le=5),
    internship: int = Query(default=1, ge=0, le=5),
    difficulty: str = Query(default="mixed", pattern="^(mixed|easy|medium|hard)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not 1 <= technical + project + behavioral + internship <= 15:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="The question mix must contain 1-15 questions")
    resume = owned_resume(db, resume_id, current_user)
    record = available_internship(db, internship_id)
    candidate = facts_or_422(db, resume)
    specs = generate_questions(candidate, record, GenerationRequest(
        mix={"technical": technical, "project": project, "behavioral": behavioral, "internship": internship},
        difficulty=difficulty, seed=0))
    return [PreviewQuestion(category=q["category"], difficulty=q["difficulty"], text=q["text"],
                            skill=q.get("skill"), skill_status=(q.get("context") or {}).get("skill_status"),
                            source_fact_ids=q.get("source_fact_ids") or []) for q in specs]


# ============================================================
# SESSIONS
# ============================================================

@router.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_interview_session(
    request: CreateSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    resume = owned_resume(db, request.resume_id, current_user)
    internship = available_internship(db, request.internship_id)
    provider = llm_provider(request.use_llm, request.llm_consent)
    candidate = facts_or_422(db, resume)
    role = None
    if request.target_role:
        from backend.services import career_tracks
        role = career_tracks.get_track(request.target_role)
        if role is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown target role")

    session, _ = create_session(
        db, current_user.user_id, resume, internship, candidate, request.mode,
        request.mix.model_dump(), request.difficulty, request.time_limit_seconds, provider, role,
    )
    return session_out(owned_session(db, session.session_id, current_user))


@router.get("/sessions", response_model=list[SessionListItem])
def list_sessions(
    status_filter: str | None = Query(default=None, alias="status",
                                      pattern="^(started|in_progress|completed|abandoned)$"),
    internship_id: int | None = None,
    resume_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (select(InterviewSession).where(InterviewSession.user_id == current_user.user_id)
             .order_by(InterviewSession.started_at.desc(), InterviewSession.session_id.desc()))
    if status_filter:
        query = query.where(InterviewSession.status == status_filter)
    if internship_id is not None:
        query = query.where(InterviewSession.internship_id == internship_id)
    if resume_id is not None:
        query = query.where(InterviewSession.resume_id == resume_id)
    return [SessionListItem(
        session_id=s.session_id, title=s.title, mode=s.mode, status=s.status, internship_id=s.internship_id,
        resume_id=s.resume_id, total_questions=s.total_questions, answered_count=s.answered_count,
        score=s.score, started_at=s.started_at, completed_at=s.completed_at) for s in db.scalars(query)]


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user)):
    return session_out(owned_session(db, session_id, current_user))


@router.post("/sessions/{session_id}/questions/{question_id}/reveal", response_model=QuestionOut)
def reveal_answer(session_id: int, question_id: int, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    session = owned_session(db, session_id, current_user)
    question = session_question(session, question_id)
    if question.revealed_at is None:
        question.revealed_at = datetime.now(timezone.utc)
        db.commit()
    return question_out(session, question)


@router.post("/sessions/{session_id}/questions/{question_id}/answers",
             response_model=AnswerOut, status_code=status.HTTP_201_CREATED)
def answer_question(
    session_id: int,
    question_id: int,
    request: AnswerRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    session = owned_session(db, session_id, current_user)
    question = session_question(session, question_id)
    if session.status in ("completed", "abandoned"):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This interview session is closed.")
    provider = llm_provider(request.use_llm_feedback, request.llm_consent)

    resume = db.get(Resume, session.resume_id) if session.resume_id else None
    try:
        candidate = build_fact_base(db, resume) if resume else None
    except NoExtractionError:
        candidate = None

    try:
        answer = submit_answer(db, session, question, request.answer_text, request.time_taken_seconds,
                               candidate, provider)
    except SessionClosedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return answer_out(answer)


@router.get("/sessions/{session_id}/questions/{question_id}/answers", response_model=list[AnswerOut])
def list_answers(session_id: int, question_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    session = owned_session(db, session_id, current_user)
    return [answer_out(a) for a in session_question(session, question_id).answers]


@router.post("/sessions/{session_id}/complete", response_model=SessionOut)
def complete(session_id: int, db: Session = Depends(get_db),
             current_user: User = Depends(get_current_user)):
    session = owned_session(db, session_id, current_user)
    try:
        complete_session(db, session)
    except SessionClosedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    return session_out(owned_session(db, session_id, current_user))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_session(session_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    session = owned_session(db, session_id, current_user)
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/progress", response_model=ProgressOut)
def get_progress(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return progress(db, current_user.user_id)
