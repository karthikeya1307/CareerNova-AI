"""Phase 5: fact checking, generation, LLM safety and rendering (no database)."""

import pytest

from backend.models import Internship, InternshipSkill, Skill
from backend.services.ats import ats_report
from backend.services.cover_letter import (
    CoverLetterOptions,
    InvalidEmphasisError,
    generate_cover_letter,
)
from backend.services.document_renderer import download_filename, render_docx, render_text
from backend.services.fact_base import CandidateFacts, Fact, scrub
from backend.services.fact_check import check_statement, skill_mentions
from backend.services.llm.base import LLMError, assert_no_contact
from backend.services.resume_customizer import ResumeOptions, customize_resume
from backend.services.resume_parser import parse_resume_file
from backend.services.skill_normalizer import normalize_extracted_skills
from conftest import FakeLLM

CONTACT = {"name": "Asha Rao", "email": "asha@example.com", "phone": "+91 90000 00002",
           "location": "Pune", "linkedin": "linkedin.com/in/asha-rao", "github": None}


def make_internship(required=("Python", "SQL", "Docker"), preferred=("Django",)):
    internship = Internship(internship_id=1, title="Backend Developer Intern",
                            company="Nimbus Analytics", domain="Software Development",
                            description="Build REST APIs and data pipelines.", is_active=True)
    internship.skill_links = [
        InternshipSkill(skill=Skill(skill_id=n, name=s), importance=imp)
        for n, (s, imp) in enumerate([*[(s, "required") for s in required],
                                      *[(s, "preferred") for s in preferred]])
    ]
    return internship


def make_candidate(skills=("Python", "FastAPI", "PostgreSQL", "Docker", "HTML", "CSS", "Git")):
    facts = [
        Fact("sum-1", "summary", "Backend developer who designs REST APIs. Enjoys databases. Third sentence."),
        Fact("edu-1", "education", "B.Tech IT, Example Institute of Technology, 2026"),
        Fact("exp-1", "experience", "Software Intern, Example Systems, 2025\n"
                                    "Built 12 REST endpoints with FastAPI and PostgreSQL."),
        Fact("proj-1", "project", "Portfolio Site\nBuilt with HTML and CSS."),
        Fact("proj-2", "project", "Inventory API\nDeployed a Docker service used by 20 users."),
    ]
    return CandidateFacts(5, dict(CONTACT), facts, list(skills), "B.Tech IT")


# ------------------------------------------------------------------
# Fact checker
# ------------------------------------------------------------------

@pytest.fixture
def candidate():
    return make_candidate()


def test_faithful_rewrite_passes(candidate):
    text = "Built 12 REST endpoints using FastAPI and PostgreSQL at Example Systems."
    assert check_statement(text, ["exp-1"], candidate.by_id, candidate.skills) == []


@pytest.mark.parametrize("text, code", [
    ("Built 40 REST endpoints with FastAPI.", "unsupported_number"),
    ("Built REST endpoints with FastAPI and Kubernetes.", "unsupported_skill"),
    ("Built REST endpoints at Google with FastAPI.", "unsupported_term"),
    ("Earned a Master of Science from Stanford.", "unsupported_term"),
])
def test_invented_content_is_caught(candidate, text, code):
    problems = check_statement(text, ["exp-1"], candidate.by_id, candidate.skills)
    assert code in {p["code"] for p in problems}


def test_skill_named_in_cited_fact_is_supported(candidate):
    # "REST APIs" is in the candidate's own summary although not a parsed skill.
    text = "Backend developer focused on REST APIs and databases."
    assert check_statement(text, ["sum-1"], candidate.by_id, candidate.skills) == []
    # ...but citing a fact that does not mention it is not enough.
    assert check_statement("Designs REST APIs.", ["proj-1"], candidate.by_id, candidate.skills)


def test_unknown_fact_id_is_caught(candidate):
    problems = check_statement("Built things.", ["exp-9"], candidate.by_id, candidate.skills)
    assert problems[0]["code"] == "unknown_fact"


@pytest.mark.parametrize("text, expected", [
    ("I excel at teamwork and like to go hiking.", set()),
    ("Rest of the team used spring cleaning.", set()),
    ("Used Excel and Go for tooling.", {"Excel", "Go"}),
    ("Deployed on AWS with Docker.", {"AWS", "Docker"}),
])
def test_skill_mentions_ignore_ordinary_words(text, expected):
    assert skill_mentions(text) == expected


def test_scrub_removes_contact_details():
    text = "Asha Rao (asha@example.com, +91 90000 00002) see https://github.com/asha"
    cleaned = scrub(text, CONTACT)
    for secret in ("Asha Rao", "asha@example.com", "90000", "github.com"):
        assert secret not in cleaned


def test_assert_no_contact():
    assert_no_contact({"text": "Built APIs in Pune"}, CONTACT)        # city alone is allowed
    for leaked in ("Asha Rao", "asha@example.com", "+91 90000 00002"):
        with pytest.raises(LLMError):
            assert_no_contact({"facts": [f"contact {leaked}"]}, CONTACT)


# ------------------------------------------------------------------
# Deterministic resume
# ------------------------------------------------------------------

def test_deterministic_resume_uses_only_candidate_facts(candidate):
    content, log = customize_resume(candidate, make_internship(), ResumeOptions(), None)
    sections = {s["key"]: s for s in content["sections"]}

    skills = sections["skills"]["items"][0]["lines"][0].split(", ")
    assert skills[:2] == ["Docker", "Python"]            # matched required first
    assert set(skills) == set(candidate.skills)          # nothing added
    assert "SQL" not in skills and "Django" not in skills
    # Summary trimmed to two sentences, still the candidate's own words.
    assert sections["summary"]["items"][0]["lines"] == ["Backend developer who designs REST APIs. Enjoys databases."]
    # Docker project ranks first among projects for a Docker internship.
    assert sections["projects"]["items"][0]["fact_ids"] == ["proj-2"]
    assert log.as_dict()["llm"]["used"] is False

    text = render_text(content)
    for fact in candidate.facts:
        if fact.kind != "summary":
            for line in fact.body:
                assert line.rstrip(".") in text


def test_resume_limits_are_respected(candidate):
    content, _ = customize_resume(candidate, make_internship(), ResumeOptions(max_projects=1, max_skills=5), None)
    sections = {s["key"]: s for s in content["sections"]}
    assert len(sections["projects"]["items"]) == 1
    assert len(sections["skills"]["items"][0]["lines"][0].split(", ")) == 5


# ------------------------------------------------------------------
# LLM resume: accepted, rejected, unavailable, privacy
# ------------------------------------------------------------------

def test_llm_valid_output_is_used(candidate):
    provider = FakeLLM({
        "summary": {"text": "Backend developer focused on REST APIs and databases.", "fact_ids": ["sum-1"]},
        "bullets": [{"fact_id": "exp-1", "text": "Built 12 REST endpoints using FastAPI and PostgreSQL."}],
    })
    content, log = customize_resume(candidate, make_internship(), ResumeOptions(), provider)
    sections = {s["key"]: s for s in content["sections"]}

    assert sections["summary"]["items"][0]["lines"] == ["Backend developer focused on REST APIs and databases."]
    assert sections["experience"]["items"][0]["lines"] == ["Built 12 REST endpoints using FastAPI and PostgreSQL."]
    assert log.llm_used and log.llm_accepted == 2 and log.rejected == []


def test_llm_fabrications_are_rejected_and_replaced(candidate):
    provider = FakeLLM({
        "summary": {"text": "Award-winning engineer from Google.", "fact_ids": ["sum-1"]},
        "bullets": [
            {"fact_id": "exp-1", "text": "Built 50 endpoints with Kubernetes."},
            {"fact_id": "exp-1", "text": "Built endpoints."},                  # supported
            {"fact_id": "exp-7", "text": "Invented entry."},
            {"fact_id": "proj-2", "text": "Deployed a Docker service."},
        ],
    })
    content, log = customize_resume(candidate, make_internship(), ResumeOptions(), provider)
    sections = {s["key"]: s for s in content["sections"]}

    assert sections["summary"]["items"][0]["fact_ids"] == ["sum-1"]
    assert "Google" not in render_text(content)
    assert "Kubernetes" not in render_text(content)
    assert sections["experience"]["items"][0]["lines"] == ["Built endpoints."]
    codes = {p["code"] for r in log.rejected for p in r["problems"]}
    assert {"unsupported_term", "unsupported_number", "unsupported_skill", "unknown_fact"} <= codes
    assert log.as_dict()["llm"] == {"used": True, "accepted": 2, "rejected": 3}


def test_llm_payload_contains_no_contact_details(candidate):
    provider = FakeLLM({})
    customize_resume(candidate, make_internship(), ResumeOptions(), provider)
    sent = str(provider.calls[0]["payload"]) + provider.calls[0]["system"]
    for value in ("Asha Rao", "asha@example.com", "90000 00002", "linkedin.com"):
        assert value not in sent
    assert "Pune" not in sent        # candidate location is not part of the payload


def test_llm_error_falls_back_to_deterministic(candidate):
    provider = FakeLLM(error=LLMError("The language-model provider could not be reached."))
    content, log = customize_resume(candidate, make_internship(), ResumeOptions(), provider)
    deterministic, _ = customize_resume(candidate, make_internship(), ResumeOptions(), None)
    assert content == deterministic
    assert log.warnings[0]["code"] == "llm_unavailable" and log.llm_used is False


def test_privacy_guard_blocks_leaking_payload():
    candidate = make_candidate()
    candidate.facts.append(Fact("ach-1", "achievement", "Award to Asha Rao"))   # unscrubbed on purpose
    candidate.by_id["ach-1"] = candidate.facts[-1]
    candidate.facts[0] = Fact("sum-1", "summary", "Asha Rao builds APIs.")
    candidate.by_id["sum-1"] = candidate.facts[0]
    provider = FakeLLM({})
    _, log = customize_resume(candidate, make_internship(), ResumeOptions(), provider)
    assert provider.calls == []
    assert log.warnings[0]["code"] == "privacy_guard"


# ------------------------------------------------------------------
# Cover letter
# ------------------------------------------------------------------

def test_cover_letter_never_claims_missing_skills(candidate):
    internship = make_internship()
    content, _ = generate_cover_letter(candidate, internship, CoverLetterOptions(), [], None)
    text = render_text(content)

    assert "Backend Developer Intern position at Nimbus Analytics" in text
    assert "Nimbus Analytics' work in Software Development" in text
    assert skill_mentions(text) <= set(candidate.skills)       # SQL/Django never claimed
    assert "learning" not in text


def test_cover_letter_learning_sentence_only_for_in_progress_skills(candidate):
    content, _ = generate_cover_letter(candidate, make_internship(), CoverLetterOptions(), ["SQL"], None)
    learning = [p for p in content["paragraphs"] if p["key"] == "learning"]
    assert learning[0]["text"] == "I am currently learning SQL to strengthen my fit for this role."


def test_cover_letter_emphasis_and_tone(candidate):
    content, _ = generate_cover_letter(candidate, make_internship(),
                                       CoverLetterOptions(emphasize_skills=("fastapi",)), [], None)
    fit = next(p for p in content["paragraphs"] if p["key"] == "fit")
    assert fit["text"].startswith("My skills in FastAPI match")

    concise, _ = generate_cover_letter(candidate, make_internship(), CoverLetterOptions(tone="concise"), [], None)
    assert "motivation" not in {p["key"] for p in concise["paragraphs"]}

    with pytest.raises(InvalidEmphasisError):
        generate_cover_letter(candidate, make_internship(), CoverLetterOptions(emphasize_skills=("Rust",)), [], None)


def test_cover_letter_llm_rejects_unsupported_paragraphs(candidate):
    provider = FakeLLM({"paragraphs": [
        {"key": "opening", "text": "I am applying for the Backend Developer Intern position at Nimbus Analytics.",
         "fact_ids": ["internship"]},
        {"key": "fit", "text": "I have 5 years of SQL experience.", "fact_ids": ["skills"]},
    ]})
    content, log = generate_cover_letter(candidate, make_internship(), CoverLetterOptions(), [], provider)
    by_key = {p["key"]: p for p in content["paragraphs"]}
    assert by_key["opening"]["text"].startswith("I am applying for the Backend Developer Intern")
    assert "SQL" not in skill_mentions(by_key["fit"]["text"])   # PostgreSQL is fine; SQL is not claimed
    assert "5 years" not in by_key["fit"]["text"]
    assert log.llm_accepted == 1 and len(log.rejected) == 1


# ------------------------------------------------------------------
# ATS report and rendering
# ------------------------------------------------------------------

def test_ats_report_reports_but_never_adds_missing_keywords(candidate):
    report = ats_report(candidate, make_internship())
    assert report["required_coverage"] == {"present": 2, "total": 3}
    assert report["missing_keywords"] == ["SQL", "Django"]
    assert any("only if you genuinely have this skill" in s for s in report["suggestions"])
    assert {c["check"] for c in report["checks"]} >= {"contact_email", "summary", "skills_section"}


def test_docx_is_ats_parsable(candidate):
    content, _ = customize_resume(candidate, make_internship(), ResumeOptions(), None)
    data = parse_resume_file(render_docx(content), "tailored.docx")["extracted_data"]

    assert {s.name for s in normalize_extracted_skills(data)} == set(candidate.skills)
    assert data["email"] == "asha@example.com"
    assert data["education"] and data["projects"] and data["work_experience"]


def test_cover_letter_renders(candidate):
    content, _ = generate_cover_letter(candidate, make_internship(), CoverLetterOptions(), [], None)
    text = render_text(content)
    assert text.startswith("Asha Rao") and text.rstrip().endswith("Asha Rao")
    assert render_docx(content)[:2] == b"PK"       # a valid DOCX (zip) file


def test_download_filename_is_safe():
    assert download_filename("resume", "Nimbus / Analytics <Inc>", "docx") == "Resume_Nimbus_Analytics_Inc.docx"
    assert download_filename("cover_letter", None, "txt") == "Cover_Letter_internship.txt"
