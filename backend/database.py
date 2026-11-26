from pathlib import Path
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker


# Project root directory
BASE_DIR = Path(__file__).resolve().parent.parent

# Load database settings from the project's .env file
load_dotenv(BASE_DIR / ".env")

DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "career_companion")


if not DB_PASSWORD:
    raise RuntimeError(
        "DB_PASSWORD is missing. Set it in the project .env file."
    )


# Build the connection URL safely
# Managed PostgreSQL (Neon, Render external URL, ...) needs TLS: set DB_SSLMODE=require there.
# Unset locally, so development and tests connect exactly as before.
DB_SSLMODE = os.getenv("DB_SSLMODE", "").strip()

DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username=DB_USER,
    password=DB_PASSWORD,
    host=DB_HOST,
    port=DB_PORT,
    database=DB_NAME,
    query={"sslmode": DB_SSLMODE} if DB_SSLMODE else {},
)

# Create the SQLAlchemy engine
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Create database sessions when the application needs them
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# Test database connectivity
def test_connection():
    with engine.connect() as connection:
        result = connection.execute(
            text("SELECT current_database(), version()")
        )
        return result.fetchone()


# FastAPI dependency for database sessions
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()