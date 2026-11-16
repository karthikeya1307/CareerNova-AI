"""Read-only tools: gather facts with traceable sources from Phase 1-7 services.

Rules:
* every tool receives the authenticated ``user_id`` and only reads that
  student's rows (internships are public knowledge-base records);
* nothing here writes or recalculates stored Phase 1-7 results: match
  explanations come from stored match runs, recommendations from stored
  skill-gap rows, statuses from the application tables;
* contact details, notes and reminder descriptions are never put in facts.
"""

from __future__ import annotations

import re

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from backend.models import (
    Application,
    GeneratedDocument,
    Internship,
    InternshipSkill,
    InterviewSession,
    MatchResult,
    Resume,
    SavedInternship,
    SkillGapRecommendation,
)
from backend.services import application_service as apps
from backend.services.application_dashboard import dashboard as application_dashboard
from backend.services.assistant.facts import ResultItem, Source, ToolResult, action, fmt_date, fmt_datetime
from backend.services.ats import ats_report
from backend.services.candidate_profile import latest_completed_extraction
from backend.services.fact_base import NoExtractionError, build_fact_base
from backend.services.internship_text import internship_skill_names
from backend.services.interview_service import progress as interview_progress
from backend.services.learning_plans import plan_for, plans_version
from backend.services.matching_agent import is_eligible
from backend.services.question_bank import questions_for_skill
from backend.services.skill_gap import analyse_internship, candidate_skill_names

MAX_LIST = 5
SEARCH_POOL = 25


def _fallback_errors() -> tuple[type[BaseException], ...]:
    from backend.services.embeddings import EmbeddingError
    from backend.services.vector_index import VectorIndexError
    return (VectorIndexError, EmbeddingError)


SEARCH_FALLBACK_ERRORS = _fallback_errors()


# ------------------------------------------------------------------
# Source helpers
# ------------------------------------------------------------------

def internship_label(internship: Internship) -> str:
    return f"{internship.title} at {internship.company}"


def internship_source(internship: Internship) -> Source:
    return Source("internship", str(internship.internship_id), internship_label(internship))


def resume_source(resume: Resume) -> Source:
    return Source("resume", str(resume.resume_id), f"Resume: {resume.filename}")


def application_label(application: Application) -> str:
    return f"{application.title} at {application.company_name}"


def application_ai_label(application: Application) -> str:
    """Label for AI requests: knowledge-base labels for internal applications; external applications'
    company and title were typed by the student and are never sent."""
    if application.source == "internal":
        return application_label(application)
    return "an external application"


def application_source(application: Application) -> Source:
    return Source("application", str(application.application_id), application_label(application))


def load_internship(db: Session, internship_id: int) -> Internship | None:
    return db.scalar(select(Internship).where(Internship.internship_id == internship_id)
                     .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill)))


def closed_reason(internship: Internship) -> str | None:
    """Why an internship is not a current opportunity (None when it is active with an open deadline)."""
    if not internship.is_active:
        return "it has been deactivated"
    if apps.deadline_passed(internship):
        return f"its application deadline ({fmt_date(internship.deadline)}) has passed"
    return None


def add_closed_note(result: ToolResult, internship: Internship) -> bool:
    """State clearly (as a sourced fact) that an internship is no longer open. Returns True if closed."""
    reason = closed_reason(internship)
    if reason is None:
        return False
    result.add(f"This internship is no longer open: {reason}.", internship_source(internship))
    result.warnings.append({"code": "internship_closed",
                            "detail": f"{internship_label(internship)} is no longer open: {reason}."})
    return True


def needs_resume(result: ToolResult | None = None) -> ToolResult:
    result = result or ToolResult()
    result.status = "needs_resume"
    result.intro = ("I need a parsed resume for that. Upload a resume (or wait for it to finish processing) "
                    "and ask again.")
    result.actions.append(action("Upload a resume", "POST", "/resumes/upload"))
    return result


def unavailable_internship(result: ToolResult, internship_id: int | str) -> ToolResult:
    result.status = "not_found"
    result.intro = (f"Internship {internship_id} is no longer available (it may have been removed, closed or "
                    "deactivated), so I can't give details for it.")
    return result


# ------------------------------------------------------------------
# Resume / profile
# ------------------------------------------------------------------

def choose_resume(db: Session, user_id: int, preferred_resume_id: int | None) -> Resume | None:
    """The conversation's resume if it still exists and is parsed, else the latest parsed resume."""
    if preferred_resume_id:
        resume = db.scalar(select(Resume).where(Resume.resume_id == preferred_resume_id,
                                                Resume.user_id == user_id))
        if resume is not None and latest_completed_extraction(db, resume.resume_id) is not None:
            return resume
    for resume in db.scalars(select(Resume).where(Resume.user_id == user_id)
                             .order_by(Resume.uploaded_at.desc(), Resume.resume_id.desc())):
        if latest_completed_extraction(db, resume.resume_id) is not None:
            return resume
    return None


def profile_summary(db: Session, user_id: int, resume: Resume | None) -> ToolResult:
    result = ToolResult(intro="Here is what your resume shows:")
    if resume is None:
        return needs_resume(result)
    try:
        facts = build_fact_base(db, resume)
    except NoExtractionError:
        return needs_resume(result)
    result.uses_resume_id = resume.resume_id
    src = resume_source(resume)
    if facts.skills:
        result.add(f"Skills on your resume: {', '.join(facts.skills)}.", src,
                   polarity={s: "have" for s in facts.skills})
    else:
        result.add("No skills were found on your resume.", src)
    if facts.degree:
        result.add(f"Degree: {facts.degree}.", src)
    for kind, label in (("experience", "Experience"), ("internship", "Internship"), ("project", "Project")):
        for fact in facts.of_kind(kind)[:3]:
            result.add(f"{label}: {fact.title}.",
                       Source("resume_fact", f"{resume.resume_id}:{fact.id}", fact.title))
    result.actions.append(action("Find internships that match your resume", "POST",
                                 f"/matches/resumes/{resume.resume_id}", requires_confirmation=False))
    return result


# ------------------------------------------------------------------
# Internships (Phase 2 knowledge base + RAG)
# ------------------------------------------------------------------

def _keyword_search(db: Session, terms: list[str], limit: int) -> list[Internship]:
    """Fallback when the semantic index is unavailable: open internships matching any term."""
    query = select(Internship).where(Internship.is_active.is_(True)).options(
        selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))
    words = [t for t in terms if len(t) >= 3][:8]
    if words:
        conditions = []
        for word in words:
            pattern = f"%{apps.escape_like(word)}%"
            conditions += [Internship.title.ilike(pattern, escape="\\"),
                           Internship.company.ilike(pattern, escape="\\"),
                           Internship.domain.ilike(pattern, escape="\\"),
                           Internship.description.ilike(pattern, escape="\\")]
        query = query.where(or_(*conditions))
    found = [i for i in db.scalars(query.order_by(Internship.internship_id).limit(limit * 4)) if is_eligible(i)]
    return found[:limit]


def _matches_filters(internship: Internship, work_mode: str | None, location: str | None) -> bool:
    if work_mode and (internship.work_mode or "") != work_mode:
        return False
    if location and location.casefold() not in (internship.location or "").casefold():
        return False
    return True


def internship_search(db: Session, user_id: int, terms: list[str], work_mode: str | None,
                      location: str | None, raw_query: str) -> ToolResult:
    from backend.services import embeddings, vector_index

    result = ToolResult(result_kind="internship")
    method = "semantic"
    query = " ".join(terms) or raw_query
    try:
        hits = vector_index.search(db, query, SEARCH_POOL, embeddings.get_embedder())
        # Same eligibility as the keyword fallback: active AND deadline not passed.
        found = [h.internship for h in hits
                 if is_eligible(h.internship) and _matches_filters(h.internship, work_mode, location)]
    except SEARCH_FALLBACK_ERRORS:   # index not built / invalid, model unavailable: keyword fallback.
        # Database and programming errors are NOT caught here; they propagate to the route.
        method = "keyword"
        found = [i for i in _keyword_search(db, terms, SEARCH_POOL) if _matches_filters(i, work_mode, location)]
    found = found[:MAX_LIST]

    filters = ", ".join(x for x in (work_mode, location) if x)
    if not found:
        result.status = "empty"
        result.intro = ("I couldn't find open internships for that"
                        + (f" ({filters})" if filters else "") + ". Try different words or fewer filters.")
        return result
    if method == "keyword":
        result.warnings.append({"code": "semantic_search_unavailable",
                                "detail": "Semantic search is not available right now; results come from a "
                                          "keyword search."})
    result.intro = "Here are open internships that fit your request" + (f" ({filters})" if filters else "") + ":"
    saved = {r for r in db.scalars(select(SavedInternship.internship_id).where(
        SavedInternship.user_id == user_id, SavedInternship.internship_id.in_([i.internship_id for i in found])))}
    for number, internship in enumerate(found, start=1):
        bits = [x for x in (internship.location, internship.work_mode, internship.domain) if x]
        text = f"{number}. {internship_label(internship)}" + (f" ({', '.join(bits)})" if bits else "")
        text += f", deadline {fmt_date(internship.deadline)}" if internship.deadline else ""
        text += " - saved" if internship.internship_id in saved else ""
        result.add(text + ".", internship_source(internship))
        result.results.append(ResultItem("internship", str(internship.internship_id), internship_label(internship)))
    result.outro = "Ask about one of them, for example \"tell me more about the second one\"."
    return result


def internship_detail(db: Session, user_id: int, internship_id: int) -> ToolResult:
    result = ToolResult()
    internship = load_internship(db, internship_id)
    if internship is None or not internship.is_active:
        return unavailable_internship(result, internship_id)
    src = internship_source(internship)
    result.focus = ResultItem("internship", str(internship.internship_id), internship_label(internship))
    result.intro = f"Details for {internship_label(internship)}:"
    add_closed_note(result, internship)
    result.add(f"Location: {internship.location or 'not stated'}; work mode: {internship.work_mode or 'not stated'}.",
               src)
    if internship.domain:
        result.add(f"Domain: {internship.domain}.", src)
    if internship.duration_weeks:
        result.add(f"Duration: {internship.duration_weeks} weeks.", src)
    if internship.stipend_per_month is not None:
        result.add(f"Stipend: {internship.stipend_per_month} {internship.stipend_currency} per month.", src)
    result.add(f"Deadline: {fmt_date(internship.deadline)}"
               + (" (passed)." if apps.deadline_passed(internship) else "."), src)
    required, preferred = internship_skill_names(internship)
    if required:
        result.add(f"Required skills: {', '.join(required)}.", src)
    if preferred:
        result.add(f"Preferred skills: {', '.join(preferred)}.", src)
    if internship.min_education:
        result.add(f"Minimum education: {internship.min_education}.", src)

    bookmark = apps.get_bookmark(db, user_id, internship.internship_id)
    application = db.scalar(apps.active_applications(user_id).where(
        Application.internship_id == internship.internship_id))
    if application is not None:
        result.add(f"You are tracking an application for it with status {application.status}.",
                   application_source(application))
    elif bookmark is not None:
        result.add("You have saved this internship.",
                   Source("bookmark", str(bookmark.bookmark_id), internship_label(internship)))
    if bookmark is None and is_eligible(internship):
        result.actions.append(action("Save this internship", "POST",
                                     f"/applications/bookmarks/{internship.internship_id}"))
    if application is None:
        result.actions.append(action("Track an application", "POST", "/applications",
                                     {"internship_id": internship.internship_id}))
    return result


# ------------------------------------------------------------------
# Matching (Phase 3) - stored runs only
# ------------------------------------------------------------------

def _latest_run_rows(db: Session, resume: Resume) -> list[MatchResult]:
    run_id = db.scalar(select(MatchResult.run_id).where(MatchResult.resume_id == resume.resume_id,
                                                        MatchResult.user_id == resume.user_id,
                                                        MatchResult.run_id.is_not(None))
                       .order_by(MatchResult.created_at.desc(), MatchResult.match_id.desc()).limit(1))
    if run_id is None:
        return []
    return list(db.scalars(select(MatchResult).where(MatchResult.run_id == run_id)
                           .options(selectinload(MatchResult.internship)).order_by(MatchResult.rank)))


def match_source(row: MatchResult, internship: Internship) -> Source:
    return Source("match_result", str(row.match_id), f"Match: {internship_label(internship)}")


def top_matches(db: Session, user_id: int, resume: Resume | None) -> ToolResult:
    result = ToolResult(result_kind="internship")
    if resume is None:
        return needs_resume(result)
    result.uses_resume_id = resume.resume_id
    all_rows = [r for r in _latest_run_rows(db, resume) if r.internship is not None]
    if not all_rows:
        result.status = "empty"
        result.intro = "You don't have a stored match run for this resume yet."
        result.actions.append(action("Run matching for your resume", "POST", f"/matches/resumes/{resume.resume_id}"))
        return result
    # Never present a closed internship as a current opportunity (M1).
    rows = [r for r in all_rows if closed_reason(r.internship) is None][:MAX_LIST]
    hidden = sum(1 for r in all_rows if closed_reason(r.internship) is not None)
    if hidden:
        result.warnings.append({"code": "closed_matches_hidden",
                                "detail": f"{hidden} internship(s) from that match run are no longer open and "
                                          "are not shown."})
    if not rows:
        result.status = "empty"
        result.intro = ("None of the internships in your latest match run are still open. Run matching again "
                        "to find current opportunities.")
        result.actions.append(action("Run matching for your resume", "POST", f"/matches/resumes/{resume.resume_id}"))
        return result
    result.intro = (f"Your top open matches from your latest match run ({fmt_date(all_rows[0].created_at)})"
                    + (f"; {hidden} that are no longer open are not shown" if hidden else "") + ":")
    for number, row in enumerate(rows, start=1):
        internship = row.internship
        result.add(f"{number}. {internship_label(internship)}: score {round(row.score)} ({row.label}), "
                   f"rank {row.rank} in that run.",
                   match_source(row, internship), internship_source(internship))
        result.results.append(ResultItem("internship", str(internship.internship_id), internship_label(internship),
                                         {"match_id": row.match_id}))
    result.outro = "Ask \"why is the first one a good match?\" for the full explanation."
    return result


def match_explain(db: Session, user_id: int, resume: Resume | None, internship_id: int) -> ToolResult:
    result = ToolResult()
    if resume is None:
        return needs_resume(result)
    internship = load_internship(db, internship_id)
    if internship is None:
        return unavailable_internship(result, internship_id)
    result.uses_resume_id = resume.resume_id
    result.focus = ResultItem("internship", str(internship.internship_id), internship_label(internship))
    row = db.scalar(select(MatchResult).where(MatchResult.user_id == user_id,
                                              MatchResult.resume_id == resume.resume_id,
                                              MatchResult.internship_id == internship.internship_id,
                                              MatchResult.run_id.is_not(None))
                    .order_by(MatchResult.created_at.desc(), MatchResult.match_id.desc()).limit(1))
    if row is None:
        result.status = "empty"
        result.intro = (f"There is no stored match result for {internship_label(internship)} with this resume. "
                        "Run matching to get a scored explanation.")
        result.actions.append(action("Run matching for your resume", "POST", f"/matches/resumes/{resume.resume_id}"))
        return result
    src = match_source(row, internship)
    breakdown = row.breakdown or {}
    if closed_reason(internship) is not None:
        result.intro = (f"{internship_label(internship)} is no longer open. For reference, this is the stored "
                        f"explanation from your match run of {fmt_date(row.created_at)}:")
        add_closed_note(result, internship)
    else:
        result.intro = (f"Why {internship_label(internship)} matches you "
                        f"(stored match run of {fmt_date(row.created_at)}):")
    result.add(f"Overall score: {round(row.score)} out of 100 ({row.label}).", src, internship_source(internship))
    for component in breakdown.get("components", []):
        result.add(f"{component['name'].capitalize()}: {round(component['score'] * 100)}% "
                   f"(weight {round(component['weight'] * 100)}%) - {component['detail']}", src)
    matched = breakdown.get("matched_required_skills") or []
    missing = breakdown.get("missing_required_skills") or []
    if matched:
        result.add(f"Required skills you have: {', '.join(matched)}.", src, polarity={s: "have" for s in matched})
    if missing:
        result.add(f"Required skills you are missing: {', '.join(missing)}.", src,
                   polarity={s: "missing" for s in missing})
    for cap in breakdown.get("caps_applied") or []:
        result.add(f"Score limit applied: {cap}.", src)
    result.actions.append(action("See the skill gaps for this internship", "GET",
                                 f"/skill-gaps/resumes/{resume.resume_id}/internships/{internship.internship_id}",
                                 requires_confirmation=False))
    return result


# ------------------------------------------------------------------
# Skill gaps and learning (Phase 4)
# ------------------------------------------------------------------

def skill_gap(db: Session, user_id: int, resume: Resume | None, internship_id: int | None) -> ToolResult:
    result = ToolResult()
    if resume is None:
        return needs_resume(result)
    result.uses_resume_id = resume.resume_id
    if internship_id is not None:
        internship = load_internship(db, internship_id)
        if internship is None or not internship.is_active:
            return unavailable_internship(result, internship_id)
        report = analyse_internship(candidate_skill_names(db, resume.resume_id), internship)
        src, rsrc = internship_source(internship), resume_source(resume)
        result.focus = ResultItem("internship", str(internship.internship_id), internship_label(internship))
        result.intro = f"Skill gaps for {internship_label(internship)}:"
        add_closed_note(result, internship)
        summary = report["summary"]
        result.add(f"You have {summary['required_matched']} of {summary['required_total']} required skills.",
                   src, rsrc)
        for key, word in (("missing", "Missing"), ("partial", "Partly covered (related skill)"),
                          ("matched", "Already have")):
            skills = [item["skill"] for item in report[key]]
            if skills:
                polarity = {"missing": "missing", "partial": "partial", "matched": "have"}[key]
                result.add(f"{word}: {', '.join(skills)}.", src, rsrc, polarity={s: polarity for s in skills})
        order = report["learning_order"]
        if order:
            result.add(f"Suggested learning order: {', '.join(order)}.",
                       Source("learning_plan", order[0], f"Learning plans {plans_version()}"))
            result.result_kind = "skill"
            result.results = [ResultItem("skill", s, s) for s in order[:MAX_LIST]]
        return result

    rows = list(db.scalars(select(SkillGapRecommendation).where(
        SkillGapRecommendation.user_id == user_id, SkillGapRecommendation.resume_id == resume.resume_id,
        SkillGapRecommendation.is_current.is_(True), SkillGapRecommendation.status != "completed")
        .options(selectinload(SkillGapRecommendation.skill))
        .order_by(SkillGapRecommendation.priority_score.desc().nulls_last(),
                  SkillGapRecommendation.recommendation_id)).all())[:MAX_LIST]
    if not rows:
        result.status = "empty"
        result.intro = "You don't have stored skill-gap recommendations for this resume yet."
        result.actions.append(action("Generate skill-gap recommendations", "POST",
                                     f"/skill-gaps/resumes/{resume.resume_id}"))
        return result
    result.intro = "Your highest-priority skills to work on:"
    result.result_kind = "skill"
    for number, rec in enumerate(rows, start=1):
        text = f"{number}. {rec.skill.name}: {rec.gap_level} gap"
        if rec.priority_score is not None:
            text += f", priority {round(rec.priority_score)}"
        if rec.demand_count:
            text += f", needed by {rec.demand_count} internship(s)"
        result.add(text + f", status {rec.status}.",
                   Source("skill_gap_recommendation", str(rec.recommendation_id), f"Recommendation: {rec.skill.name}"),
                   polarity={rec.skill.name: "partial" if rec.gap_level == "partial" else "missing"})
        result.results.append(ResultItem("skill", rec.skill.name, rec.skill.name,
                                         {"recommendation_id": rec.recommendation_id}))
    result.outro = "Ask \"how do I learn the first one?\" for a learning plan."
    return result


def learning_plan(db: Session, user_id: int, skill: str) -> ToolResult:
    plan = plan_for(skill)
    src = Source("learning_plan", skill, f"Learning plan: {skill} ({plans_version()})")
    result = ToolResult(intro=f"Learning plan for {skill}:")
    result.focus = ResultItem("skill", skill, skill)
    if not plan.get("curated"):
        result.warnings.append({"code": "generic_plan", "detail": "No curated plan exists for this skill yet; "
                                                                  "this is a generic outline."})
    if plan.get("level"):
        result.add(f"Level: {plan['level']}.", src)
    if plan.get("estimated_hours"):
        result.add(f"Estimated time: about {plan['estimated_hours']} hours.", src)
    if plan.get("prerequisites"):
        result.add(f"Learn first: {', '.join(plan['prerequisites'])}.", src)
    for number, topic in enumerate(plan.get("topics", [])[:6], start=1):
        result.add(f"Step {number}: {topic}.", src)
    if plan.get("project"):
        result.add(f"Practice project: {plan['project']}.", src)
    return result


# ------------------------------------------------------------------
# Documents (Phase 5) - read only; generation stays with /documents
# ------------------------------------------------------------------

def document_help(db: Session, user_id: int, resume: Resume | None, internship_id: int | None) -> ToolResult:
    result = ToolResult()
    query = select(GeneratedDocument).where(GeneratedDocument.user_id == user_id)
    internship = None
    if internship_id is not None:
        internship = load_internship(db, internship_id)
        if internship is None or not internship.is_active:
            return unavailable_internship(result, internship_id)
        query = query.where(GeneratedDocument.internship_id == internship.internship_id)
        result.focus = ResultItem("internship", str(internship.internship_id), internship_label(internship))
    documents = list(db.scalars(query.order_by(GeneratedDocument.created_at.desc()).limit(MAX_LIST)))
    result.intro = ("Resume and cover-letter help" + (f" for {internship_label(internship)}" if internship else "")
                    + ":")
    for document in documents:
        kind = "Tailored resume" if document.document_type == "resume" else "Cover letter"
        result.add(f"{kind} \"{document.title or document.document_id}\" (version {document.current_version}).",
                   Source("document", str(document.document_id), document.title or kind),
                   llm_text=f"{kind} (version {document.current_version}).")
    if internship is not None:
        if resume is None:
            return needs_resume(result)
        try:
            report = ats_report(build_fact_base(db, resume), internship)
        except NoExtractionError:
            return needs_resume(result)
        result.uses_resume_id = resume.resume_id
        add_closed_note(result, internship)
        src, rsrc = internship_source(internship), resume_source(resume)
        coverage = report["required_coverage"]
        result.add(f"Your resume covers {coverage['present']} of {coverage['total']} required skills.", src, rsrc)
        if report["missing_keywords"]:
            result.add(f"Keywords missing from your resume: {', '.join(report['missing_keywords'])}.", src, rsrc,
                       polarity={k: "missing" for k in report["missing_keywords"]})
        for suggestion in report["suggestions"][:3]:
            result.add(suggestion.rstrip(".") + ".", src, rsrc)
        body = {"resume_id": resume.resume_id, "internship_id": internship.internship_id}
        result.actions += [action("Create a tailored resume", "POST", "/documents/resume", body),
                           action("Create a cover letter", "POST", "/documents/cover-letter", body)]
    elif not documents:
        result.status = "empty"
        result.intro = ("You don't have any tailored documents yet. Tell me which internship you're applying to "
                        "(for example \"cover letter for the first one\") and I'll check your resume against it.")
    return result


# ------------------------------------------------------------------
# Interview preparation (Phase 6) - read only
# ------------------------------------------------------------------

def interview_prep(db: Session, user_id: int, skill: str | None, internship_id: int | None,
                   resume: Resume | None) -> ToolResult:
    result = ToolResult()
    if skill:
        questions = questions_for_skill(skill)
        if not questions:
            result.status = "empty"
            result.intro = f"I don't have practice questions for {skill} yet."
            return result
        result.intro = f"Practice questions for {skill}:"
        for q in questions[:3]:
            result.add(f"({q['difficulty']}) {q['question']}",
                       Source("question_bank", q["id"], f"Question bank: {skill}"))
        result.outro = "Start a practice session to get your answers scored."
    else:
        stats = interview_progress(db, user_id)
        src = Source("interview_progress", str(user_id), "Your interview practice progress")
        result.intro = "Your interview practice so far:"
        result.add(f"Sessions: {stats['sessions_total']} started, {stats['sessions_completed']} completed.", src)
        if stats["average_score"] is not None:
            result.add(f"Average answer score: {stats['average_score']} out of 100.", src)
        for category, score in stats["by_category"].items():
            result.add(f"{category.capitalize()} questions: average {score}.", src)
        for session in db.scalars(select(InterviewSession).where(InterviewSession.user_id == user_id)
                                  .order_by(InterviewSession.started_at.desc()).limit(3)):
            result.add(f"Session \"{session.title or session.session_id}\": {session.status}"
                       + (f", score {session.score}" if session.score is not None else "") + ".",
                       Source("interview_session", str(session.session_id), session.title or "Practice session"))
    if resume is not None:
        body = {"resume_id": resume.resume_id, **({"internship_id": internship_id} if internship_id else {})}
        result.actions.append(action("Start a practice interview", "POST", "/interviews/sessions", body))
    return result


# ------------------------------------------------------------------
# Applications (Phase 7) - read only
# ------------------------------------------------------------------

def _application_line(application: Application, summary: dict, number: int | None = None,
                      label: str | None = None) -> str:
    text = (f"{number}. " if number else "") + f"{label or application_label(application)}: {application.status}"
    if application.applied_at:
        text += f", applied {fmt_date(application.applied_at)}"
    if summary.get("next_interview") is not None:
        text += f", next interview {fmt_datetime(summary['next_interview'].scheduled_at)}"
    if summary.get("pending_reminders"):
        text += f", {summary['pending_reminders']} pending reminder(s)"
    return text + "."


def find_applications_by_company(db: Session, user_id: int, text: str) -> list[Application]:
    found = []
    for application in db.scalars(apps.active_applications(user_id)):
        key = application.company_key
        if key and len(key) >= 3 and re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", text):
            found.append(application)
    return found


def application_detail(db: Session, user_id: int, application_id: int) -> ToolResult:
    result = ToolResult()
    try:
        application = apps.owned_application(db, user_id, application_id)
    except apps.NotFound:
        result.status = "not_found"
        result.intro = "I couldn't find that application. It may have been deleted or moved to the trash."
        return result
    summary = apps.summaries(db, [application], apps.utcnow())[application.application_id]
    src = application_source(application)
    result.focus = ResultItem("application", str(application.application_id), application_label(application))
    result.intro = f"Your application to {application_label(application)}:"
    result.add(f"Status: {application.status}"
               + (f" (since {fmt_date(application.status_changed_at)})" if application.status_changed_at else "")
               + ".", src)
    if application.applied_at:
        result.add(f"Applied on {fmt_date(application.applied_at)}.", src)
    result.add(f"Interview rounds recorded: {summary['interview_count']}.", src)
    if summary["next_interview"] is not None:
        interview = summary["next_interview"]
        result.add(f"Next interview: round {interview.round_number} ({interview.interview_type}, {interview.mode}) "
                   f"on {fmt_datetime(interview.scheduled_at)}.",
                   Source("application_interview", str(interview.interview_id),
                          f"Round {interview.round_number}: {application_label(application)}"))
    result.add(f"Pending reminders: {summary['pending_reminders']}.", src)
    if summary["next_reminder"] is not None:
        reminder = summary["next_reminder"]
        result.add(f"Next reminder due {fmt_datetime(reminder.remind_at)}.",
                   Source("application_reminder", str(reminder.reminder_id), f"Reminder: {reminder.title}"))
    result.actions.append(action("Open this application", "GET", f"/applications/{application.application_id}",
                                 requires_confirmation=False))
    return result


def application_list(db: Session, user_id: int, statuses: list[str]) -> ToolResult:
    total, items = apps.list_applications(
        db, user_id, statuses=statuses or None, source=None, company=None, domain=None, q=None,
        applied_from=None, applied_to=None, created_from=None, created_to=None, sort="updated_at",
        order="desc", skip=0, limit=MAX_LIST)
    result = ToolResult(result_kind="application")
    label = ", ".join(statuses) if statuses else "all"
    if not items:
        result.status = "empty"
        result.intro = ("You aren't tracking any applications" + (f" with status {label}" if statuses else "")
                        + " yet.")
        result.actions.append(action("Track an application", "POST", "/applications"))
        return result
    result.intro = (f"You have {total} application(s)" + (f" with status {label}" if statuses else "")
                    + (f"; the {len(items)} most recently updated:" if total > len(items) else ":"))
    summaries = apps.summaries(db, items, apps.utcnow())
    for number, application in enumerate(items, start=1):
        summary = summaries[application.application_id]
        result.add(_application_line(application, summary, number), application_source(application),
                   llm_text=_application_line(application, summary, number, application_ai_label(application)))
        result.results.append(ResultItem("application", str(application.application_id),
                                         application_label(application)))
    return result


def upcoming_interviews(db: Session, user_id: int) -> ToolResult:
    data = application_dashboard(db, user_id)
    result = ToolResult(result_kind="application")
    if not data["next_interviews"]:
        result.status = "empty"
        result.intro = "You have no upcoming interviews recorded."
        return result
    result.intro = f"You have {data['upcoming_interviews']} upcoming interview(s):"
    internal = {a.application_id for a in db.scalars(select(Application).where(
        Application.application_id.in_([i["application_id"] for i in data["next_interviews"]]),
        Application.user_id == user_id, Application.source == "internal"))}
    for number, item in enumerate(data["next_interviews"], start=1):
        label = f"{item['title']} at {item['company_name']}"
        ai_label = label if item["application_id"] in internal else "an external application"
        detail = (f"round {item['round_number']} ({item['interview_type']}, {item['mode']}) on "
                  f"{fmt_datetime(item['scheduled_at'])}.")
        result.add(f"{number}. {label}: {detail}",
                   Source("application_interview", str(item["interview_id"]), f"Round {item['round_number']}: {label}"),
                   Source("application", str(item["application_id"]), label),
                   llm_text=f"{number}. {ai_label}: {detail}")
        result.results.append(ResultItem("application", str(item["application_id"]), label,
                                         {"interview_id": item["interview_id"]}))
    return result


def reminders(db: Session, user_id: int) -> ToolResult:
    total, items = apps.list_reminders(db, user_id, application_id=None, state="pending", due_from=None,
                                       due_to=None, overdue=None, skip=0, limit=MAX_LIST)
    result = ToolResult(result_kind="application")
    if not items:
        result.status = "empty"
        result.intro = "You have no pending reminders."
        return result
    now = apps.utcnow()
    result.intro = f"You have {total} pending reminder(s)" + ("; the next ones:" if total > len(items) else ":")
    for number, reminder in enumerate(items, start=1):
        application = reminder.application
        overdue = apps.as_utc(reminder.remind_at) < now
        due = f"due {fmt_datetime(reminder.remind_at)}" + (" (overdue)." if overdue else ".")
        result.add(f"{number}. \"{reminder.title}\" for {application_label(application)}, {due}",
                   Source("application_reminder", str(reminder.reminder_id), f"Reminder: {reminder.title}"),
                   application_source(application),
                   llm_text=f"{number}. A reminder for {application_ai_label(application)}, {due}")
        result.results.append(ResultItem("application", str(application.application_id),
                                         application_label(application), {"reminder_id": reminder.reminder_id}))
    result.outro = "Reminders are stored only; nothing is sent to you automatically."
    return result


def dashboard(db: Session, user_id: int) -> ToolResult:
    data = application_dashboard(db, user_id)
    src = Source("dashboard", "applications", "Application dashboard")
    result = ToolResult(intro="Your application overview:")
    result.add(f"Applications tracked: {data['total_applications']}; saved internships: {data['saved_internships']}.",
               src)
    by_status = ", ".join(f"{k} {v}" for k, v in data["by_status"].items() if v)
    if by_status:
        result.add(f"By status: {by_status}.", src)
    result.add(f"Submitted: {data['submitted_applications']}; selected: {data['selected']}; "
               f"rejected: {data['rejected']}.", src)
    if data["success_rate"] is not None:
        result.add(f"Success rate: {data['success_rate']}% ({data['formulas']['success_rate']}).", src)
    result.add(f"Upcoming interviews: {data['upcoming_interviews']}; pending reminders: {data['pending_reminders']}"
               f" ({data['overdue_reminders']} overdue).", src)
    return result


def help_result() -> ToolResult:
    result = ToolResult(status="ok")
    result.intro = ("I can help with your career search using your own data. Try:\n"
                    "- \"What skills are on my resume?\"\n"
                    "- \"Find remote data science internships in Pune\" (then \"tell me more about the second one\")\n"
                    "- \"Show my top matches\" / \"Why is the first one a good match?\"\n"
                    "- \"What skills am I missing for it?\" / \"How do I learn Docker?\"\n"
                    "- \"Help with a cover letter for the first one\"\n"
                    "- \"Give me practice questions on SQL\"\n"
                    "- \"What is the status of my applications?\" / \"When is my next interview?\" / "
                    "\"Show my reminders\"")
    return result
