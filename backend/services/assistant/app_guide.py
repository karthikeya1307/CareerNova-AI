"""Application Assistant: step-by-step guidance through the real CareerNova AI workflow.

Answers "How does this application work?", "How do I get started?", "What should I do after uploading my
resume?", "How can I find internships?", "How can I prepare for interviews?", "What should I do next?" and
follow-ups such as "tell me more about step 4" with short numbered steps. Each step names the actual page, what
the student provides and what CareerNova does next.

The student's progress comes only from their own records (profile fields, parsed resume, saved corrections,
readiness score, match runs, skill-gap plans, interview chats/sessions, applications). A step is shown as done
only when those records prove it; nothing is assumed. Interview preparation itself stays in the Interview
Preparation Assistant - this guide only points there.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (Application, Conversation, InterviewSession, MatchResult, Message, Resume, ResumeExtraction,
                            SkillGapRecommendation, StudentProfile, User)
from backend.services.assistant.facts import Source, ToolResult, action
from backend.services.candidate_profile import latest_completed_extraction
from backend.services.resume_readiness import score_resume

INTENT = "app_guide"
GUIDE_SOURCE = Source("product_doc", "02_workflow", "Product guide: Recommended workflow")

# ---- What the student asks -------------------------------------------------------------------------------
_APP = r"(?:this|the|careernova(?: ai)?)\s*(?:app\w*|platform|site|website|product|tool|careernova(?: ai)?)?"
TOPICS: list[tuple[str, re.Pattern]] = [
    ("after_registration", re.compile(
        r"\b(?:after|now\s+that)\s+(?:i\s+(?:have\s+)?)?(?:registr\w+|register(?:ed|ing)?|sign(?:ed|ing)?\s+up|"
        r"creat(?:ed|ing)\s+(?:my|an)\s+account|log(?:ged|ging)?\s+in|sign(?:ed|ing)?\s+in)\b", re.I)),
    ("improve_resume", re.compile(
        r"\bhow\s+(?:can|do|should|could)\s+i\s+(?:improve|strengthen|make\s+better|fix)\s+(?:my\s+)?(?:resume|cv)\b"
        r"(?!\s+for\b)|\bhow\s+to\s+improve\s+(?:my\s+)?(?:resume|cv)\b(?!\s+for\b)", re.I)),
    ("after_resume", re.compile(
        r"\bafter\s+(?:i\s+)?(?:upload(?:ing|ed)?|add(?:ing|ed)?)\s+(?:my\s+|a\s+)?(?:resume|cv)\b|"
        r"\b(?:uploaded|added)\s+my\s+(?:resume|cv)\b.*\b(?:now|next|then)\b", re.I)),
    ("internships", re.compile(
        r"\b(?:how|where)\s+(?:can|do|should|could)\s+i\s+(?:find|get|search\s+for|look\s+for|discover)\s+"
        r"(?:an?\s+|good\s+|suitable\s+|the\s+right\s+|relevant\s+)?(?:internships?|jobs?|opportunit\w+)\b|"
        r"\bhow\s+to\s+find\s+(?:an?\s+)?(?:internships?|jobs?)\b", re.I)),
    ("interviews", re.compile(
        r"\b(?:how|where)\s+(?:can|do|should|could)\s+i\s+(?:prepare|practi[cs]e|get\s+ready)\s+for\s+"
        r"(?:an?\s+|my\s+|the\s+)?interviews?\b|\bhow\s+to\s+prepare\s+for\s+(?:an?\s+)?interviews?\b", re.I)),
    ("overview", re.compile(
        r"\bhow\s+(?:does|do)\s+" + _APP + r"\s*work\b|"
        r"\bhow\s+(?:do|can|should)\s+i\s+(?:get\s+started|start|begin|use\s+" + _APP + r")\b|"
        r"\b(?:getting\s+started|where\s+(?:do|should|can)\s+i\s+(?:start|begin))\b|"
        r"\bwhat\s+(?:should|do|can)\s+i\s+do\s+(?:first|next|now)\b|"
        r"\bwhat(?:'s|\s+is)\s+(?:my\s+)?next\s+step\b|"
        r"\bwhat\s+is\s+the\s+(?:work\s*flow|process|flow|user\s+journey)\b|"
        r"\b(?:work\s*flow|flow|process|steps?)\s+(?:of|for|in)\s+" + _APP + r"\b", re.I)),
]
STEP_RE = re.compile(r"\bstep\s*(?:number\s*)?(\d{1,2})\b", re.I)
NEXT_RE = re.compile(r"^\s*(?:and\s+)?(?:then\s+)?(?:what(?:'s|\s+is)?\s+)?(?:next|after\s+that|then)\s*\??\s*$|"
                     r"^\s*(?:ok(?:ay)?|done|i\s+did\s+(?:that|it))[\s,.!]*(?:what(?:'s|\s+is)?\s+)?(?:next)?\s*\??\s*$",
                     re.I)


def detect(text: str) -> str | None:
    for topic, pattern in TOPICS:
        if pattern.search(text or ""):
            return topic
    return None


# ---- The workflow (real pages only) -------------------------------------------------------------------
@dataclass(frozen=True)
class Step:
    number: int
    title: str
    page: str            # where to go, as named in the navigation
    path: str            # the page's route (a safe link for the frontend)
    provide: str         # what the student gives
    then: str            # what CareerNova does afterwards


STEPS = [
    Step(1, "Create your account and sign in", "Sign up / Sign in", "",
         "your name, email, phone number and a password; then the verification link from your email",
         "creates your private account; everything you add later is visible only to you"),
    Step(2, "Complete your profile", "Profile", "/profile",
         "college, degree, graduation year, location and a short bio (skills come from your resume, not the profile)",
         "shows your profile completeness and uses your academic details alongside your resume for matching"),
    Step(3, "Upload your resume", "Resumes", "/resumes",
         "a PDF or DOCX resume, up to 5 MB",
         "reads your contact details, skills, education, experience, internships and projects"),
    Step(4, "Check the extracted details", "Resumes → Edit details", "/resumes",
         "corrections for anything that was read wrongly",
         "saves your corrected version; matching, documents and both assistants use it"),
    Step(5, "Review resume readiness and the ATS check", "Resumes and Dashboard", "/resumes",
         "nothing new - read the scores and the recommended improvements",
         "scores your resume's completeness and evidence (0-100); after matching, the ATS check compares it with "
         "your best internship match"),
    Step(6, "Find matching internships", "Matches or Internships", "/matches",
         "one click on Find my matches; optionally search or filter internships",
         "ranks open internships against your resume and explains each match"),
    Step(7, "Understand your skill gaps", "Skill gaps", "/skill-gaps",
         "the internship you are interested in",
         "lists the skills that internship needs and your resume does not show yet, with a learning plan"),
    Step(8, "Open the Interview Preparation Assistant", "Interview Prep Assistant", "/interview-assistant",
         "nothing - it reads your parsed resume",
         "recommends roles that fit your resume and sets a target role for your preparation"),
    Step(9, "Practise for interviews", "Interview Prep Assistant and Interview practice", "/interview-prep",
         "your answers to technical and HR questions, or a mock interview",
         "gives answer guidance, a personalised preparation roadmap and scored practice (practice guidance, not a "
         "hiring decision)"),
    Step(10, "Keep your profile and resume up to date", "Resumes and Profile", "/resumes",
         "a new resume version whenever you improve it (mark your preferred version)",
         "keeps every version, uses your preferred one, and lets you compare two versions"),
]
LINK_NAMES = {"/profile": "Profile", "/resumes": "Resumes", "/matches": "Matches", "/skill-gaps": "Skill gaps",
              "/interview-assistant": "the Interview Preparation Assistant", "/interview-prep": "Interview practice"}
TOPIC_STEPS = {"after_registration": [2, 3, 4], "improve_resume": [4, 5, 10], "after_resume": [4, 5, 6, 7],
               "internships": [6, 5, 7], "interviews": [8, 9]}


# ---- The student's progress (own records only) ----------------------------------------------------------
@dataclass
class Progress:
    verified: bool = False
    profile_fields: int = 0                 # of college, degree, graduation year, location
    has_bio: bool = False
    resumes: int = 0
    resume: Resume | None = None            # preferred, else newest parsed
    version: int | None = None
    corrected: bool = False
    readiness: dict | None = None
    matched: bool = False
    skill_gaps: bool = False
    interview_chats: int = 0
    interview_sessions: int = 0
    applications: int = 0
    done: dict[int, bool] = field(default_factory=dict)
    status: dict[int, str] = field(default_factory=dict)


def progress(db: Session, user: User) -> Progress:
    from backend.services.assistant import tools

    uid = user.user_id
    p = Progress(verified=bool(getattr(user, "is_verified", False)))
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == uid))
    if profile is not None:
        p.profile_fields = sum(bool(v) for v in (profile.college, profile.degree, profile.graduation_year,
                                                 profile.location))
        p.has_bio = bool(profile.bio)
    mine = list(db.scalars(select(Resume).where(Resume.user_id == uid)))
    p.resumes = len(mine)
    p.resume = tools.choose_resume(db, uid, None)
    if p.resume is not None:
        order = sorted(mine, key=lambda r: (r.uploaded_at, r.resume_id))
        p.version = next(i for i, r in enumerate(order, start=1) if r.resume_id == p.resume.resume_id)
        extraction = latest_completed_extraction(db, p.resume.resume_id)
        p.corrected = bool(db.scalar(select(func.count()).select_from(ResumeExtraction).where(
            ResumeExtraction.resume_id == p.resume.resume_id, ResumeExtraction.parser_type == "user_corrected")))
        p.readiness = score_resume(extraction.extracted_data or {}) if extraction is not None else None
        p.matched = bool(db.scalar(select(func.count()).select_from(MatchResult).where(
            MatchResult.user_id == uid, MatchResult.resume_id == p.resume.resume_id)))
        p.skill_gaps = bool(db.scalar(select(func.count()).select_from(SkillGapRecommendation).where(
            SkillGapRecommendation.user_id == uid, SkillGapRecommendation.resume_id == p.resume.resume_id)))
    p.interview_chats = db.scalar(select(func.count()).select_from(Conversation).where(
        Conversation.user_id == uid, Conversation.context["assistant"].as_string() == "interview")) or 0
    p.interview_sessions = db.scalar(select(func.count()).select_from(InterviewSession)
                                     .where(InterviewSession.user_id == uid)) or 0
    p.applications = db.scalar(select(func.count()).select_from(Application).where(Application.user_id == uid)) or 0

    name = f"V{p.version} ({p.resume.label or p.resume.filename})" if p.resume is not None else ""
    p.done = {
        1: True,
        2: p.profile_fields == 4,
        3: p.resume is not None,
        4: p.corrected,
        5: False,                                       # reading a score can't be recorded; always offered
        6: p.matched,
        7: p.skill_gaps,
        8: p.interview_chats > 0,
        9: p.interview_sessions > 0,
        10: False,                                      # ongoing
    }
    p.status = {
        1: "Done - you're signed in" + (" and your email is verified." if p.verified else "."),
        2: ("Done - all academic details are filled in." if p.done[2] else
            f"{p.profile_fields} of 4 academic details filled in." if profile is not None else
            "Not started - no profile details saved yet.") + ("" if p.has_bio or profile is None else " No bio yet."),
        3: (f"Done - {name} is parsed." if p.resume is not None else
            f"{p.resumes} resume(s) uploaded but none parsed successfully yet - re-parse or upload again."
            if p.resumes else "Not done yet - no resume uploaded."),
        4: (f"You saved corrections to {name}." if p.corrected else
            f"Open {name} and check what was extracted (no corrections saved so far)." if p.resume is not None
            else "Needs a parsed resume first."),
        5: (f"Your readiness for {name}: {p.readiness['score']}/100 ({p.readiness['label']})."
            + (" The ATS check is on your dashboard." if p.matched else " The ATS check appears after matching.")
            if p.readiness is not None else "Needs a parsed resume first."),
        6: ("Done - you have match results for this resume." if p.matched else
            # A run that found no open internships stores nothing, so only "no results yet" is known for sure.
            "Not done yet - no match results for this resume yet (run matching; if it finds nothing, no open "
            "internship fits right now)." if p.resume is not None
            else "Needs a parsed resume first."),
        7: ("Done - you have a skill-gap learning plan." if p.skill_gaps else
            "Not done yet - no skill-gap plan saved for this resume." if p.resume is not None
            else "Needs a parsed resume first."),
        8: (f"Done - you have {p.interview_chats} Interview Preparation Assistant "
            f"chat{'' if p.interview_chats == 1 else 's'}." if p.done[8] else
            "Not opened yet."),
        9: (f"Done - {p.interview_sessions} practice session{'' if p.interview_sessions == 1 else 's'} started."
            if p.done[9] else
            "No practice sessions yet."),
        10: (f"You have {p.resumes} resume version{'' if p.resumes == 1 else 's'}." if p.resumes
             else "Start by uploading your first resume."),
    }
    return p


def next_step(p: Progress) -> Step:
    for step in STEPS:
        if step.number in (5, 10):
            continue
        if not p.done.get(step.number):
            if step.number == 4 and p.resume is not None:
                continue                                 # checking is optional once parsed; don't block on it
            return step
    return STEPS[9]


# ---- Rendering -------------------------------------------------------------------------------------------
def _sources(p: Progress) -> list[Source]:
    sources = [GUIDE_SOURCE, Source("dashboard", "progress", "Your CareerNova progress")]
    if p.resume is not None:
        sources.append(Source("resume", str(p.resume.resume_id), f"Resume V{p.version}: {p.resume.filename}"))
    return sources


def _detail(result: ToolResult, step: Step, p: Progress, sources: list[Source]) -> None:
    result.add(f"**{step.number}. {step.title}** - go to **{step.page}**", *sources)
    result.add(f"- You provide: {step.provide}.", *sources)
    result.add(f"- CareerNova then {step.then}.", *sources)
    result.add(f"- Your status: {p.status[step.number]}", *sources)


def _link(result: ToolResult, step: Step) -> None:
    if step.path and not any(a["endpoint"] == step.path for a in result.actions):
        result.actions.append(action(f"Open {LINK_NAMES.get(step.path, step.page)}", "GET", step.path,
                                     requires_confirmation=False))


def build(p: Progress, topic: str, step_number: int | None = None) -> ToolResult:
    sources = _sources(p)
    result = ToolResult(uses_resume_id=p.resume.resume_id if p.resume is not None else None)
    nxt = next_step(p)
    if step_number is not None:
        step = STEPS[step_number - 1]
        result.intro = f"Step {step.number} of the CareerNova AI workflow:"
        _detail(result, step, p, sources)
        _link(result, step)
        if step.number < 10:
            result.outro = f'Ask "tell me more about step {step.number + 1}" for the following step.'
        return result

    if topic == "overview":
        result.intro = ("Here is how CareerNova AI works, step by step. The status after each step comes from your own "
                        "account data.")
        for step in STEPS:
            mark = "✓ " if p.done.get(step.number) else ""
            result.add(f"{step.number}. {mark}**{step.title}** ({step.page}) - {p.status[step.number]}", *sources)
        result.add("## Your next step", *sources)
        _detail(result, nxt, p, sources)
        _link(result, nxt)
        result.outro = ('Ask "tell me more about step 4" (or any step) for details. Interview preparation happens in '
                        "the separate Interview Preparation Assistant.")
        return result

    numbers = TOPIC_STEPS[topic]
    result.intro = {
        "after_registration": "After registering and signing in, set up your profile and resume:",
        "improve_resume": "To improve your resume in CareerNova AI:",
        "after_resume": "After uploading your resume, these are the next steps:",
        "internships": "To find internships that suit you:",
        "interviews": ("Interview preparation has its own assistant - the Interview Preparation Assistant. "
                       "Here is how to use it:"),
    }[topic]
    for n in numbers:
        _detail(result, STEPS[n - 1], p, sources)
        _link(result, STEPS[n - 1])
    if topic == "improve_resume":
        tips = (p.readiness or {}).get("recommendations") or []
        if tips:
            result.add(f"## Top improvements for V{p.version} (from its readiness check)", *sources)
            for tip in tips[:3]:
                result.add(f"- {tip}", *sources)
        result.add("- For one internship, create a tailored resume on **Documents** - it uses only facts from your "
                   "resume.", *sources)
    if topic == "internships":
        result.add("- When you find one you like: create a tailored resume and cover letter on **Documents**, then mark "
                   "it as applied and track it on **Applications**.", *sources)
    if topic == "after_resume" and p.resume is None:
        result.outro = "First upload a resume on the Resumes page (step 3)."
    elif nxt.number not in numbers:
        result.outro = f"Your next recommended step overall: step {nxt.number} - {nxt.title} ({nxt.page})."
    else:
        result.outro = f"Recommended next: step {nxt.number} - {nxt.title}."
    return result


# ---- Routing (Application Assistant only) ------------------------------------------------------------------
def _previous_guide(db: Session, conversation: Conversation) -> bool:
    """True when the latest assistant answer in this chat was a guide answer (for "step 4" / "what next?")."""
    last = db.scalar(select(Message).where(Message.conversation_id == conversation.conversation_id,
                                           Message.sender == "assistant")
                     .order_by(Message.message_id.desc()).limit(1))
    return last is not None and last.intent == INTENT


def route(db: Session, user: User, conversation: Conversation, text: str) -> tuple[str, ToolResult] | None:
    """(topic, answer) for a workflow question, else None (other questions keep their existing route)."""
    topic = detect(text)
    step = STEP_RE.search(text or "")
    if topic is None and step is not None and _previous_guide(db, conversation):
        number = int(step.group(1))
        if 1 <= number <= len(STEPS):
            return "step", build(progress(db, user), "step", number)
    if topic is None and NEXT_RE.search(text or "") and _previous_guide(db, conversation):
        topic = "overview"
    if topic is None:
        return None
    return topic, build(progress(db, user), topic)
