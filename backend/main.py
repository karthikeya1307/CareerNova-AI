
from fastapi import FastAPI, HTTPException

from backend.database import test_connection
from backend.routes.auth import router as auth_router
from backend.routes.profiles import router as profiles_router
from backend.routes.resumes import router as resumes_router


# Create FastAPI application
app = FastAPI(
    title="AI Career Companion API",
    description="User Management and Resume Parsing APIs",
    version="1.0.0"
)

# Register authentication routes
app.include_router(auth_router)
app.include_router(profiles_router)
app.include_router(resumes_router)

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
