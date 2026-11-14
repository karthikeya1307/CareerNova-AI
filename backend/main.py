
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from backend.database import test_connection
from backend.routes.admin import router as admin_router
from backend.routes.auth import router as auth_router
from backend.routes.internships import router as internships_router
from backend.routes.profiles import router as profiles_router
from backend.routes.resumes import router as resumes_router


# Create FastAPI application
app = FastAPI(
    title="AI Career Companion API",
    description="User Management and Resume Parsing APIs",
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
app.include_router(admin_router)

# Root API
@app.get("/")
def home():
    return {
        "message": "Welcome to AI Career Companion API",
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
