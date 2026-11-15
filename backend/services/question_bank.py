"""Curated interview question banks (Phase 6).

* ``backend/data/interview_question_bank.json`` - technical questions for
  every canonical skill in the internship dataset (easy/medium/hard).
* ``backend/data/behavioral_questions.json`` - behavioral/HR questions.
* ``backend/data/interview_misconceptions.json`` - curated common incorrect
  statements per key point (lower-case regular expressions plus a short
  correction). They are attached to the key points as ``misconceptions``.

All are validated on load: canonical skill names, unique ids, valid
difficulty, non-empty key points with keywords, compilable lower-case
patterns that refer to existing questions and key points, and no links.
"""

from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.services.skill_normalizer import SKILL_CATALOG

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
TECHNICAL_PATH = DATA_DIR / "interview_question_bank.json"
BEHAVIORAL_PATH = DATA_DIR / "behavioral_questions.json"
MISCONCEPTIONS_PATH = DATA_DIR / "interview_misconceptions.json"
DIFFICULTIES = ("easy", "medium", "hard")


def _no_links(data: Any, label: str) -> None:
    text = json.dumps(data).lower()
    if "http://" in text or "https://" in text or "www." in text:
        raise ValueError(f"{label} must not contain links")


def validate_technical_bank(data: dict[str, Any]) -> None:
    if not isinstance(data.get("version"), str) or not isinstance(data.get("technical"), dict):
        raise ValueError("Question bank needs 'version' and 'technical'")
    _no_links(data, "Question bank")

    seen_ids: set[str] = set()
    for skill, questions in data["technical"].items():
        if skill not in SKILL_CATALOG:
            raise ValueError(f"Unknown skill in question bank: {skill}")
        if not isinstance(questions, list) or not questions:
            raise ValueError(f"No questions for {skill}")
        for q in questions:
            qid = q.get("id")
            if not qid or qid in seen_ids:
                raise ValueError(f"Missing or duplicate question id: {qid}")
            seen_ids.add(qid)
            if q.get("difficulty") not in DIFFICULTIES:
                raise ValueError(f"Invalid difficulty for {qid}")
            text = q.get("question")
            if not isinstance(text, str) or len(text) < 15 or not text.endswith(("?", ".")):
                raise ValueError(f"Question text must be a full question or prompt for {qid}")
            points = q.get("key_points")
            if not isinstance(points, list) or len(points) < 2:
                raise ValueError(f"At least two key points required for {qid}")
            for point in points:
                if not point.get("point") or not point.get("keywords"):
                    raise ValueError(f"Key point without text or keywords in {qid}")
                if not all(isinstance(k, str) and k.strip() and k == k.lower() for k in point["keywords"]):
                    raise ValueError(f"Keywords must be lower-case strings in {qid}")
            if not q.get("explanation"):
                raise ValueError(f"Missing explanation for {qid}")


def validate_behavioral_bank(data: dict[str, Any]) -> None:
    if not isinstance(data.get("version"), str) or not isinstance(data.get("questions"), list):
        raise ValueError("Behavioral bank needs 'version' and 'questions'")
    _no_links(data, "Behavioral bank")
    seen: set[str] = set()
    for q in data["questions"]:
        qid = q.get("id")
        if not qid or qid in seen:
            raise ValueError(f"Missing or duplicate behavioral id: {qid}")
        seen.add(qid)
        if q.get("difficulty") not in DIFFICULTIES or not str(q.get("question", "")).endswith(("?", ".")):
            raise ValueError(f"Invalid behavioral question {qid}")
        if not q.get("theme_keywords") or not q.get("tips"):
            raise ValueError(f"Behavioral question {qid} needs theme keywords and tips")


def validate_misconceptions(data: dict[str, Any], technical: dict[str, Any]) -> None:
    if not isinstance(data.get("version"), str) or not isinstance(data.get("misconceptions"), dict):
        raise ValueError("Misconception file needs 'version' and 'misconceptions'")
    _no_links(data, "Misconception file")
    questions = {q["id"]: q for qs in technical["technical"].values() for q in qs}
    for qid, entries in data["misconceptions"].items():
        if qid not in questions:
            raise ValueError(f"Misconceptions refer to an unknown question: {qid}")
        if not isinstance(entries, list) or not entries:
            raise ValueError(f"No misconceptions listed for {qid}")
        for entry in entries:
            point = entry.get("point")
            if not isinstance(point, int) or not 0 <= point < len(questions[qid]["key_points"]):
                raise ValueError(f"Invalid key point index in misconceptions for {qid}")
            if not isinstance(entry.get("note"), str) or not entry["note"].strip():
                raise ValueError(f"Misconception without a correction note in {qid}")
            patterns = entry.get("patterns")
            if not isinstance(patterns, list) or not patterns:
                raise ValueError(f"Misconception without patterns in {qid}")
            for pattern in patterns:
                if not isinstance(pattern, str) or pattern != pattern.lower():
                    raise ValueError(f"Misconception patterns must be lower-case strings in {qid}")
                try:
                    re.compile(pattern)
                except re.error as exc:
                    raise ValueError(f"Invalid misconception pattern in {qid}: {exc}") from None


def attach_misconceptions(technical: dict[str, Any], misconceptions: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of the bank with ``misconceptions`` added to each affected key point."""
    merged = copy.deepcopy(technical)
    for questions in merged["technical"].values():
        for q in questions:
            for entry in misconceptions["misconceptions"].get(q["id"], []):
                q["key_points"][entry["point"]].setdefault("misconceptions", []).append(
                    {"patterns": list(entry["patterns"]), "note": entry["note"]})
    return merged


@lru_cache(maxsize=1)
def misconception_data() -> dict[str, Any]:
    raw = json.loads(TECHNICAL_PATH.read_text(encoding="utf-8"))
    validate_technical_bank(raw)
    data = json.loads(MISCONCEPTIONS_PATH.read_text(encoding="utf-8"))
    validate_misconceptions(data, raw)
    return data


@lru_cache(maxsize=1)
def technical_bank() -> dict[str, Any]:
    data = json.loads(TECHNICAL_PATH.read_text(encoding="utf-8"))
    validate_technical_bank(data)
    return attach_misconceptions(data, misconception_data())


@lru_cache(maxsize=1)
def behavioral_bank() -> dict[str, Any]:
    data = json.loads(BEHAVIORAL_PATH.read_text(encoding="utf-8"))
    validate_behavioral_bank(data)
    return data


def questions_for_skill(skill: str) -> list[dict[str, Any]]:
    return list(technical_bank()["technical"].get(skill, []))


def bank_info() -> dict[str, Any]:
    technical = technical_bank()["technical"]
    counts = {d: 0 for d in DIFFICULTIES}
    for questions in technical.values():
        for q in questions:
            counts[q["difficulty"]] += 1
    return {
        "technical_version": technical_bank()["version"],
        "behavioral_version": behavioral_bank()["version"],
        "skills_covered": len(technical),
        "technical_questions": sum(counts.values()),
        "by_difficulty": counts,
        "behavioral_questions": len(behavioral_bank()["questions"]),
        "misconception_version": misconception_data()["version"],
        "questions_with_misconception_checks": len(misconception_data()["misconceptions"]),
        "skills_with_misconception_checks": sum(
            1 for qs in technical.values()
            if any(q["id"] in misconception_data()["misconceptions"] for q in qs)),
    }
