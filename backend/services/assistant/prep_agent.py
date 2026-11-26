"""Interview preparation agent inside the career assistant (HR assignment).

Routes resume / role / interview-preparation questions to ``backend.services.prep`` and renders the
results as sourced facts. Conversation memory (``conversation.context``):
* ``target_role``  - the role the student selected (slug), used by follow-ups such as
                     "generate HR questions" or "create my roadmap";
* ``prep_questions`` - ids of the last numbered question list, so "how do I answer question 3" works.
Everything comes from the student's own resume and curated data; nothing is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Conversation, User
from backend.services import career_tracks, prep
from backend.services.assistant.facts import Source, ToolResult, action
from backend.services.prep.questions import LEVELS

INTENTS = ("resume_analysis", "role_recommendation", "role_fit", "strengths", "weaknesses", "role_select",
           "technical_questions", "hr_questions", "answer_guidance", "prep_roadmap", "mock_interview")
TITLES = {
    "resume_analysis": "Resume analysis", "role_recommendation": "Role recommendations", "role_fit": "Role fit",
    "strengths": "My strengths", "weaknesses": "Skills to improve", "role_select": "Interview preparation",
    "technical_questions": "Technical questions", "hr_questions": "HR questions",
    "answer_guidance": "Answer guidance", "prep_roadmap": "Preparation roadmap", "mock_interview": "Mock interview",
}

R = lambda *p: [re.compile(x, re.I) for x in p]  # noqa: E731
RULES: list[tuple[str, list[re.Pattern]]] = [
    ("answer_guidance", R(r"\b(how (do|should|can|would) i answer|answer guidance|guidance for|sample answer|"
                          r"example answer|model answer|how to answer|improve(d)? answer)\b")),
    ("mock_interview", R(r"\bmock interview\b", r"\b(start|begin|practi[cs]e) (an? |my )?(mock |practice )?interview\b",
                         r"\binterview practice\b")),
    ("technical_questions", R(r"\btechnical (interview )?questions?\b", r"\bcoding (interview )?questions?\b",
                              r"\b(beginner|intermediate|advanced) (level )?questions?\b")),
    ("hr_questions", R(r"\b(hr|behaviou?ral|personal|soft[- ]skills?) (round |interview )?questions?\b", r"\bhr round\b",
                       r"\bhr interview\b")),
    ("prep_roadmap", R(r"\broadmap\b", r"\b(preparation|prep|study|learning) plan\b",
                       r"\bwhat should i (learn|study)\b", r"\bhow (do|can) i become\b", r"\bto become an?\b")),
    ("role_fit", R(r"\b(am i|i am|i'm) (\w+ )?(suitable|suited|ready|qualified|eligible|a (good )?fit|fit)\b",
                   r"\b(can|could) i (apply|get|become)\b", r"\bdo i (fit|qualify|match)\b", r"\bmy (fit|chances?) for\b")),
    ("role_recommendation", R(r"\b(which|what) (job )?(roles?|jobs?|positions?|careers?|job titles?)\b",
                              r"\bsuitable (roles?|jobs?|positions?|careers?)\b", r"\brecommend(ed)? (me )?(some |a )?(roles?|jobs?|careers?)\b",
                              r"\broles? (that )?(suit|fit|match)", r"\bwhat can i (apply|work) (for|as)\b",
                              r"\bcareer options?\b")),
    ("resume_analysis", R(r"\banaly[sz]e my (resume|cv|profile)\b", r"\b(resume|cv) analysis\b",
                          r"\breview my (resume|cv)\b")),
    ("strengths", R(r"\b(strongest|strong|best|top|main) (technical )?skills\b", r"\bmy (key )?strengths?\b",
                    r"\bwhat am i good at\b")),
    ("weaknesses", R(r"\bweakness(es)?\b", r"\bweak (areas?|points?|spots?)\b",
                     r"\b(which|what) skills? (should|do|must) i (improve|work on|develop)\b",
                     r"\bwhat should i improve\b", r"\bskills? to improve\b")),
    ("role_select", R(r"\b(select|choose|pick|target|set)( (my|a|the))? (target )?role\b",
                      r"\bprepare me for\b", r"\bi want to (be|become|apply for|work as)\b",
                      r"\b(prepare|preparing|get ready) for (an? |the )?\w[\w /+-]* (interview|role|job|position)\b",
                      r"\bmy target role\b")),
]
ORDINAL_RE = re.compile(r"\b(first|second|third|fourth|fifth|1st|2nd|3rd|4th|5th|one|two|three|four|five|[1-5])\b", re.I)
ORDINALS = {"first": 1, "1st": 1, "one": 1, "1": 1, "second": 2, "2nd": 2, "two": 2, "2": 2, "third": 3, "3rd": 3,
            "three": 3, "3": 3, "fourth": 4, "4th": 4, "four": 4, "4": 4, "fifth": 5, "5th": 5, "five": 5, "5": 5}
QUESTION_NUMBER = re.compile(r"\b(?:question|q)\s*#?\s*(\d{1,2})\b", re.I)
LEVEL_RE = re.compile(r"\b(beginner|intermediate|advanced|easy|medium|hard)\b", re.I)
LEVEL_ALIAS = {"easy": "beginner", "medium": "intermediate", "hard": "advanced"}
ROLE_NEEDED = {"role_fit", "role_select", "technical_questions", "hr_questions", "prep_roadmap", "mock_interview"}


@dataclass
class PrepRoute:
    intent: str
    result: ToolResult
    context: dict[str, Any] = field(default_factory=dict)      # keys to set in conversation.context


def detect(text: str) -> str | None:
    for intent, patterns in RULES:
        if any(p.search(text) for p in patterns):
            return intent
    return None


def _track_source(track: dict[str, Any]) -> Source:
    return Source("career_track", track["slug"], f"Career track: {track['title']}")


def _resume_source(ctx: prep.ResumeContext) -> Source:
    return Source("resume", str(ctx.resume.resume_id), f"Resume: {ctx.resume.filename}")


def _fact_source(ctx: prep.ResumeContext, fact_id: str, title: str) -> Source:
    return Source("resume_fact", f"{ctx.resume.resume_id}:{fact_id}", title[:120])


def _needs_resume(intent: str) -> PrepRoute:
    result = ToolResult(status="needs_resume", intro=(
        "I need your resume for that. Upload a PDF or DOCX resume on the Resumes page (or wait until it has finished "
        "processing) and ask again - every recommendation here is based on what your resume actually shows."))
    result.actions.append(action("Upload a resume", "POST", "/resumes/upload"))
    return PrepRoute(intent, result)


def _choose_role(intent: str, ctx: prep.ResumeContext) -> PrepRoute:
    result = ToolResult(status="clarify", intro="Which role should I prepare you for? These fit your resume best:")
    for rec in prep.recommend(ctx, 4):
        result.add(f"{rec['title']} - fit {rec['score']}/100 ({rec['readiness']['label']}).",
                   _resume_source(ctx), Source("career_track", rec["slug"], f"Career track: {rec['title']}"))
    result.outro = 'Reply with a role, for example "Prepare me for Data Analyst". Any role from the career tracks works.'
    result.uses_resume_id = ctx.resume.resume_id
    return PrepRoute(intent, result)


def _role_lines(result: ToolResult, ctx: prep.ResumeContext, rec: dict[str, Any], track: dict[str, Any],
                detailed: bool) -> None:
    src = [_resume_source(ctx), _track_source(track)]
    result.add(f"**{rec['title']}** - fit {rec['score']}/100: {rec['readiness']['label']}.", *src)
    for reason in rec["reasons"][: (6 if detailed else 3)]:
        result.add(f"  - {reason}", *src)
    if rec["core"]["missing"]:
        result.add(f"  - Missing core skills: {', '.join(rec['core']['missing'])}.", *src,
                   polarity={s: "missing" for s in rec["core"]["missing"]})
    if detailed and rec["advanced"]["missing"]:
        result.add(f"  - Advanced skills to add later: {', '.join(rec['advanced']['missing'])}.", *src)


def _number(result: ToolResult, items: list[dict[str, Any]], start: int) -> int:
    return start + len(items)


def recommendations(ctx: prep.ResumeContext, db: Session | None = None) -> ToolResult:
    from backend.services.prep.internships import for_role
    result = ToolResult(intro="Based on the skills, projects and experience in your resume, these roles fit you best:")
    recs = prep.recommend(ctx, 5)
    for number, rec in enumerate(recs):
        track = career_tracks.get_track(rec["slug"])
        _role_lines(result, ctx, rec, track, detailed=False)
        if rec["improve"]:
            result.add(f"  - Preparation priorities: {', '.join(rec['improve'][:3])}.", _resume_source(ctx), _track_source(track))
        if db is not None and number < 3:
            for job in for_role(db, track, ctx, 2):
                missing = f" (missing: {', '.join(job['missing_skills'][:3])})" if job["missing_skills"] else ""
                result.add(f"  - Internship to look at: {job['title']} at {job['company']}{missing}.",
                           Source("internship", str(job["internship_id"]), f"{job['title']} at {job['company']}"))
    result.outro = ('Fit = 75% core skills + 25% advanced skills found on your resume (roles-v1); it is guidance, not '
                    'a hiring prediction. Say "Prepare me for <role>" to select one, or ask "Am I suitable for a Java '
                    'Developer role?"')
    result.actions.append(action("See internships that match your resume", "POST", f"/matches/resumes/{ctx.resume.resume_id}",
                                 requires_confirmation=False))
    result.uses_resume_id = ctx.resume.resume_id
    return result


def analysis(ctx: prep.ResumeContext) -> ToolResult:
    p = prep.profile(ctx)
    src = _resume_source(ctx)
    result = ToolResult(intro=f"Here is what I read from your resume ({p['filename']}):")
    if p["degree"]:
        result.add(f"Education: {p['degree']}.", src)
    result.add(f"Skills ({len(p['skills'])}): {', '.join(p['skills']) or 'none recognised'}.", src)
    for kind, label in (("projects", "Projects"), ("experience", "Experience / internships"),
                        ("certifications", "Certifications"), ("achievements", "Achievements")):
        if p[kind]:
            result.add(f"{label}: {'; '.join(p[kind][:4])}.", src)
    evidence = [r for r in prep.skill_evidence(ctx) if r["evidence_count"]]
    if evidence:
        result.add(f"Strongest evidence (skills used in your projects or work): "
                   f"{', '.join(r['skill'] for r in evidence[:5])}.", src)
    top = prep.recommend(ctx, 3)
    result.add("## Roles that fit", src)
    for rec in top:
        result.add(f"{rec['title']} - fit {rec['score']}/100 ({rec['readiness']['label']}).",
                   src, Source("career_track", rec["slug"], f"Career track: {rec['title']}"))
    if not p["has_summary"]:
        result.add("Your resume has no professional summary - adding 2-3 lines aimed at your target role helps.", src)
    result.outro = 'Next: "Prepare me for <role>", "What are my weaknesses?" or "Create my preparation roadmap".'
    result.uses_resume_id = ctx.resume.resume_id
    return result


def strengths(ctx: prep.ResumeContext) -> ToolResult:
    result = ToolResult(intro="Your strongest technical skills, judged by where your resume shows them:")
    rows = prep.skill_evidence(ctx)
    if not rows:
        result.status = "empty"
        result.intro = "No skills were recognised on your resume yet. Add a Skills section and re-upload it."
        return result
    for row in rows[:6]:
        if row["evidence_count"]:
            places = "; ".join(e["title"][:70] for e in row["evidence"][:2])
            result.add(f"{row['skill']} - used in {row['evidence_count']} resume entr{'y' if row['evidence_count'] == 1 else 'ies'} ({places}).",
                       *[_fact_source(ctx, e["fact_id"], e["title"]) for e in row["evidence"][:2]],
                       polarity={row["skill"]: "have"})
        else:
            result.add(f"{row['skill']} - listed in your skills, not yet shown in a project or job.", _resume_source(ctx),
                       polarity={row["skill"]: "have"})
    result.outro = "Skills you can back with a project or job make the strongest interview answers."
    result.uses_resume_id = ctx.resume.resume_id
    return result


def weaknesses(ctx: prep.ResumeContext, track: dict[str, Any] | None) -> ToolResult:
    src = _resume_source(ctx)
    result = ToolResult()
    unproven = [r["skill"] for r in prep.skill_evidence(ctx) if not r["evidence_count"]]
    if track is None:
        track = career_tracks.get_track(prep.recommend(ctx, 1)[0]["slug"])
        result.intro = f"Areas to improve, measured against your best-fitting role ({track['title']}):"
    else:
        result.intro = f"Areas to improve for {track['title']}:"
    rec = prep.assess(track, ctx)
    tsrc = _track_source(track)
    if rec["core"]["missing"]:
        result.add(f"Missing core skills: {', '.join(rec['core']['missing'])} (learn these first).", src, tsrc,
                   polarity={s: "missing" for s in rec["core"]["missing"]})
    if rec["advanced"]["missing"]:
        result.add(f"Advanced skills not on your resume: {', '.join(rec['advanced']['missing'])}.", src, tsrc)
    if unproven:
        result.add(f"Listed but not shown in any project or job: {', '.join(unproven[:6])} - add a project or bullet that uses them.", src)
    profile = prep.profile(ctx)
    if not profile["projects"]:
        result.add("Your resume shows no projects - one solid project per core skill is the quickest improvement.", src)
    if not profile["has_summary"]:
        result.add("No professional summary was found on your resume.", src)
    if not result.facts:
        result.add(f"Your resume already covers every {track['title']} skill in the track - focus on interview practice.", src, tsrc)
    result.outro = 'Say "Create my preparation roadmap" for a step-by-step plan.'
    result.uses_resume_id = ctx.resume.resume_id
    return result


def role_fit(ctx: prep.ResumeContext, track: dict[str, Any]) -> ToolResult:
    rec = prep.assess(track, ctx)
    verdict = {"ready": "Yes - your resume is a good fit for", "close": "Nearly - you are close to",
               "possible": "Partly - with focused learning you can reach", "long_term": "Not yet - it is a longer-term goal to reach"}
    result = ToolResult(intro=f"{verdict[rec['readiness']['level']]} the {track['title']} role.")
    _role_lines(result, ctx, rec, track, detailed=True)
    result.outro = (f'Next: "Generate technical questions", "Generate HR questions" or "Create my roadmap" for '
                    f"{track['title']}. I've set it as your target role.")
    result.uses_resume_id = ctx.resume.resume_id
    return result


def select_role(ctx: prep.ResumeContext, track: dict[str, Any]) -> ToolResult:
    result = role_fit(ctx, track)
    result.intro = f"Target role set: {track['title']}. Here is where you stand:"
    result.outro = ("Ask me next: \"Generate technical questions\" (beginner / intermediate / advanced), \"Generate HR "
                    "questions\", \"How do I answer question 1?\", \"Create my preparation roadmap\" or \"Start a mock interview\".")
    result.actions.append(action(f"Practise a mock interview for {track['title']}", "POST", "/interviews/sessions",
                                 {"resume_id": ctx.resume.resume_id, "target_role": track["slug"], "mode": "mock"}))
    return result


def technical(ctx: prep.ResumeContext, track: dict[str, Any], level: str | None) -> tuple[ToolResult, list[str]]:
    data = prep.technical_questions(track, ctx, level)
    result = ToolResult(intro=f"Technical interview questions for {track['title']}, starting with skills on your resume:")
    ids: list[str] = []
    src_bank = Source("question_bank", "technical", "Curated technical question bank")
    for name, items in data["levels"].items():
        if not items:
            continue
        result.add(f"## {name.title()}", src_bank)
        for q in items:
            ids.append(q["id"])
            note = "" if q["skill_status"] == "on_resume" else (" (role skill not on your resume)" if q["skill_status"] == "role_missing" else "")
            result.add(f"{len(ids)}. [{q['skill']}] {q['question']}{note}", src_bank, _track_source(track))
    if data["project_questions"]:
        result.add("## About your own projects", _resume_source(ctx))
        for q in data["project_questions"]:
            ids.append(q["id"])
            result.add(f"{len(ids)}. {q['question']}", _fact_source(ctx, q["fact_id"], q["question"]))
    result.outro = 'Ask "How do I answer question 2?" for what the interviewer expects, key points, a sample answer and mistakes to avoid.'
    result.uses_resume_id = ctx.resume.resume_id
    return result, ids


def hr(ctx: prep.ResumeContext, track: dict[str, Any]) -> tuple[ToolResult, list[str]]:
    data = prep.hr_questions(track, ctx)
    result = ToolResult(intro=f"HR and behavioural questions for a {track['title']} interview:")
    ids = []
    src = Source("question_bank", "hr", "Curated HR question guide")
    for q in data["questions"]:
        ids.append(q["id"])
        extra = [_resume_source(ctx)] if q["personalised"] else []
        result.add(f"{len(ids)}. {q['question']}", src, *extra)
    result.outro = 'Ask "How do I answer question 1?" - for "Tell me about yourself" I draft an answer using only your resume.'
    result.uses_resume_id = ctx.resume.resume_id
    return result, ids


def answer_guidance(ctx: prep.ResumeContext, track: dict[str, Any] | None, question_id: str) -> ToolResult | None:
    g = prep.guidance(question_id, ctx, track)
    if g is None:
        return None
    src = Source("question_bank", g["kind"], "Curated question bank" if g["kind"] == "technical" else "Curated interview guide")
    result = ToolResult(intro=f"How to answer: \"{g['question']}\"")
    result.add(f"**What the interviewer expects:** {g['expects']}", src)
    result.add("## Points to mention", src)
    for p in g["points"]:
        result.add(f"- {p}", src)
    result.add("## Suggested structure", src)
    for i, step in enumerate(g["structure"], start=1):
        result.add(f"{i}. {step}", src)
    sample = g["sample_answer"]
    result.add(f"## {sample['label']}", src if sample["is_sample"] else _resume_source(ctx))
    result.add(sample["text"], src if sample["is_sample"] else _resume_source(ctx))
    result.add("## Common mistakes to avoid", src)
    for m in g["mistakes"]:
        result.add(f"- {m}", src)
    if g["from_your_resume"]:
        result.add("## From your resume (verified - use these)", _resume_source(ctx))
        for item in g["from_your_resume"]:
            sources = [_fact_source(ctx, item["fact_id"], item["text"])] if item["fact_id"] not in ("degree", "skills") else [_resume_source(ctx)]
            result.add(f"- {item['text']}", *sources)
    if g.get("note"):
        result.outro = g["note"]
    result.uses_resume_id = ctx.resume.resume_id
    return result


def roadmap_result(ctx: prep.ResumeContext, track: dict[str, Any], progress: dict[str, str]) -> ToolResult:
    r = prep.roadmap(track, ctx, progress)
    src, tsrc = _resume_source(ctx), _track_source(track)
    result = ToolResult(intro=f"Your {track['title']} preparation roadmap. {r['summary']}")
    for stage in r["stages"]:
        result.add(f"## Step {stage['step']}: {stage['stage']} - {stage['goal']}", tsrc)
        for t in stage["topics"]:
            hours = f", about {t['estimated_hours']} h" if t["estimated_hours"] else ""
            topics = f" Topics: {', '.join(t['topics'][:3])}." if t["topics"] else ""
            if t.get("resource"):
                topics += f" Resource: {t['resource']['title']}."
            result.add(f"- [{t['priority'].upper()}] {t['skill']}: {t['action']}{hours}.{topics}", src, tsrc,
                       polarity={t["skill"]: "have" if t["on_resume"] else "missing"})
    result.add("## Coding exercises", tsrc)
    for e in r["coding_exercises"]:
        result.add(f"- {e}", tsrc)
    if r["practice_questions"]:
        bank = Source("question_bank", "technical", "Curated technical question bank")
        result.add("## Interview questions to practise", bank)
        for q in r["practice_questions"]:
            result.add(f"- [{q['skill']}] {q['question']}", bank)
    result.add("## Improve your existing projects", src)
    for e in r["project_improvements"]:
        result.add(f"- {e}", src)
    result.add("## New project ideas", tsrc)
    for e in r["project_ideas"]:
        result.add(f"- {e}", tsrc)
    result.add("## Interview practice", tsrc)
    for e in r["interview_practice"]:
        result.add(f"- {e}", tsrc)
    if r["estimated_learning_hours"]:
        result.outro = (f"Estimated learning time for the high and medium priority skills: about "
                        f"{r['estimated_learning_hours']} hours (curated estimates).")
    result.actions.append(action(f"Practise a mock interview for {track['title']}", "POST", "/interviews/sessions",
                                 {"resume_id": ctx.resume.resume_id, "target_role": track["slug"], "mode": "mock"}))
    result.uses_resume_id = ctx.resume.resume_id
    return result


def route(db: Session, user: User, conversation: Conversation, text: str) -> PrepRoute | None:
    """Handle preparation-agent questions; None leaves the question to the other assistant tools."""
    intent = detect(text)
    named = prep.find_role(text)
    ctx_data = dict(conversation.context or {})
    awaiting = ctx_data.get("prep_awaiting_role")
    if intent is None:
        ordinal = ORDINAL_RE.search(text)
        if named is None and awaiting and ordinal and len(text.split()) <= 6:
            roles = ctx_data.get("prep_roles") or []
            index = ORDINALS.get(ordinal.group(1).lower(), 0) - 1
            if 0 <= index < len(roles):
                named = career_tracks.get_track(roles[index])
        if named is not None and re.search(r"\binterview questions?\b", text, re.I):
            intent = "technical_questions"
        elif named is not None and awaiting and len(text.split()) <= 6:
            # A role name (or "the second one") right after a role list selects it.
            intent = awaiting if awaiting in ROLE_NEEDED else "role_select"
        else:
            return None
    target = career_tracks.get_track(ctx_data.get("target_role") or "") if ctx_data.get("target_role") else None
    # "Interview questions for X" without technical/HR -> technical.
    if intent == "role_select" and named is None:
        return None
    if intent in ("role_fit", "prep_roadmap") and named is None and target is None:
        return None                 # e.g. "what should I learn next?" -> the skill-gap tools
    if intent == "answer_guidance" and not QUESTION_NUMBER.search(text) and not re.search(
            r"about yourself|strength|weakness|why should|why (are you|this)|team|deadline|goal|difficult problem|problem", text, re.I):
        return None                 # e.g. "how do I answer questions about my internship" -> other tools
    ctx = prep.load_context(db, user.user_id, conversation.resume_id)
    if ctx is None:
        return _needs_resume(intent)

    track = named or target
    updates: dict[str, Any] = {}
    if intent in ROLE_NEEDED and track is None:
        route_ = _choose_role(intent, ctx)
        route_.context = {"prep_awaiting_role": intent, "prep_roles": [r["slug"] for r in prep.recommend(ctx, 4)]}
        return route_
    if named is not None and intent in ROLE_NEEDED | {"weaknesses"}:
        updates["target_role"] = named["slug"]
    updates["prep_awaiting_role"] = None

    if intent == "resume_analysis":
        result = analysis(ctx)
    elif intent == "role_recommendation":
        result = recommendations(ctx, db)
        updates["prep_awaiting_role"] = "role_select"
        updates["prep_roles"] = [r["slug"] for r in prep.recommend(ctx, 5)]
    elif intent == "strengths":
        result = strengths(ctx)
    elif intent == "weaknesses":
        result = weaknesses(ctx, named or target)
    elif intent == "role_fit":
        result = role_fit(ctx, track)
    elif intent == "role_select":
        result = select_role(ctx, track)
    elif intent == "technical_questions":
        level = LEVEL_RE.search(text)
        level_name = LEVEL_ALIAS.get(level.group(1).lower(), level.group(1).lower()) if level else None
        result, ids = technical(ctx, track, level_name if level_name in LEVELS else None)
        updates["prep_questions"] = ids
    elif intent == "hr_questions":
        result, ids = hr(ctx, track)
        updates["prep_questions"] = ids
    elif intent == "answer_guidance":
        qid = None
        number = QUESTION_NUMBER.search(text)
        listed = ctx_data.get("prep_questions") or []
        if number:
            index = int(number.group(1)) - 1
            if 0 <= index < len(listed):
                qid = listed[index]
            else:
                result = ToolResult(status="clarify", intro=(
                    f"I don't have a question {number.group(1)} in this conversation. Ask for technical or HR "
                    "questions first, then pick a number from that list." if not listed else
                    f"The last list had {len(listed)} questions - pick a number from 1 to {len(listed)}."))
                return PrepRoute(intent, result, updates)
        else:
            theme = re.search(r"about yourself|strength|weakness|why should|why (are you|this)|team|deadline|goal|difficult problem|problem", text, re.I)
            key = theme.group(0).lower()
            qid = {"about yourself": "hr-about", "strength": "hr-strengths-weaknesses", "weakness": "hr-strengths-weaknesses",
                   "why should": "hr-why-hire", "team": "hr-teamwork", "deadline": "hr-situational-deadline",
                   "difficult problem": "hr-problem-solving", "problem": "hr-problem-solving",
                   "goal": "hr-goals"}.get(key, "hr-why-role")
        result = answer_guidance(ctx, track, qid)
        if result is None:
            result = ToolResult(status="not_found", intro="I couldn't find guidance for that question. Ask for a new list.")
    elif intent == "prep_roadmap":
        from backend.services import skill_progress
        progress = {k: v["status"] for k, v in skill_progress.statuses_for(db, user.user_id).items()}
        result = roadmap_result(ctx, track, progress)
    else:  # mock_interview
        result = ToolResult(intro=(f"Let's practise a {track['title']} mock interview. Open Interview practice: the role is "
                                   "pre-selected - choose the difficulty, then answer one question at a time. Each answer "
                                   "gets feedback, missing points and an improved answer, and you get a summary at the end."))
        result.add(f"Target role: {track['title']}.", _track_source(track), _resume_source(ctx))
        result.actions.append(action(f"Start a {track['title']} mock interview", "POST", "/interviews/sessions",
                                     {"resume_id": ctx.resume.resume_id, "target_role": track["slug"], "mode": "mock"}))
        result.uses_resume_id = ctx.resume.resume_id
    return PrepRoute(intent, result, updates)
