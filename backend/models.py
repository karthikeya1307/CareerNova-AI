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

    user: Mapped["User"] = relationship(
        back_populates="profile"
    )


class Resume(Base):
    __tablename__ = "resumes"

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
    __tablename__ = "match_results"

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
    __tablename__ = "skill_gap_recommendations"

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
    __tablename__ = "generated_documents"

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

    user: Mapped["User"] = relationship(
        back_populates="generated_documents"
    )
    resume: Mapped["Resume | None"] = relationship(
        back_populates="generated_documents"
    )
    internship: Mapped["Internship | None"] = relationship(
        back_populates="generated_documents"
    )


# ============================================================
# MODULE 7: INTERVIEW PREPARATION
# ============================================================

class InterviewSession(Base):
    __tablename__ = "interview_sessions"

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
    )


class InterviewQuestion(Base):
    __tablename__ = "interview_questions"

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

    session: Mapped["InterviewSession"] = relationship(
        back_populates="questions"
    )


# ============================================================
# MODULE 8: APPLICATION TRACKING
# ============================================================

class Application(Base):
    __tablename__ = "applications"

    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "internship_id",
            name="uq_application_user_internship",
        ),
    )

    application_id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    internship_id: Mapped[int] = mapped_column(
        ForeignKey("internships.internship_id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30), default="saved", nullable=False
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
    internship: Mapped["Internship"] = relationship(
        back_populates="applications"
    )


# ============================================================
# MODULE 9: CONVERSATIONAL CAREER ASSISTANT
# ============================================================

class Conversation(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[int] = mapped_column(
        primary_key=True
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(String(255))

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
        order_by="Message.created_at",
    )


class Message(Base):
    __tablename__ = "messages"

    __table_args__ = (
        CheckConstraint(
            "sender IN ('user', 'assistant', 'system')",
            name="ck_message_sender",
        ),
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

    # Optional citations or source metadata returned by the AI
    sources: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(
        back_populates="messages"
    )

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
