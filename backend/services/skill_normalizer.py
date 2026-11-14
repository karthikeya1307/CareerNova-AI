"""Skill normalization.

Turns the raw skill strings produced by ``resume_parser`` into canonical
skill names with a category, so resumes and internships can be compared
on the same vocabulary.

Rules:
* Known skills and their aliases map to one canonical name.
  Lookup ignores case, spaces, dots, hyphens, slashes and underscores,
  which also repairs PDF spacing glitches such as ``"A WS"`` -> ``AWS``.
* Proficiency words and section labels (``Basic``, ``Skills`` ...) are noise.
* Unknown skills are KEPT with category ``other`` and lightly cleaned.
* Output is de-duplicated case-insensitively and keeps first-seen order.

This module is pure (no database access) and does not change the
parser's own output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

CATEGORY_OTHER = "other"


# ============================================================
# CANONICAL SKILL CATALOG
# canonical name -> category
# Includes every skill used by the internship dataset.
# ============================================================

SKILL_CATALOG: dict[str, str] = {
    # Programming languages
    "Python": "programming_language",
    "Java": "programming_language",
    "C": "programming_language",
    "C++": "programming_language",
    "C#": "programming_language",
    "JavaScript": "programming_language",
    "TypeScript": "programming_language",
    "Kotlin": "programming_language",
    "Swift": "programming_language",
    "Go": "programming_language",
    "Rust": "programming_language",
    "PHP": "programming_language",
    "Ruby": "programming_language",
    "R": "programming_language",
    "Dart": "programming_language",
    "Scala": "programming_language",
    "MATLAB": "programming_language",
    "ABAP": "programming_language",
    "Bash": "programming_language",
    "HTML": "web",
    "CSS": "web",

    # Frameworks and libraries
    "React": "framework",
    "React Native": "framework",
    "Angular": "framework",
    "Vue": "framework",
    "Next.js": "framework",
    "Node.js": "framework",
    "Express.js": "framework",
    "Django": "framework",
    "Flask": "framework",
    "FastAPI": "framework",
    "Spring Boot": "framework",
    "Bootstrap": "framework",
    "Tailwind CSS": "framework",
    "Flutter": "framework",
    "Streamlit": "framework",
    ".NET": "framework",
    "REST API": "web",
    "GraphQL": "web",

    # Databases
    "SQL": "database",
    "MySQL": "database",
    "PostgreSQL": "database",
    "SQLite": "database",
    "MongoDB": "database",
    "Redis": "database",
    "Oracle": "database",
    "Firebase": "database",

    # Cloud and DevOps
    "AWS": "cloud_devops",
    "Azure": "cloud_devops",
    "GCP": "cloud_devops",
    "Docker": "cloud_devops",
    "Kubernetes": "cloud_devops",
    "Terraform": "cloud_devops",
    "Jenkins": "cloud_devops",
    "CI/CD": "cloud_devops",
    "Linux": "cloud_devops",
    "Networking": "cloud_devops",
    "Monitoring": "cloud_devops",
    "Vercel": "cloud_devops",
    "Netlify": "cloud_devops",
    "Heroku": "cloud_devops",

    # Data science and ML
    "Machine Learning": "data_ml",
    "Deep Learning": "data_ml",
    "NLP": "data_ml",
    "Computer Vision": "data_ml",
    "TensorFlow": "data_ml",
    "PyTorch": "data_ml",
    "Keras": "data_ml",
    "Scikit-learn": "data_ml",
    "Pandas": "data_ml",
    "NumPy": "data_ml",
    "Matplotlib": "data_ml",
    "Statistics": "data_ml",
    "Data Analysis": "data_ml",
    "Data Visualization": "data_ml",
    "Excel": "data_ml",
    "Power BI": "data_ml",
    "Tableau": "data_ml",
    "Generative AI": "data_ml",
    "LLM": "data_ml",

    # Tools
    "Git": "tool",
    "GitHub": "tool",
    "GitLab": "tool",
    "JIRA": "tool",
    "VS Code": "tool",
    "Google Colab": "tool",
    "Jupyter": "tool",
    "Postman": "tool",

    # Testing
    "Selenium": "testing",
    "Unit Testing": "testing",

    # Computer science fundamentals
    "Data Structures": "cs_fundamentals",
    "Algorithms": "cs_fundamentals",
    "OOP": "cs_fundamentals",
    "DBMS": "cs_fundamentals",
    "Operating Systems": "cs_fundamentals",

    # Design
    "Figma": "design",
    "Adobe XD": "design",
    "Wireframing": "design",
    "Prototyping": "design",
    "User Research": "design",
    "Design Systems": "design",
    "UI/UX Design": "design",

    # Business and marketing
    "Agile": "business",
    "Scrum": "business",
    "Market Research": "business",
    "Financial Modeling": "business",
    "SEO": "business",
    "Google Analytics": "business",
    "Social Media Marketing": "business",
    "Content Writing": "business",

    # Soft skills
    "Communication": "soft_skill",
    "Teamwork": "soft_skill",
    "Leadership": "soft_skill",
    "Problem Solving": "soft_skill",
    "Time Management": "soft_skill",
    "Adaptability": "soft_skill",
    "Critical Thinking": "soft_skill",
    "Creativity": "soft_skill",
    "Collaboration": "soft_skill",
    "Decision Making": "soft_skill",
    "Public Speaking": "soft_skill",
    "Analytical Thinking": "soft_skill",
    "Interpersonal Skills": "soft_skill",
    "Conflict Resolution": "soft_skill",
}


# alias -> canonical name (keys are compared after compaction)
SKILL_ALIASES: dict[str, str] = {
    "py": "Python",
    "python3": "Python",
    "core java": "Java",
    "cpp": "C++",
    "c plus plus": "C++",
    "csharp": "C#",
    "js": "JavaScript",
    "es6": "JavaScript",
    "ts": "TypeScript",
    "golang": "Go",
    "html5": "HTML",
    "css3": "CSS",
    "react.js": "React",
    "reactjs": "React",
    "react js": "React",
    "react-native": "React Native",
    "angularjs": "Angular",
    "angular.js": "Angular",
    "vue.js": "Vue",
    "vuejs": "Vue",
    "nextjs": "Next.js",
    "node": "Node.js",
    "nodejs": "Node.js",
    "express": "Express.js",
    "expressjs": "Express.js",
    "springboot": "Spring Boot",
    "spring": "Spring Boot",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "dotnet": ".NET",
    "asp.net": ".NET",
    "rest": "REST API",
    "rest apis": "REST API",
    "restful api": "REST API",
    "restful apis": "REST API",
    "restful services": "REST API",
    "postgres": "PostgreSQL",
    "postgre sql": "PostgreSQL",
    "mongo": "MongoDB",
    "ms sql": "SQL",
    "sql server": "SQL",
    "amazon web services": "AWS",
    "microsoft azure": "Azure",
    "google cloud": "GCP",
    "google cloud platform": "GCP",
    "k8s": "Kubernetes",
    "ci cd": "CI/CD",
    "continuous integration": "CI/CD",
    "linux administration": "Linux",
    "computer networks": "Networking",
    "computer networking": "Networking",
    "ml": "Machine Learning",
    "dl": "Deep Learning",
    "natural language processing": "NLP",
    "tensor flow": "TensorFlow",
    "sklearn": "Scikit-learn",
    "scikit learn": "Scikit-learn",
    "numpy": "NumPy",
    "data analytics": "Data Analysis",
    "ms excel": "Excel",
    "microsoft excel": "Excel",
    "advanced excel": "Excel",
    "powerbi": "Power BI",
    "genai": "Generative AI",
    "large language models": "LLM",
    "llms": "LLM",
    "github actions": "CI/CD",
    "jira": "JIRA",
    "vscode": "VS Code",
    "visual studio code": "VS Code",
    "colab": "Google Colab",
    "jupyter notebook": "Jupyter",
    "selenium webdriver": "Selenium",
    "dsa": "Data Structures",
    "data structures and algorithms": "Data Structures",
    "object oriented programming": "OOP",
    "oops": "OOP",
    "database management systems": "DBMS",
    "os": "Operating Systems",
    "ui/ux": "UI/UX Design",
    "ui ux": "UI/UX Design",
    "ux design": "UI/UX Design",
    "ui design": "UI/UX Design",
    "adobexd": "Adobe XD",
    "wireframes": "Wireframing",
    "prototypes": "Prototyping",
    "agile methodology": "Agile",
    "search engine optimization": "SEO",
    "social media": "Social Media Marketing",
    "copywriting": "Content Writing",
    "communication skills": "Communication",
    "verbal communication": "Communication",
    "written communication": "Communication",
    "team work": "Teamwork",
    "team player": "Teamwork",
    "problem-solving": "Problem Solving",
    "problem solver": "Problem Solving",
    "decision-making": "Decision Making",
    "time-management": "Time Management",
    "team leadership": "Leadership",
}


# Values that are never skills on their own.
NOISE_VALUES: frozenset[str] = frozenset({
    "basic", "basics", "beginner", "intermediate", "advanced", "expert",
    "proficient", "familiar", "knowledge", "working knowledge",
    "skill", "skills", "technical skills", "soft skills", "tools",
    "technologies", "others", "other", "etc", "and", "languages",
    "programming languages", "web technologies", "databases",
    "frameworks", "libraries", "platforms", "tools and platforms",
    "n/a", "na", "none",
})

MAX_SKILL_LENGTH = 60


# ============================================================
# KEY HELPERS
# ============================================================

def compact_key(value: str) -> str:
    """Case-insensitive key that ignores spacing and separators.

    ``"A WS"``, ``"aws"`` and ``"A.W.S"`` all become ``"aws"``.
    ``+`` and ``#`` are kept so C, C++ and C# stay distinct.
    """
    return re.sub(r"[^0-9a-z+#]", "", value.casefold())


def _clean_display(value: str) -> str:
    value = value.strip().strip("-–—•▪*:;,. ").strip()
    return re.sub(r"\s+", " ", value)


def _build_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}

    for canonical in SKILL_CATALOG:
        lookup[compact_key(canonical)] = canonical

    for alias, canonical in SKILL_ALIASES.items():
        if canonical not in SKILL_CATALOG:
            raise ValueError(f"Alias target not in catalog: {canonical}")
        lookup.setdefault(compact_key(alias), canonical)

    return lookup


_LOOKUP = _build_lookup()
_NOISE_KEYS = frozenset(compact_key(v) for v in NOISE_VALUES)


# ============================================================
# PUBLIC API
# ============================================================

@dataclass(frozen=True)
class NormalizedSkill:
    name: str
    category: str
    raw: str
    source: str | None = None

    @property
    def is_known(self) -> bool:
        return self.category != CATEGORY_OTHER


def normalize_skill(raw: str, source: str | None = None) -> NormalizedSkill | None:
    """Normalize one raw skill string. Returns ``None`` for noise."""

    if not isinstance(raw, str):
        return None

    display = _clean_display(raw)

    if not display or len(display) > MAX_SKILL_LENGTH:
        return None

    key = compact_key(display)

    # Nothing meaningful left, pure numbers, or a noise word.
    if not key or key.isdigit() or key in _NOISE_KEYS:
        return None

    canonical = _LOOKUP.get(key)

    if canonical:
        return NormalizedSkill(
            name=canonical,
            category=SKILL_CATALOG[canonical],
            raw=raw,
            source=source,
        )

    return NormalizedSkill(
        name=display,
        category=CATEGORY_OTHER,
        raw=raw,
        source=source,
    )


def normalize_skills(
    values: Iterable[str], source: str | None = None
) -> list[NormalizedSkill]:
    """Normalize many values, de-duplicated case-insensitively."""

    result: list[NormalizedSkill] = []
    seen: set[str] = set()

    for value in values or []:
        skill = normalize_skill(value, source=source)

        if skill is None:
            continue

        key = skill.name.casefold()

        if key not in seen:
            seen.add(key)
            result.append(skill)

    return result


# Order matters: the first section that mentions a skill is recorded
# as its source.
SKILL_SOURCE_FIELDS = ("technical_skills", "soft_skills", "skills")


def normalize_extracted_skills(
    extracted_data: dict[str, Any],
) -> list[NormalizedSkill]:
    """Normalize every skill list in a parser ``extracted_data`` dict."""

    result: list[NormalizedSkill] = []
    seen: set[str] = set()

    for field in SKILL_SOURCE_FIELDS:
        values = extracted_data.get(field) or []

        if not isinstance(values, list):
            continue

        for skill in normalize_skills(values, source=field):
            key = skill.name.casefold()

            if key not in seen:
                seen.add(key)
                result.append(skill)

    return result
