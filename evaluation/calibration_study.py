"""Semantic-similarity calibration study (in memory, no database).

Usage:
    python -m evaluation.calibration_study

Embeds all 180 internship texts and synthetic persona queries with the
pinned model and reports the cosine-similarity distribution for related
(same-domain) and unrelated pairs, and how candidate calibration bounds
map them. Writes docs/assignment/evaluation/calibration_results.json.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import numpy as np  # noqa: E402

from backend.models import Internship, InternshipSkill, Skill  # noqa: E402
from backend.services.candidate_profile import build_query_text  # noqa: E402
from backend.services.compatibility import SEMANTIC_CEILING, SEMANTIC_FLOOR  # noqa: E402
from backend.services.embeddings import SentenceTransformerEmbedder  # noqa: E402
from backend.services.internship_seed import load_dataset  # noqa: E402
from backend.services.internship_text import build_internship_text  # noqa: E402

OUTPUT = Path(__file__).resolve().parents[1] / "docs" / "assignment" / "evaluation" / "calibration_results.json"

PERSONAS = {
    "data_science": (["Python", "Pandas", "NumPy", "Scikit-learn", "Statistics", "Machine Learning", "SQL"],
                     "B.Sc Statistics", "Aspiring data scientist building ML models.", {"Data Science"}),
    "frontend_web": (["JavaScript", "React", "HTML", "CSS", "TypeScript", "Tailwind CSS", "Git"],
                     "B.Tech Computer Science", "Frontend developer building responsive web apps.", {"Web Development"}),
    "backend": (["Python", "FastAPI", "Django", "PostgreSQL", "REST API", "Docker", "Git"],
                "B.Tech Computer Science", "Backend developer building APIs.", {"Software Development", "Web Development"}),
    "devops": (["Docker", "Kubernetes", "AWS", "Terraform", "Linux", "CI/CD", "Jenkins"],
               "B.Tech IT", "Cloud and DevOps enthusiast.", {"DevOps/Cloud"}),
    "mobile": (["Kotlin", "Swift", "React Native", "Firebase", "Git"], "BCA", "Mobile app developer.",
               {"Mobile Development"}),
    "ui_ux": (["Figma", "Adobe XD", "Wireframing", "Prototyping", "User Research"], "B.Des", "Product designer.",
              {"UI/UX Design"}),
    "security": (["Linux", "Networking", "Python", "SQL"], "B.Tech CSE",
                 "Interested in cybersecurity and penetration testing.", {"Cybersecurity"}),
    "qa": (["Selenium", "Java", "JIRA", "Agile", "SQL"], "B.Tech", "QA automation tester.", {"QA/Testing"}),
    "marketing": (["SEO", "Content Writing", "Social Media Marketing", "Google Analytics", "Market Research"],
                  "BBA", "Digital marketing enthusiast.", {"Digital Marketing"}),
    "sparse_one_skill": (["Communication"], None, None, set()),
    "mismatch_chef": (["Cooking", "Menu Planning", "Food Safety"], "Diploma in Culinary Arts",
                      "Professional chef.", set()),
}

CANDIDATE_BOUNDS = [(0.15, 0.65), (0.30, 0.75), (0.35, 0.75), (0.40, 0.75), (0.45, 0.80)]


def _transient(record: dict) -> Internship:
    internship = Internship(
        title=record["role_title"], company=record["company"], domain=record["domain"],
        location=record["location"], work_mode=record["mode"],
        min_education=record["min_education"], description=record["description"],
    )
    internship.skill_links = (
        [InternshipSkill(skill=Skill(name=s), importance="required") for s in record["required_skills"]]
        + [InternshipSkill(skill=Skill(name=s), importance="preferred") for s in record["preferred_skills"]]
    )
    return internship


def _pct(values) -> dict:
    return {f"p{p}": round(float(np.percentile(values, p)), 4) for p in (5, 25, 50, 75, 95)}


def main() -> int:
    records = load_dataset()
    texts = [build_internship_text(_transient(r)) for r in records]
    domains = np.array([r["domain"] for r in records])

    embedder = SentenceTransformerEmbedder()
    documents = embedder.embed(texts)
    names = list(PERSONAS)
    queries = embedder.embed([build_query_text(p[0], p[1], p[2]) for p in PERSONAS.values()])
    sims = queries @ documents.T

    related, unrelated, per_persona = [], [], {}
    for i, name in enumerate(names):
        targets = PERSONAS[name][3]
        row = sims[i]
        mask = np.isin(domains, list(targets)) if targets else np.zeros(len(row), bool)
        top5 = np.argsort(-row)[:5]
        if targets:
            related.extend(row[mask])
            unrelated.extend(row[~mask])
        per_persona[name] = {
            "top1": round(float(row[top5[0]]), 4),
            "top5_in_target_domain": int(mask[top5].sum()) if targets else None,
            "max_similarity": round(float(row.max()), 4),
        }

    related, unrelated = np.array(related), np.array(unrelated)
    bounds = []
    for floor, ceiling in CANDIDATE_BOUNDS:
        f = lambda x: np.clip((x - floor) / (ceiling - floor), 0, 1)  # noqa: E731
        bounds.append({
            "floor": floor, "ceiling": ceiling,
            "unrelated_median": round(float(np.median(f(unrelated))), 3),
            "unrelated_p95": round(float(np.percentile(f(unrelated), 95)), 3),
            "related_median": round(float(np.median(f(related))), 3),
            "related_p95": round(float(np.percentile(f(related), 95)), 3),
            "share_saturated": round(float((f(sims.ravel()) >= 1).mean()), 4),
            "mismatch_max": round(float(f(sims[names.index("mismatch_chef")]).max()), 3),
            "sparse_max": round(float(f(sims[names.index("sparse_one_skill")]).max()), 3),
            "in_use": (floor, ceiling) == (SEMANTIC_FLOOR, SEMANTIC_CEILING),
        })

    result = {
        "model": embedder.model_name, "revision": embedder.revision,
        "pairs": int(sims.size),
        "all_pairs": {"min": round(float(sims.min()), 4), **_pct(sims.ravel()), "max": round(float(sims.max()), 4)},
        "related_pairs": {"n": int(related.size), **_pct(related)},
        "unrelated_pairs": {"n": int(unrelated.size), **_pct(unrelated)},
        "per_persona": per_persona,
        "candidate_bounds": bounds,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
