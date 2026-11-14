"""Shared pytest fixtures.

Safety rules:
* Tests ALWAYS run against a separate PostgreSQL database
  (TEST_DB_NAME, default ``career_companion_test``). The name must end
  in ``_test``; otherwise the run aborts before touching anything.
* Emails are captured in memory, never sent.
* Uploaded files go to a temporary directory, never ``uploads/``.
"""

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ------------------------------------------------------------------
# Point the application at the test database BEFORE importing it.
# load_dotenv() never overrides variables that are already set.
# ------------------------------------------------------------------
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "career_companion_test")

if not TEST_DB_NAME.endswith("_test"):
    raise RuntimeError(
        "Refusing to run tests: TEST_DB_NAME must end with '_test'."
    )

os.environ["DB_NAME"] = TEST_DB_NAME
os.environ.setdefault(
    "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
)
load_dotenv(PROJECT_ROOT / ".env")


def _ensure_test_database_exists() -> None:
    import psycopg
    from psycopg import sql

    with psycopg.connect(
        dbname="postgres",
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5432")),
        autocommit=True,
    ) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (TEST_DB_NAME,),
        ).fetchone()

        if not exists:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(TEST_DB_NAME)
                )
            )


_ensure_test_database_exists()

# Application imports must come after the environment is prepared.
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from backend import database  # noqa: E402
from backend.main import app  # noqa: E402
from backend.models import Base, User  # noqa: E402

assert database.engine.url.database == TEST_DB_NAME, (
    "Test engine is not connected to the test database"
)


# ------------------------------------------------------------------
# Database lifecycle
# ------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def test_schema():
    """Create a fresh schema once per test run."""
    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)
    yield
    database.engine.dispose()


@pytest.fixture(autouse=True)
def clean_tables():
    """Empty every table before each test."""
    table_names = ", ".join(
        f'"{table.name}"' for table in reversed(Base.metadata.sorted_tables)
    )
    with database.engine.begin() as connection:
        connection.execute(
            text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE")
        )
    yield


@pytest.fixture
def db_session():
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


# ------------------------------------------------------------------
# Email capture and file isolation
# ------------------------------------------------------------------

class Outbox:
    def __init__(self):
        self.messages: list[dict] = []
        self.fail = False

    def _send(self, kind: str):
        def sender(to_email: str, token: str) -> None:
            if self.fail:
                raise RuntimeError("Simulated SMTP failure")
            self.messages.append(
                {"kind": kind, "to": to_email, "token": token}
            )
        return sender

    def last(self, kind: str, to_email: str) -> dict:
        matches = [
            m for m in self.messages
            if m["kind"] == kind and m["to"] == to_email
        ]
        assert matches, f"No {kind} email sent to {to_email}"
        return matches[-1]

    def count(self, kind: str, to_email: str) -> int:
        return sum(
            1 for m in self.messages
            if m["kind"] == kind and m["to"] == to_email
        )


@pytest.fixture(autouse=True)
def outbox(monkeypatch):
    box = Outbox()
    monkeypatch.setattr(
        "backend.routes.auth.send_verification_email",
        box._send("verify"),
    )
    monkeypatch.setattr(
        "backend.routes.auth.send_password_reset_email",
        box._send("reset"),
    )
    return box


@pytest.fixture(autouse=True)
def isolated_uploads(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads" / "resumes"
    monkeypatch.setattr("backend.routes.resumes.UPLOAD_DIR", upload_dir)
    return upload_dir


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

DEFAULT_PASSWORD = "Str0ngPass!word"


@pytest.fixture
def create_user(client, outbox, db_session):
    """Register, verify and log in a user. Returns a dict with tokens."""

    counter = {"n": 0}

    def _create(role: str = "student", email: str | None = None) -> dict:
        counter["n"] += 1
        email = email or f"user{counter['n']}@example.com"

        response = client.post("/auth/register", json={
            "first_name": "Test",
            "last_name": f"User{counter['n']}",
            "phone_number": "+919876543210",
            "email": email,
            "password": DEFAULT_PASSWORD,
        })
        assert response.status_code == 201, response.text

        token = outbox.last("verify", email)["token"]
        verify = client.get("/auth/verify-email", params={"token": token})
        assert verify.status_code == 200, verify.text

        user = db_session.get(User, response.json()["user_id"])
        if role != "student":
            user.role = role
            db_session.commit()

        login = client.post("/auth/login", json={
            "email": email, "password": DEFAULT_PASSWORD,
        })
        assert login.status_code == 200, login.text
        tokens = login.json()

        return {
            "user_id": user.user_id,
            "email": email,
            "password": DEFAULT_PASSWORD,
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "headers": {
                "Authorization": f"Bearer {tokens['access_token']}"
            },
        }

    return _create
