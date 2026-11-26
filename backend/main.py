
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.database import test_connection
from backend.routes.admin import router as admin_router
from backend.routes.auth import router as auth_router
from backend.routes.documents import router as documents_router
from backend.routes.internships import router as internships_router
from backend.routes.interviews import router as interviews_router
from backend.routes.applications import router as applications_router
from backend.routes.assistant import router as assistant_router
from backend.routes.matches import router as matches_router
from backend.routes.skill_gaps import router as skill_gaps_router
from backend.routes.profiles import router as profiles_router
from backend.routes.resumes import router as resumes_router
from backend.routes.career_tracks import router as career_tracks_router
from backend.routes.prep import router as prep_router
from backend.routes.study_documents import router as study_documents_router


# Create FastAPI application
app = FastAPI(
    title="CareerNova AI API",
    description="CareerNova AI — Your Skills. Your Potential. Your Career. Accounts, resumes, matching, skill gaps, documents, interviews, applications and the career assistant.",
    version="1.0.0"
)


# ============================================================
# CORS
# Allowed browser origins come from CORS_ORIGINS (comma-separated).
# Defaults cover the Vite dev server.
# ============================================================

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

cors_origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

if "*" in cors_origins:
    raise RuntimeError(
        "CORS_ORIGINS must list explicit origins; '*' is not allowed."
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Register routers
app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(resumes_router)
app.include_router(internships_router)
app.include_router(matches_router)
app.include_router(skill_gaps_router)
app.include_router(documents_router)
app.include_router(interviews_router)
app.include_router(applications_router)
app.include_router(assistant_router)
app.include_router(admin_router)
app.include_router(career_tracks_router)
app.include_router(prep_router)
app.include_router(study_documents_router)

# Root API
@app.get("/")
def home():
    return {
        "message": "Welcome to CareerNova AI API",
        "status": "Running"
    }


# Database health check
@app.get("/health")
def health_check():
    try:
        database_name, _ = test_connection()

        return {
            "status": "Healthy",
            "database": database_name,
            "message": "Database connection successful"
        }

    except Exception:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed"
        )
