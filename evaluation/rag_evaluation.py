"""RAG internship-matching evaluation runner.

Usage (from the project root):
    python -m evaluation.rag_evaluation

Safety:
* Runs ONLY against a PostgreSQL database whose name ends in "_test"
  (default career_companion_test); it empties that database's tables.
* Builds its FAISS index in a temporary folder that is deleted afterwards.
* Loads the embedding model from the local .models folder only.

Outputs (synthetic data only):
    docs/assignment/evaluation/evaluation_results.json
    docs/assignment/evaluation/EVALUATION_RAW.md
"""

from __future__ import annotations

import os

os.environ.setdefault("DB_NAME", "career_companion_test")
os.environ.setdefault("HF_HUB_OFFLINE", "1")

if not os.environ["DB_NAME"].endswith("_test"):
    raise SystemExit("Refusing to run: DB_NAME must end with '_test'.")

import hashlib  # noqa: E402
import json  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
from collections import Counter  # noqa: E402
from datetime import datetime, timezone  # noqa: E402
from pathlib import Path  # noqa: E402

import numpy as np  # noqa: E402
from sqlalchemy import func, select, text  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "assignment" / "evaluation"


def main() -> int:
    index_dir = Path(tempfile.mkdtemp(prefix="rag_eval_index_"))
    os.environ["FAISS_INDEX_DIR"] = str(index_dir)

    from backend import database
    from backend.models import (
        Base, Internship, KnowledgeDocument, Resume, ResumeExtraction,
        StudentProfile, User,
    )
    from backend.services import embeddings, vector_index
    from backend.services.candidate_profile import build_candidate, build_query_text
    from backend.services.compatibility import (
        ALGORITHM_VERSION, SEMANTIC_CEILING, SEMANTIC_FLOOR, WEIGHTS,
    )
    from backend.services.internship_seed import (
        DEFAULT_DATASET_PATH, load_dataset, seed_internships, validate_records,
    )
    from backend.services.matching_agent import run_matching
    from backend.services.resume_parser import parse_resume_file
    from backend.services.resume_skills import sync_resume_skills
    from backend.services.skill_normalizer import normalize_extracted_skills
    from evaluation.profiles import PROFILES

    assert database.engine.url.database.endswith("_test"), "not a test database"

    checks: list[dict] = []

    def check(name: str, passed: bool, details) -> None:
        checks.append({"check": name, "passed": bool(passed), "details": details})
        print(f"[{'PASS' if passed else 'FAIL'}] {name}: {details}")

    try:
        # ----------------------------------------------------------
        # Reset the TEST database
        # ----------------------------------------------------------
        Base.metadata.create_all(bind=database.engine)
        tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
        with database.engine.begin() as connection:
            connection.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))

        db = database.SessionLocal()

        # ----------------------------------------------------------
        # 1. Dataset validation
        # ----------------------------------------------------------
        raw_bytes = Path(DEFAULT_DATASET_PATH).read_bytes()
        raw = load_dataset()
        report = validate_records(raw)
        required_fields = ["id", "company", "role_title", "domain", "location", "mode",
                           "duration_weeks", "stipend_inr_per_month", "min_education",
                           "required_skills", "preferred_skills", "description"]
        missing = {f: sum(1 for r in raw if r.get(f) in (None, "", [])) for f in required_fields}
        missing["preferred_skills"] = sum(1 for r in raw if "preferred_skills" not in r)
        content_dupes = sum(c - 1 for c in Counter(
            (r["company"], r["role_title"], r["location"]) for r in raw).values() if c > 1)
        description_dupes = sum(c - 1 for c in Counter(r["description"] for r in raw).values() if c > 1)

        dataset_info = {
            "records": report.total,
            "valid": len(report.valid),
            "errors": report.errors,
            "duplicate_ids": report.duplicate_ids,
            "duplicate_company_title_location": content_dupes,
            "identical_descriptions": description_dupes,
            "missing_values_per_field": missing,
            "unmapped_skills": report.unmapped_skills,
            "distinct_skills": report.skill_count,
            "stipend_range_inr": report.stipend_range,
            "duration_weeks_range": (min(r["duration_weeks"] for r in raw),
                                     max(r["duration_weeks"] for r in raw)),
            "domains": dict(Counter(r["domain"] for r in raw).most_common()),
            "work_modes": dict(Counter(r["mode"] for r in raw).most_common()),
            "education_requirements": dict(Counter(r["min_education"] for r in raw).most_common()),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "synthetic": True,
        }
        check("dataset: 180 valid records, no duplicate ids, no missing values",
              report.ok and report.total == 180 and not any(missing.values()),
              f"{len(report.valid)}/{report.total} valid, missing={sum(missing.values())}, "
              f"duplicate ids={len(report.duplicate_ids)}")
        check("dataset: no duplicate company+title+location", content_dupes == 0,
              f"{content_dupes} duplicates")
        check("dataset: every skill maps to the canonical catalog", not report.unmapped_skills,
              f"{report.skill_count} distinct skills, unmapped={report.unmapped_skills or 'none'}")

        # ----------------------------------------------------------
        # 2. Import into PostgreSQL and verify against the source file
        # ----------------------------------------------------------
        seed_internships(db, report.valid, apply=True)
        db.commit()
        by_external = {r["id"]: r for r in raw}
        mismatches = 0
        for internship in db.scalars(select(Internship)):
            source = by_external[internship.external_id]
            links = {l.skill.name: l.importance for l in internship.skill_links}
            same = (
                internship.title == source["role_title"]
                and internship.company == source["company"]
                and internship.description == source["description"]
                and internship.location == source["location"]
                and internship.work_mode == source["mode"]
                and {k for k, v in links.items() if v == "required"} == set(source["required_skills"])
                and {k for k, v in links.items() if v == "preferred"} == set(source["preferred_skills"])
            )
            mismatches += 0 if same else 1
        count = db.scalar(select(func.count()).select_from(Internship))
        check("database records identical to dataset file", count == 180 and mismatches == 0,
              f"{count} rows, {mismatches} mismatches")

        # ----------------------------------------------------------
        # 3. Embedding model and FAISS index
        # ----------------------------------------------------------
        embedder = embeddings.SentenceTransformerEmbedder()
        embeddings.set_embedder(embedder)
        probe = embedder.embed(["python developer", "graphic designer"])
        check("embedding model: all-MiniLM-L6-v2, 384 dimensions, unit vectors",
              embedder.dimension == 384 and np.allclose(np.linalg.norm(probe, axis=1), 1, atol=1e-4),
              f"{embedder.model_name} @ {embedder.revision[:8]}, dim={embedder.dimension}")

        build = vector_index.rebuild_index(embedder)
        loaded = vector_index.load_index()
        manifest = loaded.manifest
        documents = db.scalars(
            select(KnowledgeDocument).where(KnowledgeDocument.indexing_status == "indexed")
        ).all()
        active_ids = set(db.scalars(select(Internship.internship_id).where(Internship.is_active)))
        doc_ok = all(d.internship_id in active_ids for d in documents)
        check("FAISS manifest consistent with model and PostgreSQL",
              manifest["count"] == loaded.index.ntotal == len(documents) == len(active_ids) == 180
              and manifest["dimension"] == 384 and manifest["model_name"] == embedder.model_name
              and manifest["model_revision"] == embedder.revision and doc_ok,
              f"vectors={loaded.index.ntotal}, documents={len(documents)}, active={len(active_ids)}, "
              f"dim={manifest['dimension']}, sha256 verified on load")

        sample = documents[:: max(1, len(documents) // 12)][:12]
        stored = np.vstack([loaded.index.reconstruct(int(d.document_id)) for d in sample])
        fresh = embedder.embed([d.content for d in sample])
        agreement = float(np.min(np.sum(stored * fresh, axis=1)))
        check("stored vectors match re-embedded source text", agreement > 0.999,
              f"min cosine over {len(sample)} documents = {agreement:.6f}")

        index_info = {
            "model": embedder.model_name, "revision": embedder.revision,
            "dimension": embedder.dimension, "vectors": loaded.index.ntotal,
            "index_type": type(loaded.index).__name__, "built_at": build.built_at,
            "semantic_calibration": {"floor": SEMANTIC_FLOOR, "ceiling": SEMANTIC_CEILING},
            "weights": WEIGHTS, "algorithm_version": ALGORITHM_VERSION,
        }
        doc_by_internship = {d.internship_id: d.document_id for d in documents}

        def cosine(query_vector, internship_id):
            vector = loaded.index.reconstruct(int(doc_by_internship[internship_id]))
            return float(np.dot(query_vector, vector))

        # ----------------------------------------------------------
        # 4. Per-profile evaluation
        # ----------------------------------------------------------
        results = []
        retrieval_problems = 0
        grounding_problems = 0

        for number, profile in enumerate(PROFILES, start=1):
            parsed = parse_resume_file(profile.to_docx(), f"{profile.key}.docx")
            data = parsed["extracted_data"]

            user = User(first_name="Candidate", last_name=f"{number:02d}",
                        email=f"candidate{number:02d}@example.com",
                        password_hash="not-used", is_verified=True)
            db.add(user)
            db.flush()
            if profile.profile_degree or profile.profile_location:
                db.add(StudentProfile(user_id=user.user_id, degree=profile.profile_degree,
                                      location=profile.profile_location))
            resume = Resume(user_id=user.user_id, filename=f"{profile.key}.docx",
                            file_path=f"uploads/resumes/{user.user_id}/{'0' * 32}.docx",
                            file_type="docx", status="completed")
            db.add(resume)
            db.flush()
            db.add(ResumeExtraction(resume_id=resume.resume_id, parser_type=parsed["parser_type"],
                                    extracted_data=data, status="completed"))
            sync_resume_skills(db, resume.resume_id, data)
            db.commit()

            normalized = normalize_extracted_skills(data)
            context = build_candidate(db, resume)
            candidate = context.candidate
            query_vector = embedder.embed([context.query_text])[0]

            # Pure semantic retrieval (vector database only).
            retrieved = vector_index.search(db, context.query_text, 5, embedder)
            scores = [h.similarity for h in retrieved]
            if scores != sorted(scores, reverse=True) or not all(h.internship.is_active for h in retrieved):
                retrieval_problems += 1

            # Full matching (retrieval + compatibility scoring).
            run = run_matching(db, resume, k=5)
            matches = []
            for rank, (result, internship) in enumerate(run.results, start=1):
                source = by_external[internship.external_id]
                posting_skills = set(source["required_skills"]) | set(source["preferred_skills"])
                grounded = (
                    internship.title == source["role_title"]
                    and internship.company == source["company"]
                    and set(result.matched_required) | set(result.missing_required) == set(source["required_skills"])
                    and set(result.matched_preferred) | set(result.missing_preferred) == set(source["preferred_skills"])
                    and set(result.matched_required + result.matched_preferred) <= set(candidate.skills)
                    and set(result.matched_required + result.matched_preferred) <= posting_skills
                )
                grounding_problems += 0 if grounded else 1
                relevant = internship.domain in profile.expected_domains
                flags = []
                if profile.expected_domains and not relevant:
                    flags.append("outside expected domains")
                if result.score < 45:
                    flags.append("weak score (<45)")
                if result.required_coverage == 0:
                    flags.append("no required skill matched")
                matches.append({
                    "rank": rank,
                    "internship_id": internship.internship_id,
                    "external_id": internship.external_id,
                    "title": internship.title,
                    "company": internship.company,
                    "domain": internship.domain,
                    "work_mode": internship.work_mode,
                    "location": internship.location,
                    "min_education": internship.min_education,
                    "required_skills": source["required_skills"],
                    "preferred_skills": source["preferred_skills"],
                    "raw_cosine_similarity": round(cosine(query_vector, internship.internship_id), 4),
                    "semantic_score": round(result.component("semantic").score, 4),
                    "compatibility_score": result.score,
                    "score_before_caps": result.score_before_caps,
                    "label": result.label,
                    "data_completeness": result.data_completeness,
                    "components": [c.as_dict() for c in result.components],
                    "matched_required": result.matched_required,
                    "missing_required": result.missing_required,
                    "matched_preferred": result.matched_preferred,
                    "missing_preferred": result.missing_preferred,
                    "explanation": result.explanation,
                    "caps_applied": result.caps_applied,
                    "missing_information": result.missing_information,
                    "grounded_in_source": grounded,
                    "in_expected_domain": relevant if profile.expected_domains else None,
                    "flags": flags,
                })

            # Diagnostic only: would experience/project text change retrieval?
            ablation = None
            if data.get("work_experience") or data.get("projects"):
                extra = " ".join(
                    e.get("details", "") for e in (data.get("work_experience") or []) + (data.get("projects") or [])
                    if isinstance(e, dict)
                )
                extended_query = context.query_text + f"\nExperience and projects: {extra}"
                extended = vector_index.search(db, extended_query, 5, embedder)
                ablation = {
                    "note": "Diagnostic only; the application query does not include experience/project text.",
                    "current_top5_domains": [h.internship.domain for h in retrieved],
                    "with_experience_projects_top5_domains": [h.internship.domain for h in extended],
                    "current_top5_mean_similarity": round(float(np.mean([h.similarity for h in retrieved])), 4),
                    "with_experience_projects_mean_similarity": round(float(np.mean([h.similarity for h in extended])), 4),
                    "overlap_of_top5": len({h.internship.internship_id for h in retrieved}
                                           & {h.internship.internship_id for h in extended}),
                }

            results.append({
                "key": profile.key,
                "scenario": profile.scenario,
                "expected_domains": list(profile.expected_domains),
                "extracted": {
                    "parser": parsed["parser_type"],
                    "summary": data.get("professional_summary"),
                    "raw_skills": data.get("skills"),
                    "normalized_skills": [{"name": s.name, "category": s.category} for s in normalized],
                    "education_entries": [e.get("details") for e in data.get("education") or []],
                    "experience_entries": [e.get("details") for e in data.get("work_experience") or []],
                    "project_entries": [e.get("details") for e in data.get("projects") or []],
                    "address": data.get("address"),
                },
                "candidate": {
                    "degree": candidate.degree_text, "degree_source": candidate.degree_source,
                    "location": candidate.location_text, "location_source": candidate.location_source,
                    "query_text": context.query_text,
                },
                "semantic_retrieval_top5": [
                    {"rank": i, "title": h.internship.title, "company": h.internship.company,
                     "domain": h.internship.domain, "cosine_similarity": h.similarity,
                     "is_active": h.internship.is_active}
                    for i, h in enumerate(retrieved, start=1)
                ],
                "matching": {
                    "run_id": str(run.run_id),
                    "semantic_available": run.semantic_available,
                    "candidates_considered": run.candidates_considered,
                    "top5": matches,
                },
                "ablation_experience_projects": ablation,
            })
            print(f"profile {profile.key}: top score "
                  f"{matches[0]['compatibility_score'] if matches else '-'}")

        check("retrieval: results active and sorted by similarity", retrieval_problems == 0,
              f"{retrieval_problems} profiles with problems")
        check("matching: every result grounded in source records", grounding_problems == 0,
              f"{grounding_problems} ungrounded results")

        db.close()

        output = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "database": database.engine.url.database,
            "dataset": dataset_info,
            "index": index_info,
            "system_checks": checks,
            "profiles": results,
        }
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        (OUTPUT_DIR / "evaluation_results.json").write_text(
            json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        (OUTPUT_DIR / "EVALUATION_RAW.md").write_text(render_markdown(output), encoding="utf-8")
        print(f"Wrote {OUTPUT_DIR / 'evaluation_results.json'}")
        print(f"Wrote {OUTPUT_DIR / 'EVALUATION_RAW.md'}")
        return 0 if all(c["passed"] for c in checks) else 1

    finally:
        from backend.services import embeddings as _e, vector_index as _v
        _e.set_embedder(None)
        _v.clear_cache()
        shutil.rmtree(index_dir, ignore_errors=True)


# ============================================================
# MARKDOWN RENDERING (generated, not hand-written)
# ============================================================

def _skills(values) -> str:
    return ", ".join(values) if values else "—"


def render_markdown(out: dict) -> str:
    lines = [
        "# RAG Evaluation — Raw Output",
        "",
        "> Generated automatically by `python -m evaluation.rag_evaluation`. Do not edit by hand.",
        f"> Generated at {out['generated_at']} on database `{out['database']}` (synthetic data only).",
        "",
        "## System checks",
        "",
        "| Result | Check | Details |",
        "|---|---|---|",
    ]
    for c in out["system_checks"]:
        lines.append(f"| {'PASS' if c['passed'] else 'FAIL'} | {c['check']} | {c['details']} |")

    idx = out["index"]
    lines += [
        "",
        "## Index",
        "",
        f"- Model: `{idx['model']}` @ `{idx['revision']}` — {idx['dimension']} dimensions",
        f"- FAISS index: `{idx['index_type']}` with {idx['vectors']} vectors",
        f"- Semantic calibration: floor {idx['semantic_calibration']['floor']}, "
        f"ceiling {idx['semantic_calibration']['ceiling']}",
        f"- Weights: {idx['weights']} — algorithm `{idx['algorithm_version']}`",
        "",
    ]

    for p in out["profiles"]:
        ex, cand, m = p["extracted"], p["candidate"], p["matching"]
        lines += [
            f"## {p['key']} — {p['scenario']}",
            "",
            "### Extracted candidate information",
            "",
            f"- Normalized skills: {_skills([s['name'] + ('' if s['category'] != 'other' else ' (other)') for s in ex['normalized_skills']])}",
            f"- Education (resume): {_skills(ex['education_entries'])}",
            f"- Experience entries: {len(ex['experience_entries'])} | Project entries: {len(ex['project_entries'])}",
            f"- Degree used: {cand['degree'] or '—'} (source: {cand['degree_source'] or 'missing'})",
            f"- Location used: {cand['location'] or '—'} (source: {cand['location_source'] or 'missing'})",
            f"- Expected domains (evaluator): {_skills(p['expected_domains'])}",
            "",
            "### Top 5 — pure semantic retrieval (FAISS)",
            "",
            "| # | Internship | Company | Domain | Cosine |",
            "|---|---|---|---|---|",
        ]
        for r in p["semantic_retrieval_top5"]:
            lines.append(f"| {r['rank']} | {r['title']} | {r['company']} | {r['domain']} | {r['cosine_similarity']:.4f} |")

        lines += [
            "",
            f"### Top 5 — final matching (candidates considered: {m['candidates_considered']})",
            "",
            "| # | Internship | Domain | Mode / location | Cosine | Semantic | Score | Label | Matched | Missing (required) | Flags |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in m["top5"]:
            matched = _skills(r["matched_required"] + [f"{s} (pref)" for s in r["matched_preferred"]])
            lines.append(
                f"| {r['rank']} | {r['title']} — {r['company']} | {r['domain']} | "
                f"{r['work_mode']} / {r['location']} | {r['raw_cosine_similarity']:.4f} | "
                f"{r['semantic_score']:.2f} | {r['compatibility_score']} | {r['label']} | {matched} | "
                f"{_skills(r['missing_required'])} | {_skills(r['flags'])} |"
            )
        lines += ["", "#### Why each internship was recommended", ""]
        for r in m["top5"]:
            lines.append(f"**{r['rank']}. {r['title']} — {r['company']}** "
                         f"(score {r['compatibility_score']}, completeness {r['data_completeness']})")
            for sentence in r["explanation"]:
                lines.append(f"- {sentence}")
            for info in r["missing_information"]:
                lines.append(f"- _Missing information:_ {info}")
            lines.append("")

        if p["ablation_experience_projects"]:
            a = p["ablation_experience_projects"]
            lines += [
                "#### Diagnostic: adding experience/project text to the query",
                "",
                f"- Current top-5 domains: {_skills(a['current_top5_domains'])} "
                f"(mean cosine {a['current_top5_mean_similarity']})",
                f"- With experience/projects: {_skills(a['with_experience_projects_top5_domains'])} "
                f"(mean cosine {a['with_experience_projects_mean_similarity']})",
                f"- Shared internships in top 5: {a['overlap_of_top5']}/5",
                "",
            ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
