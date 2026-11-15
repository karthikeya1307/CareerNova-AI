"""Ten synthetic candidate profiles for the RAG matching evaluation.

All names, e-mail addresses and phone numbers are fictional placeholders.
Each profile is rendered as a real DOCX resume and parsed by the
application's own resume parser, so the evaluation exercises the full
pipeline (parsing -> normalization -> embedding -> retrieval -> scoring).

``profile_degree`` / ``profile_location`` simulate what the student typed
into their profile page. ``None`` means the field was left empty, in which
case the system falls back to the resume (or reports missing data).
``expected_domains`` is the evaluator's judgement of relevant internship
domains, used only to flag weak recommendations; it is never given to
the matching system.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field

from docx import Document


@dataclass(frozen=True)
class SyntheticProfile:
    key: str
    scenario: str
    name: str
    summary: str | None
    skills: list[str]
    education: str | None
    experience: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    profile_degree: str | None = None
    profile_location: str | None = None
    expected_domains: tuple[str, ...] = ()

    def resume_lines(self) -> list[str]:
        number = self.key.split("_")[0]
        lines = [self.name, f"candidate{number}@example.com | +91 90000 000{number}"]
        if self.summary:
            lines += ["SUMMARY", self.summary]
        if self.skills:
            lines += ["SKILLS", ", ".join(self.skills)]
        if self.education:
            lines += ["EDUCATION", self.education]
        if self.experience:
            lines += ["EXPERIENCE", *self.experience]
        if self.projects:
            lines += ["PROJECTS", *self.projects]
        return lines

    def to_docx(self) -> bytes:
        document = Document()
        for line in self.resume_lines():
            document.add_paragraph(line)
        buffer = io.BytesIO()
        document.save(buffer)
        return buffer.getvalue()


PROFILES: list[SyntheticProfile] = [
    SyntheticProfile(
        key="01_ai_ml",
        scenario="AI/ML candidate",
        name="Candidate One",
        summary="Machine learning enthusiast building deep learning models for computer vision.",
        skills=["Python", "TensorFlow", "PyTorch", "Deep Learning", "Machine Learning",
                "NumPy", "Computer Vision"],
        education="B.Tech Computer Science and Engineering, Example Institute of Technology, 2026",
        projects=["Image Classifier", "Trained a CNN with PyTorch to classify plant diseases."],
        profile_degree="B.Tech Computer Science", profile_location="Bengaluru",
        expected_domains=("Data Science",),
    ),
    SyntheticProfile(
        key="02_backend",
        scenario="Backend developer",
        name="Candidate Two",
        summary="Backend developer who designs REST APIs and relational databases.",
        skills=["Python", "FastAPI", "Django", "PostgreSQL", "REST API", "Docker", "Git"],
        education="B.Tech Information Technology, Example Institute of Technology, 2026",
        profile_degree="B.Tech IT", profile_location="Pune",
        expected_domains=("Software Development", "Web Development"),
    ),
    SyntheticProfile(
        key="03_data_science",
        scenario="Data Science candidate",
        name="Candidate Three",
        summary="Aspiring data scientist working on statistical analysis and dashboards.",
        skills=["Python", "Pandas", "NumPy", "Scikit-learn", "Statistics", "SQL", "Tableau"],
        education="B.Sc Statistics, Example College of Science, 2026",
        profile_degree="B.Sc Statistics", profile_location="Hyderabad",
        expected_domains=("Data Science", "Business Analysis"),
    ),
    SyntheticProfile(
        key="04_generative_ai",
        scenario="Generative AI candidate",
        name="Candidate Four",
        summary="Builds LLM applications with retrieval-augmented generation and prompt engineering.",
        skills=["Python", "LLM", "Generative AI", "NLP", "PyTorch", "Prompt Engineering", "LangChain"],
        education="M.Tech Computer Science, Example Institute of Technology, 2026",
        projects=["RAG Chatbot", "Built a document question-answering bot with embeddings and a vector store."],
        profile_degree="M.Tech CSE", profile_location="Chennai",
        expected_domains=("Data Science",),
    ),
    SyntheticProfile(
        key="05_multi_language",
        scenario="Candidate with multiple programming skills",
        name="Candidate Five",
        summary="Versatile programmer comfortable across several languages.",
        skills=["Java", "Python", "C++", "JavaScript", "Kotlin", "Go", "SQL", "Git"],
        education="B.Tech Computer Science, Example Institute of Technology, 2026",
        profile_degree="B.Tech CSE", profile_location="Noida",
        expected_domains=("Software Development", "Web Development", "Mobile Development"),
    ),
    SyntheticProfile(
        key="06_strong_education",
        scenario="Candidate with strong educational qualifications",
        name="Candidate Six",
        summary="Postgraduate researcher with a gold medal and a strong algorithms background.",
        skills=["Python", "Data Structures", "Algorithms", "Machine Learning"],
        education="M.Tech Computer Science (Gold Medal, CGPA 9.6), Example Institute of Technology, 2026",
        profile_degree=None, profile_location="Kolkata",   # degree read from resume
        expected_domains=("Data Science", "Software Development"),
    ),
    SyntheticProfile(
        key="07_relevant_experience",
        scenario="Candidate with relevant experience",
        name="Candidate Seven",
        summary="QA engineer focused on automated testing.",
        skills=["Selenium", "Java", "JIRA", "Agile", "SQL"],
        education="BCA, Example College of Computer Applications, 2025",
        experience=["QA Automation Intern, Example Testing Labs, 2024-2025",
                    "Automated 300 regression test cases with Selenium and Java; tracked defects in JIRA."],
        profile_degree=None, profile_location="Chennai",
        expected_domains=("QA/Testing",),
    ),
    SyntheticProfile(
        key="08_academic_projects",
        scenario="Candidate with relevant academic projects",
        name="Candidate Eight",
        summary="Final-year student interested in product design.",
        skills=["Figma", "HTML", "CSS"],
        education="B.Sc Computer Science, Example College of Science, 2026",
        projects=["Campus App Redesign",
                  "Created wireframes and interactive prototypes in Figma after user research interviews.",
                  "Design System", "Built a reusable component library with consistent typography."],
        profile_degree=None, profile_location=None,
        expected_domains=("UI/UX Design", "Web Development"),
    ),
    SyntheticProfile(
        key="09_partial_overlap",
        scenario="Candidate with partial skill overlap",
        name="Candidate Nine",
        summary="Commerce graduate moving into IT support and analytics.",
        skills=["Linux", "Excel", "Communication", "Networking"],
        education="B.Com, Example Commerce College, 2025",
        profile_degree="B.Com", profile_location="Jaipur",
        expected_domains=("Cybersecurity", "DevOps/Cloud", "Business Analysis"),
    ),
    SyntheticProfile(
        key="10_limited_information",
        scenario="Candidate with limited or missing information",
        name="Candidate Ten",
        summary=None,
        skills=["Communication"],
        education=None,
        profile_degree=None, profile_location=None,
        expected_domains=(),
    ),
]
