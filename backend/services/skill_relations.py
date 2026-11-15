"""Curated relationships between canonical skills (for partial matches).

A required skill counts as *partially matched* when the candidate does
not have it but has a closely related skill whose knowledge transfers
(e.g. MySQL for PostgreSQL, PyTorch for TensorFlow). Partial matches are
reported by skill-gap analysis only; they never change the Phase 3
compatibility score.

Every name here must be a canonical name from
``skill_normalizer.SKILL_CATALOG`` (verified by tests). Relations are
symmetric.
"""

from __future__ import annotations

from backend.services.skill_normalizer import SKILL_CATALOG

RELATIONS_VERSION = "2026.11-v1"

# (skill_a, skill_b, why knowledge transfers)
RELATED_SKILL_PAIRS: list[tuple[str, str, str]] = [
    # Languages
    ("JavaScript", "TypeScript", "TypeScript is a typed superset of JavaScript"),
    ("C", "C++", "C++ builds on C syntax and memory concepts"),
    ("Java", "Kotlin", "both run on the JVM with similar object models"),
    ("Kotlin", "Swift", "both are modern mobile-first languages with similar syntax"),
    ("C#", ".NET", "C# is the main language of .NET"),
    ("Linux", "Bash", "Bash is the standard Linux shell"),
    # Web frameworks
    ("React", "React Native", "React Native uses React's component model"),
    ("React", "Next.js", "Next.js is a React framework"),
    ("React", "Vue", "both are component-based UI libraries"),
    ("React", "Angular", "both are component-based UI frameworks"),
    ("Vue", "Angular", "both are component-based UI frameworks"),
    ("Node.js", "Express.js", "Express.js runs on Node.js"),
    ("Django", "Flask", "both are Python web frameworks"),
    ("Django", "FastAPI", "both are Python web frameworks"),
    ("Flask", "FastAPI", "both are lightweight Python web frameworks"),
    ("CSS", "Tailwind CSS", "Tailwind CSS is a CSS utility framework"),
    ("CSS", "Bootstrap", "Bootstrap is a CSS framework"),
    ("Tailwind CSS", "Bootstrap", "both are CSS frameworks"),
    ("REST API", "GraphQL", "both are web API styles"),
    ("Java", "Spring Boot", "Spring Boot is a Java framework"),
    ("React Native", "Flutter", "both are cross-platform mobile frameworks"),
    # Databases
    ("SQL", "MySQL", "MySQL is queried with SQL"),
    ("SQL", "PostgreSQL", "PostgreSQL is queried with SQL"),
    ("SQL", "SQLite", "SQLite is queried with SQL"),
    ("SQL", "Oracle", "Oracle is queried with SQL"),
    ("MySQL", "PostgreSQL", "both are relational SQL databases"),
    ("PostgreSQL", "SQLite", "both are relational SQL databases"),
    ("MongoDB", "Firebase", "both are document-oriented NoSQL stores"),
    # Cloud and DevOps
    ("AWS", "Azure", "both are major public clouds with equivalent services"),
    ("AWS", "GCP", "both are major public clouds with equivalent services"),
    ("Azure", "GCP", "both are major public clouds with equivalent services"),
    ("Docker", "Kubernetes", "Kubernetes orchestrates containers such as Docker"),
    ("Jenkins", "CI/CD", "Jenkins is a CI/CD tool"),
    ("Git", "GitHub", "GitHub hosts Git repositories"),
    ("Git", "GitLab", "GitLab hosts Git repositories"),
    # Data and ML
    ("TensorFlow", "PyTorch", "both are deep learning frameworks"),
    ("TensorFlow", "Keras", "Keras is TensorFlow's high-level API"),
    ("PyTorch", "Keras", "both are deep learning frameworks"),
    ("Machine Learning", "Deep Learning", "deep learning is a branch of machine learning"),
    ("Machine Learning", "Scikit-learn", "Scikit-learn is a machine learning library"),
    ("Deep Learning", "Computer Vision", "modern computer vision relies on deep learning"),
    ("Deep Learning", "NLP", "modern NLP relies on deep learning"),
    ("NLP", "LLM", "LLMs are large NLP models"),
    ("LLM", "Generative AI", "LLMs are generative AI models"),
    ("Pandas", "NumPy", "Pandas is built on NumPy"),
    ("Data Analysis", "Statistics", "data analysis applies statistics"),
    ("Data Analysis", "Pandas", "Pandas is a data analysis library"),
    ("Excel", "Power BI", "both are business analytics tools"),
    ("Excel", "Tableau", "both are business analytics tools"),
    ("Power BI", "Tableau", "both are BI dashboard tools"),
    ("Data Visualization", "Tableau", "Tableau is a data visualization tool"),
    ("Data Visualization", "Power BI", "Power BI is a data visualization tool"),
    ("Data Visualization", "Matplotlib", "Matplotlib is a visualization library"),
    # Fundamentals, design, testing, process, marketing
    ("Data Structures", "Algorithms", "taught and practised together"),
    ("Figma", "Adobe XD", "both are UI design tools"),
    ("Wireframing", "Prototyping", "prototypes are built from wireframes"),
    ("Figma", "Prototyping", "Figma is commonly used for prototyping"),
    ("UI/UX Design", "Figma", "Figma is a core UI/UX design tool"),
    ("Selenium", "Unit Testing", "both are automated testing practices"),
    ("Agile", "Scrum", "Scrum is an Agile framework"),
    ("Agile", "JIRA", "JIRA is commonly used to run Agile work"),
    ("SEO", "Google Analytics", "SEO work is measured with web analytics"),
    ("Social Media Marketing", "Content Writing", "social media marketing relies on content"),
]


def _build_index() -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for a, b, why in RELATED_SKILL_PAIRS:
        for name in (a, b):
            if name not in SKILL_CATALOG:
                raise ValueError(f"Related skill not in catalog: {name}")
        index.setdefault(a, {})[b] = why
        index.setdefault(b, {})[a] = why
    return index


_RELATED = _build_index()


def related_skills(skill: str) -> dict[str, str]:
    """Canonical skills related to ``skill`` -> reason."""
    return dict(_RELATED.get(skill, {}))


def find_related_in(skill: str, candidate_skills) -> list[tuple[str, str]]:
    """Candidate skills related to ``skill`` as (skill, reason), sorted."""
    have = {s.casefold(): s for s in candidate_skills}
    related = _RELATED.get(skill, {})
    return sorted(
        (have[name.casefold()], why) for name, why in related.items()
        if name.casefold() in have
    )
