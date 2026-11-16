"""Phase 8: intent detection and entity extraction (pure, no database)."""

import numpy as np
import pytest

from backend.services.assistant.intents import EXAMPLES, SemanticIntent, understand


@pytest.mark.parametrize("question, intent", [
    ("Hi!", "help"), ("hello there", "help"), ("What can you do?", "help"), ("help", "help"),
    ("What skills are on my resume?", "profile_summary"), ("summarise my profile", "profile_summary"),
    ("what do I know", "profile_summary"),
    ("Find remote data science internships in Pune", "internship_search"),
    ("show me internships for web development", "internship_search"),
    ("any machine learning openings?", "internship_search"), ("internships in Bengaluru", "internship_search"),
    ("tell me more about the 3rd one", "internship_detail"), ("details about internship #4", "internship_detail"),
    ("show my top matches", "top_matches"), ("which internships suit me", "top_matches"),
    ("why is the second one a good match?", "match_explain"), ("explain my match score", "match_explain"),
    ("how well do I fit it", "match_explain"),
    ("what skills am I missing for it?", "skill_gap"), ("what should I learn", "skill_gap"),
    ("show my skill gaps", "skill_gap"),
    ("how do I learn Docker?", "learning_plan"), ("give me a learning plan for SQL", "learning_plan"),
    ("roadmap for React", "learning_plan"),
    ("help me write a cover letter for the first one", "document_help"), ("is my resume ATS friendly", "document_help"),
    ("give me practice questions on SQL", "interview_prep"), ("prepare me for an interview", "interview_prep"),
    ("how is my interview progress", "interview_prep"),
    ("what is the status of my Acme application?", "application_status"),
    ("which applications were rejected?", "application_status"), ("did I get shortlisted", "application_status"),
    ("when is my next interview?", "upcoming_interviews"), ("my interviews this week", "upcoming_interviews"),
    ("show my reminders", "reminders"), ("what follow-ups do I have", "reminders"),
    ("what is my success rate?", "dashboard"), ("show my application dashboard", "dashboard"),
    ("What about the second one?", "followup"), ("and the last one?", "followup"), ("number 4", "followup"),
    ("is that one remote?", "followup"),
    ("asdf qwerty", "unknown"), ("the weather is nice", "unknown"),
])
def test_rule_based_intents(question, intent):
    assert understand(question).intent == intent


@pytest.mark.parametrize("question, ordinal", [
    ("the second one", 2), ("the 3rd one", 3), ("number 4", 4), ("option 2", 2), ("#5", 5), ("the last one", -1),
    ("the top one", 1), ("first", 1), ("the 2 one", 2), ("tell me about it", None),
])
def test_ordinals(question, ordinal):
    assert understand(question).ordinal == ordinal


def test_explicit_ids_are_not_ordinals():
    u = understand("cover letter for internship #12 please")
    assert u.internship_id == 12 and u.ordinal is None
    a = understand("what about application id 7")
    assert a.application_id == 7 and a.ordinal is None


def test_entities():
    u = understand("Find REMOTE Docker and SQL internships")
    assert u.work_mode == "Remote" and u.skills == ["Docker", "SQL"]
    assert "docker" in u.search_terms and "internships" not in u.search_terms
    assert understand("which were shortlisted or rejected").statuses == ["SHORTLISTED", "REJECTED"]
    assert understand("is it hybrid?").referent and understand("is it hybrid?").work_mode == "Hybrid"
    assert understand("the second one").search_terms == []


def test_long_input_is_truncated_safely():
    assert understand("find internships " * 500).intent == "internship_search"


class FakeEmbedder:
    """Unit vectors: phrases mentioning a keyword point in one direction."""
    model_name = "fake"

    def embed(self, texts):
        out = []
        for t in texts:
            v = np.array([("prepare" in t) * 1.0, ("roadmap" in t) * 1.0, 0.05])
            out.append(v / np.linalg.norm(v))
        return np.array(out)


def test_semantic_stage_threshold_and_margin():
    semantic = SemanticIntent(FakeEmbedder())
    assert semantic.classify("I want a roadmap") == "learning_plan"   # close to "give me a study roadmap"
    assert semantic.classify("zzz") is None                       # below the threshold
    assert understand("zzz unclear", semantic=semantic).intent == "unknown"


def test_semantic_stage_is_skipped_with_the_test_embedder():
    from backend.services.assistant.intents import default_semantic_intent
    assert default_semantic_intent() is None
