"""Interview preparation agent (HR assignment): resume-grounded role recommendations, role-specific
technical and HR questions with answer guidance, and personalised preparation roadmaps.

Everything here is deterministic and built only from:
* the signed-in student's own extracted resume (``fact_base.build_fact_base``),
* curated data: career tracks (``career_tracks.json``), the technical question bank, common
  misconceptions, the HR question guide (``hr_question_guide.json``) and learning plans.

Nothing is invented about the candidate. Sample answers are labelled as samples; drafts built from
the resume say so. The assistant (``assistant/prep_agent.py``) and the REST routes (``routes/prep.py``)
both use these functions.
"""

from backend.services.prep.context import ResumeContext, load_context, profile, skill_evidence
from backend.services.prep.guidance import guidance
from backend.services.prep.questions import hr_questions, technical_questions
from backend.services.prep.roadmap import roadmap
from backend.services.prep.roles import assess, find_role, recommend

__all__ = [
    "ResumeContext", "assess", "find_role", "guidance", "hr_questions", "load_context", "profile",
    "recommend", "roadmap", "skill_evidence", "technical_questions",
]
