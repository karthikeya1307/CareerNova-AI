"""extend interview tables and add interview_answers

Revision ID: f3c9e1a5b7d2
Revises: e7b2d4f6a8c1
Create Date: 2026-11-15

Additive only: new nullable or defaulted columns, named constraints and
indexes on interview_sessions / interview_questions, plus a new
interview_answers table. The status check accepts the original default
value ('started').
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3c9e1a5b7d2"
down_revision: Union[str, Sequence[str], None] = "e7b2d4f6a8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SESSION_COLUMNS = [
    ("title", sa.String(length=255)),
    ("mode", sa.String(length=20)),
    ("question_mix", sa.JSON()),
    ("difficulty", sa.String(length=20)),
    ("generation_method", sa.String(length=20)),
    ("llm_provider", sa.String(length=50)),
    ("llm_model", sa.String(length=100)),
    ("total_questions", sa.Integer()),
    ("summary", sa.JSON()),
]

QUESTION_COLUMNS = [
    ("category", sa.String(length=20)),
    ("position", sa.Integer()),
    ("bank_question_id", sa.String(length=60)),
    ("source_fact_ids", sa.JSON()),
    ("difficulty", sa.String(length=20)),
    ("key_points", sa.JSON()),
    ("explanation", sa.Text()),
    ("suggested_answer", sa.JSON()),
    ("context", sa.JSON()),
    ("time_limit_seconds", sa.Integer()),
    ("revealed_at", sa.DateTime(timezone=True)),
    ("answered_at", sa.DateTime(timezone=True)),
    ("evaluation", sa.JSON()),
]


def upgrade() -> None:
    # ---------------- interview_sessions ----------------
    op.add_column("interview_sessions", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.create_foreign_key("interview_sessions_resume_id_fkey", "interview_sessions", "resumes",
                          ["resume_id"], ["resume_id"], ondelete="SET NULL")
    op.create_index(op.f("ix_interview_sessions_resume_id"), "interview_sessions", ["resume_id"])
    for name, column_type in SESSION_COLUMNS:
        op.add_column("interview_sessions", sa.Column(name, column_type, nullable=True))
    op.add_column("interview_sessions", sa.Column(
        "answered_count", sa.Integer(), server_default=sa.text("0"), nullable=False))
    op.add_column("interview_sessions", sa.Column(
        "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False))
    op.create_check_constraint("ck_interview_sessions_status", "interview_sessions",
                               "status IN ('started', 'in_progress', 'completed', 'abandoned')")
    op.create_check_constraint("ck_interview_sessions_mode", "interview_sessions",
                               "mode IN ('practice', 'mock')")
    op.create_check_constraint("ck_interview_sessions_score_range", "interview_sessions",
                               "score >= 0 AND score <= 100")
    op.create_index("ix_interview_sessions_user_status", "interview_sessions", ["user_id", "status"])

    # ---------------- interview_questions ----------------
    for name, column_type in QUESTION_COLUMNS:
        op.add_column("interview_questions", sa.Column(name, column_type, nullable=True))
    op.add_column("interview_questions", sa.Column("skill_id", sa.Integer(), nullable=True))
    op.create_foreign_key("interview_questions_skill_id_fkey", "interview_questions", "skills",
                          ["skill_id"], ["skill_id"], ondelete="SET NULL")
    op.create_check_constraint("ck_interview_questions_category", "interview_questions",
                               "category IN ('technical', 'project', 'behavioral', 'internship')")
    op.create_check_constraint("ck_interview_questions_difficulty", "interview_questions",
                               "difficulty IN ('easy', 'medium', 'hard')")
    op.create_check_constraint("ck_interview_questions_score_range", "interview_questions",
                               "score >= 0 AND score <= 100")
    op.create_unique_constraint("uq_interview_question_position", "interview_questions",
                                ["session_id", "position"])

    # ---------------- interview_answers ----------------
    op.create_table(
        "interview_answers",
        sa.Column("answer_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("time_taken_seconds", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("evaluation", sa.JSON(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("feedback_source", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("feedback_source IN ('rubric', 'llm')", name="ck_interview_answers_feedback_source"),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_interview_answers_score_range"),
        sa.ForeignKeyConstraint(["question_id"], ["interview_questions.question_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("answer_id"),
        sa.UniqueConstraint("question_id", "attempt", name="uq_interview_answer_attempt"),
    )
    op.create_index(op.f("ix_interview_answers_question_id"), "interview_answers", ["question_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_interview_answers_question_id"), table_name="interview_answers")
    op.drop_table("interview_answers")

    op.drop_constraint("uq_interview_question_position", "interview_questions", type_="unique")
    for name in ("ck_interview_questions_score_range", "ck_interview_questions_difficulty",
                 "ck_interview_questions_category"):
        op.drop_constraint(name, "interview_questions", type_="check")
    op.drop_constraint("interview_questions_skill_id_fkey", "interview_questions", type_="foreignkey")
    op.drop_column("interview_questions", "skill_id")
    for name, _ in reversed(QUESTION_COLUMNS):
        op.drop_column("interview_questions", name)

    op.drop_index("ix_interview_sessions_user_status", table_name="interview_sessions")
    for name in ("ck_interview_sessions_score_range", "ck_interview_sessions_mode",
                 "ck_interview_sessions_status"):
        op.drop_constraint(name, "interview_sessions", type_="check")
    op.drop_column("interview_sessions", "updated_at")
    op.drop_column("interview_sessions", "answered_count")
    for name, _ in reversed(SESSION_COLUMNS):
        op.drop_column("interview_sessions", name)
    op.drop_index(op.f("ix_interview_sessions_resume_id"), table_name="interview_sessions")
    op.drop_constraint("interview_sessions_resume_id_fkey", "interview_sessions", type_="foreignkey")
    op.drop_column("interview_sessions", "resume_id")
