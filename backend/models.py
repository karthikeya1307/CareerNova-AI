import uuid

from datetime import datetime
from typing import Any


from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    CheckConstraint,
    JSON,
    Uuid,
    text,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


# ============================================================
# BASE CLASS
# All SQLAlchemy models inherit from Base.
# ============================================================

class Base(DeclarativeBase):
    pass


# ============================================================
# MODULE 1: STUDENT PROFILE AND RESUME MANAGEMENT
# ============================================================

class User(Base):
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint(
            "user_uuid",
            name="uq_users_user_uuid"
        ),
        # Keep in sync with backend/utils/roles.VALID_ROLES.
        CheckConstraint(
            "role IN ('student', 'admin', 'super_admin')",
            name="ck_users_role"
        ),
        # At most one super admin, enforced by the database.
        Index(
            "uq_users_single_super_admin",
            "role",
            unique=True,
            postgresql_where=text("role = 'super_admin'"),
        ),
    )
    user_id: Mapped[int] = mapped_column(primary_key=True)

    user_uuid: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        unique=True,
        nullable=False
    )

    first_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    last_name: Mapped[str] = mapped_column(
        String(100), nullable=False
    )

    phone_number: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True
    )

    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )

    password_hash: Mapped[str] = mapped_column(
        String(255), nullable=False
    )

    role: Mapped[str] = mapped_column(
        String(30),
        default="student",
        server_default=text("'student'"),
        nullable=False
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        nullable=False
    )

    # Deactivated accounts cannot sign in or use any API; their data is kept.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False
    )

    deactivated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )
    
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    recommendations: Mapped[list["SkillGapRecommendation"]] = (
        relationship(
            back_populates="user",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )
    )

    generated_documents: Mapped[list["GeneratedDocument"]] = (
        relationship(
            back_populates="user",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )
    )

    interview_sessions: Mapped[list["InterviewSession"]] = (
        relationship(
            back_populates="user",
            cascade="all, delete-orphan",
            passive_deletes=True,
        )
    )

    applications: Mapped[list["Application"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    saved_internships: Mapped[list["SavedInternship"]] = relationship(
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class StudentProfile(Base):
    __tablename__ = "student_profiles"

    profile_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )

    college: Mapped[str | None] = mapped_column(String(200))
    degree: Mapped[str | None] = mapped_column(String(150))
    graduation_year: Mapped[int | None] = mapped_column(Integer)
    location: Mapped[str | None] = mapped_column(String(150))
    # Profile enhancement: a short professional introduction and an optional profile picture
    # (stored under uploads/avatars/<user id>/, served only to its owner).
    bio: Mapped[str | None] = mapped_column(Text)
    avatar_path: Mapped[str | None] = mapped_column(String(500))
    avatar_content_type: Mapped[str | None] = mapped_column(String(30))
    avatar_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def has_avatar(self) -> bool:
        return bool(self.avatar_path)

    user: Mapped["User"] = relationship(
        back_populates="profile"
    )


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (
        Index("uq_resumes_one_preferred_per_user", "user_id", unique=True,
              postgresql_where=text("is_preferred")),
    )

    resume_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    filename: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    file_path: Mapped[str] = mapped_column(
        String(500), nullable=False
    )
    file_type: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="uploaded", nullable=False
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    # Resume versions: an optional name ("Internship-focused") and the student's preferred/current version
    # (at most one per student; NULL label and false = the previous behaviour).
    label: Mapped[str | None] = mapped_column(String(120))
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"), default=False)

    user: Mapped["User"] = relationship(
        back_populates="resumes"
    )

    extractions: Mapped[list["ResumeExtraction"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    resume_skills: Mapped[list["ResumeSkill"]] = relationship(
        back_populates="resume",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="resume",
        passive_deletes=True,
    )

    generated_documents: Mapped[list["GeneratedDocument"]] = (
        relationship(back_populates="resume")
    )


# ============================================================
# MODULE 2: RESUME PARSING AND SKILL EXTRACTION
# ============================================================

class ResumeExtraction(Base):
    __tablename__ = "resume_extractions"

    extraction_id: Mapped[int] = mapped_column(primary_key=True)

    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    parser_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    extracted_data: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="completed", nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    resume: Mapped["Resume"] = relationship(
        back_populates="extractions"
    )


class Skill(Base):
    __tablename__ = "skills"

    skill_id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    category: Mapped[str | None] = mapped_column(String(80))

    resume_links: Mapped[list["ResumeSkill"]] = relationship(
        back_populates="skill",
        passive_deletes=True,
    )

    internship_links: Mapped[list["InternshipSkill"]] = (
        relationship(
            back_populates="skill",
            passive_deletes=True,
        )
    )

    recommendations: Mapped[list["SkillGapRecommendation"]] = (
        relationship(
            back_populates="skill",
            passive_deletes=True,
        )
    )


# Skill names are unique regardless of case ("AWS" == "aws").
Index(
    "uq_skills_name_lower",
    func.lower(Skill.name),
    unique=True,
)


class ResumeSkill(Base):
    __tablename__ = "resume_skills"

    # Composite primary key
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        primary_key=True,
    )

    proficiency: Mapped[str | None] = mapped_column(String(30))
    evidence: Mapped[str | None] = mapped_column(Text)

    resume: Mapped["Resume"] = relationship(
        back_populates="resume_skills"
    )
    skill: Mapped["Skill"] = relationship(
        back_populates="resume_links"
    )


# ============================================================
# MODULE 3: INTERNSHIP KNOWLEDGE BASE AND RAG
# ============================================================

class Internship(Base):
    __tablename__ = "internships"

    __table_args__ = (
        CheckConstraint(
            "work_mode IN ('Onsite', 'Hybrid', 'Remote')",
            name="ck_internships_work_mode",
        ),
        CheckConstraint(
            "duration_weeks > 0",
            name="ck_internships_duration_positive",
        ),
        CheckConstraint(
            "stipend_per_month >= 0",
            name="ck_internships_stipend_non_negative",
        ),
        CheckConstraint(
            "source IN ('dataset', 'admin', 'manual')",
            name="ck_internships_source",
        ),
    )

    internship_id: Mapped[int] = mapped_column(primary_key=True)

    # Stable identifier from an external dataset (used for idempotent
    # imports). NULL for internships created by administrators.
    external_id: Mapped[str | None] = mapped_column(
        String(64), unique=True
    )

    title: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    company: Mapped[str] = mapped_column(
        String(200), nullable=False
    )
    description: Mapped[str | None] = mapped_column(Text)
    eligibility: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(150))
    application_url: Mapped[str | None] = mapped_column(
        String(1000)
    )
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    domain: Mapped[str | None] = mapped_column(String(80), index=True)
    work_mode: Mapped[str | None] = mapped_column(String(20))
    duration_weeks: Mapped[int | None] = mapped_column(Integer)
    stipend_per_month: Mapped[int | None] = mapped_column(Integer)
    stipend_currency: Mapped[str] = mapped_column(
        String(3),
        default="INR",
        server_default=text("'INR'"),
        nullable=False,
    )
    min_education: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(
        String(30),
        default="manual",
        server_default=text("'manual'"),
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Job-source tracking (P3). None means "not known" - never guessed.
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)    # where the listing came from
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # sha256 of the normalised "title|company|location", used to spot duplicate listings.
    dedup_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    skill_links: Mapped[list["InternshipSkill"]] = relationship(
        back_populates="internship",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    knowledge_documents: Mapped[list["KnowledgeDocument"]] = (
        relationship(back_populates="internship")
    )

    match_results: Mapped[list["MatchResult"]] = relationship(
        back_populates="internship",
        passive_deletes=True,
    )

    recommendations: Mapped[list["SkillGapRecommendation"]] = (
        relationship(
            back_populates="internship",
            passive_deletes=True,
        )
    )

    applications: Mapped[list["Application"]] = relationship(
        back_populates="internship",
        passive_deletes=True,
    )

    generated_documents: Mapped[list["GeneratedDocument"]] = (
        relationship(
            back_populates="internship",
            passive_deletes=True,
        )
    )

    interview_sessions: Mapped[list["InterviewSession"]] = (
        relationship(
            back_populates="internship",
            passive_deletes=True,
        )
    )


class InternshipSkill(Base):
    __tablename__ = "internship_skills"

    __table_args__ = (
        CheckConstraint(
            "importance IN ('required', 'preferred')",
            name="ck_internship_skills_importance",
        ),
    )

    internship_id: Mapped[int] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="CASCADE"),
        primary_key=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        primary_key=True,
    )

    importance: Mapped[str] = mapped_column(
        String(30), default="required", nullable=False
    )

    internship: Mapped["Internship"] = relationship(
        back_populates="skill_links"
    )
    skill: Mapped["Skill"] = relationship(
        back_populates="internship_links"
    )


class KnowledgeDocument(Base):
    """One indexed text per source (e.g. per internship).

    PostgreSQL is the source of truth; ``document_id`` is the vector ID
    stored in the FAISS index.
    """

    __tablename__ = "knowledge_documents"

    __table_args__ = (
        UniqueConstraint(
            "internship_id",
            "source_type",
            name="uq_knowledge_document_internship_source",
        ),
    )

    document_id: Mapped[int] = mapped_column(primary_key=True)

    internship_id: Mapped[int | None] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="SET NULL"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(
        String(300), nullable=False
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(
        String(1000)
    )
    storage_key: Mapped[str | None] = mapped_column(
        String(500)
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(128), index=True
    )
    indexing_status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )

    # Exact text that was embedded (used for RAG context/citations).
    content: Mapped[str | None] = mapped_column(Text)
    embedding_model: Mapped[str | None] = mapped_column(String(200))
    error_message: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    indexed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    internship: Mapped["Internship | None"] = relationship(
        back_populates="knowledge_documents"
    )


# ============================================================
# MODULE 4: JOB-RESUME MATCHING
# ============================================================

class MatchResult(Base):
    """One scored internship within a matching run.

    ``score`` is the final compatibility score on a 0-100 scale.
    Rows of one request share ``run_id``; earlier runs are kept.
    """

    __tablename__ = "match_results"

    __table_args__ = (
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_match_results_score_range",
        ),
        CheckConstraint(
            "label IN ('Excellent', 'Strong', 'Fair', 'Weak')",
            name="ck_match_results_label",
        ),
        CheckConstraint(
            "data_completeness >= 0 AND data_completeness <= 1",
            name="ck_match_results_completeness_range",
        ),
        UniqueConstraint(
            "run_id",
            "internship_id",
            name="uq_match_results_run_internship",
        ),
        Index(
            "ix_match_results_resume_created",
            "resume_id",
            "created_at",
        ),
    )

    match_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_id: Mapped[int] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="CASCADE"),
        nullable=False,
    )
    internship_id: Mapped[int] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="CASCADE"),
        nullable=False,
    )

    score: Mapped[float] = mapped_column(
        Float, nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(Text)

    # Added in Phase 3 (all nullable: additive migration).
    run_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), index=True
    )
    rank: Mapped[int | None] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(String(20))
    algorithm_version: Mapped[str | None] = mapped_column(String(20))
    skill_score: Mapped[float | None] = mapped_column(Float)
    semantic_score: Mapped[float | None] = mapped_column(Float)
    education_score: Mapped[float | None] = mapped_column(Float)
    location_score: Mapped[float | None] = mapped_column(Float)
    required_skill_coverage: Mapped[float | None] = mapped_column(Float)
    data_completeness: Mapped[float | None] = mapped_column(Float)
    # Full component breakdown, skills and explanation sentences.
    breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="match_results"
    )
    resume: Mapped["Resume"] = relationship(
        back_populates="match_results"
    )
    internship: Mapped["Internship"] = relationship(
        back_populates="match_results"
    )


# ============================================================
# MODULE 5: SKILL GAP ANALYSIS
# ============================================================

class SkillGapRecommendation(Base):
    """One recommended skill for one resume (Phase 4).

    Regenerating recommendations updates the existing row for the same
    (user, resume, skill), preserving the student's progress status.
    """

    __tablename__ = "skill_gap_recommendations"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'in_progress', 'completed', 'dismissed')",
            name="ck_skill_gap_status",
        ),
        CheckConstraint(
            "gap_level IN ('identified', 'missing', 'partial')",
            name="ck_skill_gap_level",
        ),
        CheckConstraint(
            "importance IN ('required', 'preferred')",
            name="ck_skill_gap_importance",
        ),
        CheckConstraint(
            "priority_score >= 0 AND priority_score <= 100",
            name="ck_skill_gap_priority_range",
        ),
        CheckConstraint(
            "completed_via IN ('user', 'resume')",
            name="ck_skill_gap_completed_via",
        ),
        UniqueConstraint(
            "user_id",
            "resume_id",
            "skill_id",
            name="uq_skill_gap_user_resume_skill",
        ),
        Index(
            "ix_skill_gap_user_status",
            "user_id",
            "status",
        ),
    )

    recommendation_id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    skill_id: Mapped[int] = mapped_column(
        ForeignKey("skills.skill_id", ondelete="CASCADE"),
        nullable=False,
    )
    internship_id: Mapped[int | None] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="SET NULL"),
        nullable=True,
    )

    gap_level: Mapped[str] = mapped_column(
        String(30), default="identified", nullable=False
    )
    recommended_action: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(30), default="pending", nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Added in Phase 4 (additive migration).
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="CASCADE"),
        index=True,
    )
    importance: Mapped[str | None] = mapped_column(String(20))
    priority_score: Mapped[float | None] = mapped_column(Float)
    demand_count: Mapped[int | None] = mapped_column(Integer)
    # Internships (ids) in the analysed set that need this skill.
    internship_ids: Mapped[list[int] | None] = mapped_column(JSON)
    # Candidate skills that partially cover this one: [{skill, reason}].
    related_skills: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    learning_plan: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    learning_plan_version: Mapped[str | None] = mapped_column(String(20))
    # "match_run" or "selection"; run id when generated from a match run.
    source: Mapped[str | None] = mapped_column(String(30))
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True))
    # False when the latest analysis no longer includes this skill.
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    completed_via: Mapped[str | None] = mapped_column(String(20))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="recommendations"
    )
    skill: Mapped["Skill"] = relationship(
        back_populates="recommendations"
    )
    internship: Mapped["Internship | None"] = relationship(
        back_populates="recommendations"
    )


# ============================================================
# MODULE 6: RESUME AND COVER LETTER CUSTOMIZATION
# ============================================================

class GeneratedDocument(Base):
    """A customized resume or cover letter (Phase 5).

    ``content`` holds the rendered plain text of the current version and
    ``content_json`` its structured sections. Every save creates a row in
    ``generated_document_versions``.
    """

    __tablename__ = "generated_documents"

    __table_args__ = (
        CheckConstraint(
            "document_type IN ('resume', 'cover_letter')",
            name="ck_generated_documents_type",
        ),
        CheckConstraint(
            "generation_method IN ('deterministic', 'llm')",
            name="ck_generated_documents_method",
        ),
        CheckConstraint(
            "current_version >= 1",
            name="ck_generated_documents_version_positive",
        ),
    )

    document_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="SET NULL"),
        nullable=True,
    )
    internship_id: Mapped[int | None] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="SET NULL"),
        nullable=True,
    )

    document_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Added in Phase 5 (additive migration).
    content_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    generation_method: Mapped[str | None] = mapped_column(String(20))
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    llm_model: Mapped[str | None] = mapped_column(String(100))
    fact_check: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    ats_report: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    options: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    current_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default=text("1"), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="generated_documents"
    )
    resume: Mapped["Resume | None"] = relationship(
        back_populates="generated_documents"
    )
    internship: Mapped["Internship | None"] = relationship(
        back_populates="generated_documents"
    )
    versions: Mapped[list["GeneratedDocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="GeneratedDocumentVersion.version",
    )


class GeneratedDocumentVersion(Base):
    """Immutable snapshot of a generated document (Phase 5)."""

    __tablename__ = "generated_document_versions"

    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "version",
            name="uq_generated_document_version",
        ),
        CheckConstraint(
            "source IN ('generated', 'edited', 'restored')",
            name="ck_generated_document_versions_source",
        ),
    )

    version_id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("generated_documents.document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    fact_check: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    document: Mapped["GeneratedDocument"] = relationship(
        back_populates="versions"
    )


# ============================================================
# MODULE 7: INTERVIEW PREPARATION
# ============================================================

class InterviewSession(Base):
    """A practice or mock interview (Phase 6). ``score`` is 0-100."""

    __tablename__ = "interview_sessions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('started', 'in_progress', 'completed', 'abandoned')",
            name="ck_interview_sessions_status",
        ),
        CheckConstraint(
            "mode IN ('practice', 'mock')",
            name="ck_interview_sessions_mode",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_interview_sessions_score_range",
        ),
        Index("ix_interview_sessions_user_status", "user_id", "status"),
    )

    session_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    internship_id: Mapped[int | None] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30), default="started", nullable=False
    )
    score: Mapped[float | None] = mapped_column(Float)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )

    # Added in Phase 6 (additive migration).
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str | None] = mapped_column(String(255))
    mode: Mapped[str | None] = mapped_column(String(20))
    question_mix: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    difficulty: Mapped[str | None] = mapped_column(String(20))
    generation_method: Mapped[str | None] = mapped_column(String(20))
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    llm_model: Mapped[str | None] = mapped_column(String(100))
    total_questions: Mapped[int | None] = mapped_column(Integer)
    answered_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="interview_sessions"
    )
    internship: Mapped["Internship | None"] = relationship(
        back_populates="interview_sessions"
    )
    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InterviewQuestion.position",
    )


class InterviewQuestion(Base):
    """One question in a session. ``score`` is the latest attempt (0-100)."""

    __tablename__ = "interview_questions"

    __table_args__ = (
        CheckConstraint(
            "category IN ('technical', 'project', 'behavioral', 'internship')",
            name="ck_interview_questions_category",
        ),
        CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')",
            name="ck_interview_questions_difficulty",
        ),
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_interview_questions_score_range",
        ),
        UniqueConstraint("session_id", "position", name="uq_interview_question_position"),
    )

    question_id: Mapped[int] = mapped_column(primary_key=True)

    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.session_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question_text: Mapped[str] = mapped_column(
        Text, nullable=False
    )
    question_type: Mapped[str | None] = mapped_column(
        String(50)
    )
    user_answer: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)
    score: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Added in Phase 6 (additive migration).
    category: Mapped[str | None] = mapped_column(String(20))
    position: Mapped[int | None] = mapped_column(Integer)
    skill_id: Mapped[int | None] = mapped_column(
        ForeignKey("skills.skill_id", ondelete="SET NULL")
    )
    bank_question_id: Mapped[str | None] = mapped_column(String(60))
    source_fact_ids: Mapped[list[str] | None] = mapped_column(JSON)
    difficulty: Mapped[str | None] = mapped_column(String(20))
    key_points: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    explanation: Mapped[str | None] = mapped_column(Text)
    suggested_answer: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evaluation: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    session: Mapped["InterviewSession"] = relationship(
        back_populates="questions"
    )
    answers: Mapped[list["InterviewAnswer"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="InterviewAnswer.attempt",
    )


class InterviewAnswer(Base):
    """One answer attempt to an interview question (Phase 6)."""

    __tablename__ = "interview_answers"

    __table_args__ = (
        UniqueConstraint("question_id", "attempt", name="uq_interview_answer_attempt"),
        CheckConstraint("score >= 0 AND score <= 100", name="ck_interview_answers_score_range"),
        CheckConstraint("feedback_source IN ('rubric', 'llm')", name="ck_interview_answers_feedback_source"),
    )

    answer_id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("interview_questions.question_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    time_taken_seconds: Mapped[int | None] = mapped_column(Integer)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    feedback_source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    question: Mapped["InterviewQuestion"] = relationship(back_populates="answers")


# ============================================================
# MODULE 8: APPLICATION TRACKING
# ============================================================

APPLICATION_STATUSES = ("SAVED", "APPLIED", "SHORTLISTED", "INTERVIEW_SCHEDULED", "SELECTED", "REJECTED",
                        "WITHDRAWN")
_STATUS_SQL = ", ".join(f"'{s}'" for s in APPLICATION_STATUSES)


class Application(Base):
    """A student's application (Phase 7 extends the original table).

    Internal applications reference an internship from the knowledge base;
    external ones (found elsewhere) store company, title and an optional URL
    or reference. Company, title and listing details are copied from the
    internship at creation, so the record survives if the internship row is
    ever removed (internship_id is then set to NULL). ``deleted_at`` marks an
    application moved to the trash (soft delete).
    """

    __tablename__ = "applications"

    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_SQL})", name="ck_applications_status"),
        CheckConstraint("source IN ('internal', 'external')", name="ck_applications_source"),
        CheckConstraint("source = 'internal' OR internship_id IS NULL",
                        name="ck_applications_external_no_internship"),
        CheckConstraint("work_mode IN ('Onsite', 'Hybrid', 'Remote')", name="ck_applications_work_mode"),
        Index("ix_applications_user_status", "user_id", "status"),
        Index("ix_applications_user_updated", "user_id", "updated_at"),
        Index("ix_applications_user_applied", "user_id", "applied_at"),
        Index("uq_applications_user_internship_active", "user_id", "internship_id", unique=True,
              postgresql_where=text("deleted_at IS NULL AND internship_id IS NOT NULL")),
        Index("uq_applications_user_url_active", "user_id", "application_url_normalized", unique=True,
              postgresql_where=text("deleted_at IS NULL AND source = 'external' "
                                    "AND application_url_normalized IS NOT NULL")),
        Index("uq_applications_user_reference_active", "user_id", "company_key", "external_reference",
              unique=True, postgresql_where=text("deleted_at IS NULL AND external_reference IS NOT NULL")),
    )

    application_id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    internship_id: Mapped[int | None] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Phase 7 fields.
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'internal'"))
    company_name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_key: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    application_url: Mapped[str | None] = mapped_column(String(1000))          # same size as internships
    application_url_normalized: Mapped[str | None] = mapped_column(String(1000))
    external_reference: Mapped[str | None] = mapped_column(String(100))
    domain: Mapped[str | None] = mapped_column(String(80))
    location: Mapped[str | None] = mapped_column(String(150))
    work_mode: Mapped[str | None] = mapped_column(String(20))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str | None] = mapped_column(String(255))
    resume_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_documents.document_id", ondelete="SET NULL"))
    cover_letter_document_id: Mapped[int | None] = mapped_column(
        ForeignKey("generated_documents.document_id", ondelete="SET NULL"))
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String(30), default="SAVED", server_default=text("'SAVED'"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)

    applied_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="applications"
    )
    internship: Mapped["Internship | None"] = relationship(
        back_populates="applications"
    )
    status_history: Mapped[list["ApplicationStatusHistory"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ApplicationStatusHistory.history_id",
    )
    interviews: Mapped[list["ApplicationInterview"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ApplicationInterview.round_number",
    )
    reminders: Mapped[list["ApplicationReminder"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ApplicationReminder.remind_at",
    )
    activity: Mapped[list["ApplicationActivity"]] = relationship(
        back_populates="application", cascade="all, delete-orphan", passive_deletes=True,
        order_by="ApplicationActivity.activity_id",
    )


class SavedInternship(Base):
    """A student's bookmark of a knowledge-base internship (Phase 7)."""

    __tablename__ = "saved_internships"
    __table_args__ = (
        UniqueConstraint("user_id", "internship_id", name="uq_saved_internships_user_internship"),
    )

    bookmark_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    internship_id: Mapped[int] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    internship: Mapped["Internship"] = relationship()


STATUS_CHANGE_TYPES = ("created", "manual", "correction", "interview_added", "interview_cancelled", "migrated")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class ApplicationStatusHistory(Base):
    """Every actual status change of an application (Phase 7)."""

    __tablename__ = "application_status_history"
    __table_args__ = (
        CheckConstraint(f"to_status IN ({_STATUS_SQL})", name="ck_application_status_history_to"),
        CheckConstraint(f"from_status IS NULL OR from_status IN ({_STATUS_SQL})",
                        name="ck_application_status_history_from"),
        CheckConstraint(_in_list("change_type", STATUS_CHANGE_TYPES),
                        name="ck_application_status_history_change_type"),
        Index("ix_application_status_history_app_time", "application_id", "changed_at"),
    )

    history_id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    change_type: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    application: Mapped["Application"] = relationship(back_populates="status_history")


INTERVIEW_TYPES = ("technical", "hr", "behavioral", "managerial", "case_study", "assignment", "group", "other")
INTERVIEW_MODES = ("online", "offline", "phone")
INTERVIEW_OUTCOMES = ("pending", "passed", "failed", "cancelled", "no_show")


class ApplicationInterview(Base):
    """One interview round of an application (Phase 7)."""

    __tablename__ = "application_interviews"
    __table_args__ = (
        UniqueConstraint("application_id", "round_number", name="uq_application_interviews_round"),
        CheckConstraint("round_number >= 1", name="ck_application_interviews_round_positive"),
        CheckConstraint(_in_list("interview_type", INTERVIEW_TYPES), name="ck_application_interviews_type"),
        CheckConstraint(_in_list("mode", INTERVIEW_MODES), name="ck_application_interviews_mode"),
        CheckConstraint(_in_list("outcome", INTERVIEW_OUTCOMES), name="ck_application_interviews_outcome"),
        CheckConstraint("duration_minutes IS NULL OR (duration_minutes BETWEEN 5 AND 600)",
                        name="ck_application_interviews_duration"),
        Index("ix_application_interviews_app_time", "application_id", "scheduled_at"),
    )

    interview_id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    interview_type: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    meeting_url: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(200))
    preparation_notes: Mapped[str | None] = mapped_column(Text)
    feedback: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'pending'"),
                                         default="pending")
    interview_session_id: Mapped[int | None] = mapped_column(
        ForeignKey("interview_sessions.session_id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    application: Mapped["Application"] = relationship(back_populates="interviews")


class ApplicationReminder(Base):
    """A follow-up reminder for an application (Phase 7). Stored only; never delivered."""

    __tablename__ = "application_reminders"
    __table_args__ = (
        Index("ix_application_reminders_app_time", "application_id", "remind_at"),
        Index("ix_application_reminders_completed_time", "is_completed", "remind_at"),
    )

    reminder_id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    remind_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false", default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    application: Mapped["Application"] = relationship(back_populates="reminders")


ACTIVITY_EVENTS = (
    "application_created", "details_updated", "status_changed", "interview_scheduled", "interview_updated",
    "interview_deleted", "reminder_created", "reminder_updated", "reminder_completed", "reminder_reopened",
    "reminder_deleted", "application_deleted", "application_restored",
)


class ApplicationActivity(Base):
    """Non-sensitive activity feed for an application (Phase 7).

    ``details`` holds statuses, changed field NAMES, round numbers and ids
    only - never notes, contact details, URLs or reminder text.
    """

    __tablename__ = "application_activity"
    __table_args__ = (
        CheckConstraint(_in_list("event_type", ACTIVITY_EVENTS), name="ck_application_activity_event_type"),
        Index("ix_application_activity_app_time", "application_id", "created_at"),
    )

    activity_id: Mapped[int] = mapped_column(primary_key=True)
    application_id: Mapped[int] = mapped_column(
        ForeignKey("applications.application_id", ondelete="CASCADE"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)

    application: Mapped["Application"] = relationship(back_populates="activity")


# ============================================================
# MODULE 9: CONVERSATIONAL CAREER ASSISTANT
# ============================================================

class Conversation(Base):
    """A chat with the career assistant (Phase 8 extends the original table).

    ``context`` holds only POINTERS (message ids) to earlier result sets and
    the current focus - never resume facts or personal data. The result sets
    themselves live on the assistant messages, so deleting a message (for
    example when the resume it used is deleted) also removes what a
    follow-up could resolve against.
    """

    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
    )

    conversation_id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(String(255))

    # Phase 8 fields.
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="SET NULL"), index=True)
    context: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0", default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(
        back_populates="conversations"
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Message.message_id",
    )


class Message(Base):
    """One chat message (Phase 8 extends the original table).

    ``resume_id`` is set on BOTH messages of a turn whose answer used resume
    data; ON DELETE CASCADE removes that turn when the resume is deleted, so
    no deleted resume facts survive in the chat history.
    """

    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "sender IN ('user', 'assistant', 'system')",
            name="ck_message_sender",
        ),
        CheckConstraint("generation_method IN ('deterministic', 'llm')",
                        name="ck_messages_generation_method"),
        Index("ix_messages_conversation_message", "conversation_id", "message_id"),
    )

    message_id: Mapped[int] = mapped_column(primary_key=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.conversation_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    sender: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    content: Mapped[str] = mapped_column(
        Text, nullable=False
    )

    # Structured, traceable sources: [{"type", "id", "label"}, ...]
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON
    )

    # Phase 8 fields.
    resume_id: Mapped[int | None] = mapped_column(
        ForeignKey("resumes.resume_id", ondelete="CASCADE"), index=True)
    intent: Mapped[str | None] = mapped_column(String(40))
    entities: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    result_set: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    suggested_actions: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    generation_method: Mapped[str | None] = mapped_column(String(20))
    llm_provider: Mapped[str | None] = mapped_column(String(50))
    llm_model: Mapped[str | None] = mapped_column(String(100))
    fact_check: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    warnings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )


ASSISTANT_RATE_BUCKETS = ("minute", "day", "llm_hour")


class AssistantRateLimit(Base):
    """Per-user request counters for the assistant (Phase 8).

    One row per (user, bucket, window). Incremented with a single atomic
    INSERT ... ON CONFLICT DO UPDATE ... RETURNING, so concurrent requests can
    never both slip under the limit.
    """

    __tablename__ = "assistant_rate_limits"
    __table_args__ = (
        CheckConstraint("bucket IN ('minute', 'day', 'llm_hour')", name="ck_assistant_rate_limits_bucket"),
        CheckConstraint("count >= 0", name="ck_assistant_rate_limits_count"),
        Index("ix_assistant_rate_limits_window", "window_start"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True)
    bucket: Mapped[str] = mapped_column(String(20), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


# ============================================================
# AUTHENTICATION MODULE
# ============================================================

class AuthSession(Base):
    __tablename__ = "auth_sessions"

    session_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    refresh_token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )


# ============================================================
# EMAIL VERIFICATION TOKEN
# ============================================================

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    token_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )


# ============================================================
# PASSWORD RESET TOKEN
# ============================================================

class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_id: Mapped[int] = mapped_column(primary_key=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    token_hash: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False
    )

    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )


# ============================================================
# ACCOUNT SECURITY (Phase 1 of the admin upgrade)
# ============================================================

class AdminAuditEvent(Base):
    """Append-only record of administrative and security actions.

    ``details`` holds only identifiers, roles and changed field names/values;
    never passwords, password hashes, tokens or credentials
    (backend/services/audit.py enforces this).
    """

    __tablename__ = "admin_audit_events"
    __table_args__ = (
        Index("ix_admin_audit_events_created_at", "created_at"),
        Index("ix_admin_audit_events_actor", "actor_user_id"),
        Index("ix_admin_audit_events_target", "target_user_id"),
        Index("ix_admin_audit_events_action", "action"),
    )

    event_id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(30), nullable=True)   # None = command line / system
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    target_label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuthRateLimit(Base):
    """Failed sign-in counters per (bucket, hashed key, window).

    Incremented with one atomic INSERT ... ON CONFLICT DO UPDATE ... RETURNING,
    so concurrent attempts can never both slip under the limit. Email keys are
    stored only as SHA-256 hashes.
    """

    __tablename__ = "auth_rate_limits"
    __table_args__ = (
        CheckConstraint("bucket IN ('login_email', 'login_ip')", name="ck_auth_rate_limits_bucket"),
        CheckConstraint("count >= 0", name="ck_auth_rate_limits_count"),
        Index("ix_auth_rate_limits_window", "window_start"),
    )

    bucket: Mapped[str] = mapped_column(String(20), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


# ============================================================
# INVITATIONS AND EMAIL DELIVERY LOG (Phase 2 of the admin upgrade)
# ============================================================

class UserInvitation(Base):
    """A single-use, expiring link that lets a pending account set its own password.

    Only the SHA-256 hash of the token is stored. Sending a new invitation revokes the previous one.
    """

    __tablename__ = "user_invitations"
    __table_args__ = (
        Index("ix_user_invitations_user", "user_id"),
        Index("ix_user_invitations_created_at", "created_at"),
    )

    invitation_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    invited_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivery_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")
    delivery_error: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)


class EmailDelivery(Base):
    """Outcome of every email attempt (no message body, links or tokens are stored)."""

    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint("status IN ('sent', 'outboxed', 'skipped', 'failed')", name="ck_email_deliveries_status"),
        Index("ix_email_deliveries_created_at", "created_at"),
        Index("ix_email_deliveries_user", "user_id"),
    )

    delivery_id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True)
    invitation_id: Mapped[int | None] = mapped_column(
        ForeignKey("user_invitations.invitation_id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ============================================================
# SKILL PROGRESS (P3)
# ============================================================

class SkillProgress(Base):
    """A student's learning progress for one skill (applies to every job that needs it)."""

    __tablename__ = "skill_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "skill_id", name="uq_skill_progress_user_skill"),
        CheckConstraint("status IN ('not_started', 'learning', 'practiced', 'completed')",
                        name="ck_skill_progress_status"),
    )

    progress_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skills.skill_id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="not_started")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class StudyDocument(Base):
    """A PDF/DOCX a student uploaded to ask questions about (HR assignment: document Q&A).

    Only the extracted text is kept (in ``study_document_chunks``); the original file is not stored.
    Owned by one user; deleting the user deletes their documents.
    """

    __tablename__ = "study_documents"
    __table_args__ = (
        UniqueConstraint("user_id", "sha256", name="uq_study_documents_user_sha256"),
        CheckConstraint("file_type IN ('pdf', 'docx')", name="ck_study_documents_file_type"),
    )

    document_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str] = mapped_column(String(10), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer)          # PDF pages; None for DOCX
    section_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    warnings: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chunks: Mapped[list["StudyDocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", passive_deletes=True,
        order_by="StudyDocumentChunk.position")


class StudyDocumentChunk(Base):
    """One passage of a study document with its page (PDF) or section heading (DOCX)."""

    __tablename__ = "study_document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "position", name="uq_study_document_chunks_position"),)

    chunk_id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("study_documents.document_id", ondelete="CASCADE"),
                                             nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer)
    section: Mapped[str | None] = mapped_column(String(255))
    text: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped[StudyDocument] = relationship(back_populates="chunks")
