"""Natural-language internship search ("Java developer internships for freshers", "Remote React internships",
"Entry-level AI/ML jobs in Hyderabad").

Reuses the existing pieces instead of replacing them:
* ``vector_index.search`` (MiniLM embeddings over the internship knowledge base) for meaning;
* ``fact_check.skill_mentions`` (the skill catalogue) to recognise skills in the query;
* the internships' own skills, titles, domains, locations and work modes for exact matching.

What changed compared with the plain vector search (the root cause of "search returns unrelated jobs"):
1. The query is interpreted: skills, role words, location, work mode, internship/job, fresher level.
2. Location and work mode the student asked for are applied as filters.
3. A result must actually be relevant: it has a requested skill (or the skill in its title), or a requested role word
   in its title/domain, or - when the query names neither - a high semantic similarity. Unrelated queries
   ("pizza delivery driver") therefore return nothing, with an explanation, instead of the nearest k postings.
4. When the embedding model or the index is unavailable, the same rules run on keywords only (no crash, no 503).

Nothing is invented: every result is an existing active internship from the database.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.models import Internship, InternshipSkill
from backend.services.fact_check import skill_mentions

SEMANTIC_FLOOR = 0.50          # minimum cosine similarity when the query names no skill/role we can check exactly
SEMANTIC_SUPPORT = 0.40        # similarity that supports a keyword match
WORK_MODES = {"remote": "Remote", "work from home": "Remote", "wfh": "Remote", "hybrid": "Hybrid",
              "onsite": "Onsite", "on-site": "Onsite", "on site": "Onsite", "in office": "Onsite", "office": "Onsite"}
# Role vocabulary -> words that must appear in a posting's title, domain or skills.
ROLE_SYNONYMS = {
    "ai/ml": ["ai", "machine learning", "ml", "artificial intelligence", "deep learning", "data science"],
    "ai": ["ai", "artificial intelligence", "machine learning", "generative ai"],
    "ml": ["machine learning", "ml"],
    "machine learning": ["machine learning", "ml", "ai"],
    "data science": ["data science", "data scientist", "machine learning"],
    "data analyst": ["data analyst", "data analysis", "analytics"],
    "data analytics": ["data analyst", "data analysis", "analytics"],
    "software engineering": ["software engineering", "software engineer", "software developer", "software development"],
    "software developer": ["software developer", "software engineering", "software development"],
    "software engineer": ["software engineer", "software engineering"],
    "full stack": ["full stack", "full-stack", "fullstack"],
    "full-stack": ["full stack", "full-stack", "fullstack"],
    "frontend": ["frontend", "front-end", "front end", "react", "web"],
    "front-end": ["frontend", "front-end", "front end"],
    "backend": ["backend", "back-end", "back end", "api"],
    "back-end": ["backend", "back-end", "back end"],
    "web developer": ["web", "frontend", "full stack"],
    "web development": ["web", "frontend", "full stack"],
    "devops": ["devops", "cloud", "kubernetes", "docker"],
    "cloud": ["cloud", "aws", "azure", "devops"],
    "cybersecurity": ["cybersecurity", "security"],
    "security": ["security", "cybersecurity"],
    "mobile": ["mobile", "android", "ios", "flutter"],
    "android": ["android", "mobile"],
    "ui/ux": ["ui", "ux", "design"],
    "marketing": ["marketing"],
    "content": ["content"],
    "seo": ["seo"],
    "finance": ["finance"],
    "operations": ["operations"],
    "research": ["research"],
}
FILLER = set("""a an and the for in at on of to with from near my me i am looking want need find show give any some
internship internships intern interns job jobs role roles position positions opening openings vacancy vacancies work
fresher freshers fresh graduate graduates student students entry entry-level level beginner beginners junior trainee
trainees opportunity opportunities paid unpaid part full time remote hybrid onsite on-site office home wfh based""".split())
WEAK_ROLE_WORDS = {"developer", "developers", "engineer", "engineers", "engineering", "development", "programmer"}
LEVEL_WORDS = re.compile(r"\b(fresher|freshers|entry[- ]level|beginner|junior|graduate|no experience|0 years)\b", re.I)
JOB_WORDS = re.compile(r"\b(job|jobs|full[- ]time role|position|positions|vacanc(y|ies))\b", re.I)


@dataclass
class Interpretation:
    text: str
    skills: list[str] = field(default_factory=list)
    roles: list[str] = field(default_factory=list)          # specific role phrases ("software engineering", "ai/ml")
    words: list[str] = field(default_factory=list)          # other content words
    location: str | None = None
    work_mode: str | None = None
    asks_for_jobs: bool = False
    fresher: bool = False

    def as_dict(self) -> dict:
        return {"skills": self.skills, "roles": self.roles, "keywords": self.words, "location": self.location,
                "work_mode": self.work_mode, "opportunity": "job" if self.asks_for_jobs else "internship",
                "experience_level": "fresher / entry level" if self.fresher else None}


@dataclass
class Result:
    internship: Internship
    score: float
    similarity: float | None
    reasons: list[str]
    in_title: bool = False


def _cities(db: Session) -> list[str]:
    cities = set()
    for (location,) in db.execute(select(Internship.location).where(Internship.is_active.is_(True))):
        if location:
            cities.add(location.split(",")[0].strip())
    return sorted((c for c in cities if c and c.casefold() != "remote"), key=len, reverse=True)


def interpret(text: str, cities: list[str]) -> Interpretation:
    raw = " ".join((text or "").split())
    low = raw.casefold()
    it = Interpretation(text=raw)
    it.skills = sorted(skill_mentions(raw))
    for phrase, mode in sorted(WORK_MODES.items(), key=lambda kv: -len(kv[0])):
        if re.search(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", low):
            it.work_mode = mode
            break
    for city in cities:
        if re.search(rf"\b{re.escape(city.casefold())}\b", low):
            it.location = city
            break
    it.asks_for_jobs = bool(JOB_WORDS.search(low))
    it.fresher = bool(LEVEL_WORDS.search(low))
    rest = low
    for phrase in sorted(ROLE_SYNONYMS, key=len, reverse=True):
        if re.search(rf"(?<![\w/]){re.escape(phrase)}(?![\w/])", rest):
            it.roles.append(phrase)
            rest = re.sub(rf"(?<![\w/]){re.escape(phrase)}(?![\w/])", " ", rest)
    skill_words = {w for s in it.skills for w in re.findall(r"[a-z0-9+#.]+", s.casefold())}
    city_words = set(re.findall(r"[a-z]+", (it.location or "").casefold()))
    for word in re.findall(r"[a-z0-9+#./-]+", rest):
        word = word.strip(".-/")
        if (len(word) >= 2 and word not in FILLER and word not in skill_words and word not in city_words
                and word not in WEAK_ROLE_WORDS and not word.isdigit()):
            it.words.append(word)
    return it


def _haystack(i: Internship) -> tuple[str, str, set[str]]:
    """(title + domain, title + domain + company, skills). Skills and roles are matched against the posting itself;
    the company name is used only for plain words ("internships at <company>"), so a company called "... AI Ltd"
    does not turn an iOS posting into an AI/ML match."""
    skills = {link.skill.name.casefold() for link in i.skill_links if link.skill}
    title_domain = f" {i.title} {i.domain or ''} ".casefold()
    return title_domain, f"{title_domain}{i.company} ".casefold(), skills


def _contains(text: str, term: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(term.casefold())}(?![a-z0-9])", text) is not None


def search(db: Session, text: str, k: int, embedder=None) -> tuple[Interpretation, list[Result], str, str | None]:
    """(interpretation, results, mode, message). ``mode`` is "hybrid" or "keyword" (model/index unavailable)."""
    from backend.services import vector_index

    it = interpret(text, _cities(db))
    rows = list(db.scalars(select(Internship).where(Internship.is_active.is_(True))
                           .options(selectinload(Internship.skill_links).selectinload(InternshipSkill.skill))))
    similarity: dict[int, float] = {}
    mode = "keyword"
    if embedder is not None:
        try:
            for hit in vector_index.search(db, it.text, max(len(rows), 1), embedder):
                similarity[hit.internship.internship_id] = hit.similarity
            active = {r.internship_id for r in rows}
            mode = "hybrid" if similarity.keys() & active else "keyword"     # a stale index matches nothing
        except Exception:                      # index not built / model failure: keyword rules still apply
            similarity, mode = {}, "keyword"

    specific = bool(it.skills or it.roles or it.words)
    results: list[Result] = []
    for i in rows:
        title_domain, with_company, skills = _haystack(i)
        reasons: list[str] = []
        # Filters the student asked for.
        if it.location:
            loc = (i.location or "").casefold()
            if it.location.casefold() not in loc:
                continue
            reasons.append(f"in {it.location}")
        if it.work_mode:
            # The structured work_mode is authoritative (a few curated postings say location "Remote" but are
            # Onsite/Hybrid; showing them for a remote search would contradict their own work-mode badge).
            if (i.work_mode or "") != it.work_mode:
                continue
            reasons.append(f"{it.work_mode.lower()} work mode")
        # Relevance.
        skill_hits = [s for s in it.skills if s.casefold() in skills or _contains(title_domain, s)]
        role_hits = [r for r in it.roles if any(_contains(title_domain, syn) or syn in skills for syn in ROLE_SYNONYMS[r])]
        word_hits = [w for w in it.words if _contains(with_company, w) or w in skills]
        sim = similarity.get(i.internship_id)
        if it.skills and not skill_hits:
            continue                                            # asked for Java: no posting without Java
        if not it.skills and it.roles and not role_hits:
            continue
        if not it.skills and not it.roles and it.words:
            if not word_hits and (sim is None or sim < SEMANTIC_FLOOR):
                continue
        if not specific and sim is not None and not (it.location or it.work_mode):
            if sim < SEMANTIC_FLOOR:
                continue
        if not specific and not (it.location or it.work_mode) and sim is None:
            continue                                            # nothing to match on
        parts = []
        if it.skills:
            parts.append(len(skill_hits) / len(it.skills))
            reasons.insert(0, "skills: " + ", ".join(skill_hits))
        if it.roles:
            parts.append(len(role_hits) / len(it.roles))
            if role_hits:
                reasons.insert(0, "role: " + ", ".join(role_hits))
        if it.words:
            parts.append(len(word_hits) / len(it.words))
            if word_hits:
                reasons.append("mentions: " + ", ".join(word_hits))
        exact = sum(parts) / len(parts) if parts else 1.0
        score = 0.6 * exact + 0.4 * sim if sim is not None else exact
        if sim is not None and sim >= SEMANTIC_SUPPORT:
            reasons.append(f"similar meaning ({round(sim * 100)}%)")
        title = f" {i.title} ".casefold()
        in_title = any(_contains(title, s) for s in it.skills) or any(
            _contains(title, syn) for r in role_hits for syn in ROLE_SYNONYMS[r])
        results.append(Result(i, round(score, 4), sim, reasons, in_title))

    # Equal scores: postings whose title names the skill/role ("Java Developer Intern") before ones that only list it.
    results.sort(key=lambda r: (-r.score, not r.in_title, -(r.similarity or 0), r.internship.internship_id))
    seen, unique = set(), []
    for r in results:                                           # same posting imported twice: show once
        key = (r.internship.title.casefold(), r.internship.company.casefold(), (r.internship.location or "").casefold())
        if key not in seen:
            seen.add(key)
            unique.append(r)
    message = None
    if not unique:
        if not rows:
            message = "There are no active internships in the catalogue yet."
        elif it.location or it.work_mode:
            message = ("No internships match all of: " + ", ".join(filter(None, [
                ", ".join(it.skills + it.roles) or None, it.location, it.work_mode and it.work_mode.lower()]))
                + ". Try removing the location or work mode, or browse all internships.")
        else:
            message = ("No internships in the catalogue match this search. Try a role (e.g. \"data analyst\"), "
                       "a skill (e.g. \"Python\") or a domain, or browse all internships.")
    elif it.asks_for_jobs:
        message = "CareerNova's catalogue lists internships only, so these are internships that match your search."
    return it, unique[:k], mode, message
