import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.app.config import settings, competition_config
from backend.app.db.init_db import init_database
from backend.app.services.dataset_manager import dataset_manager
from backend.app.api.auth import router as auth_router
from backend.app.api.teams import router as teams_router
from backend.app.api.submissions import router as submissions_router
from backend.app.api.leaderboard import router as leaderboard_router
from backend.app.api.admin import router as admin_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hackeval")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing HackEval platform database...")
    init_database()
    logger.info("Verifying ground truth datasets...")
    dataset_manager._ensure_synthetic_datasets()
    logger.info("HackEval backend started successfully.")
    yield
    logger.info("HackEval backend shutdown.")


app = FastAPI(
    title="HackEval API",
    description="Secure & Auditable Classification Hackathon Evaluation Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware for Next.js / React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(auth_router)
app.include_router(teams_router)
app.include_router(submissions_router)
app.include_router(leaderboard_router)
app.include_router(admin_router)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "competition": competition_config.name,
        "is_production_ready": competition_config.is_production_ready,
    }


@app.get("/api/status")
def status_info():
    return {
        "competition_name": competition_config.name,
        "timezone": competition_config.timezone,
        "problem_type": competition_config.problem_type,
        "scoring_weights": {
            "verified_performance_weight": competition_config.verified_performance_weight,
            "reliability_weight": competition_config.reliability_weight,
        },
        "max_attempts": competition_config.max_attempts_per_team,
        "accepted_extensions": competition_config.accepted_extensions,
        "is_production_ready": competition_config.is_production_ready,
        "unresolved_todos": competition_config.unresolved_todos,
    }


# Mock participant endpoint helper for local testing and demonstration
@app.post("/mock-finalist-endpoint")
@app.post("/mock-finalist-endpoint/health")
async def mock_participant_endpoint(request: Request):
    """
    Mock participant-hosted endpoint for testing and local evaluation demonstration.
    Returns valid predictions and echoes deployment version.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    req_action = body.get("action")
    if req_action == "health_check":
        return {
            "status": "ok",
            "version": "v1.0.0",
            "model": "ClassificationEnsemble-XGBoost",
        }

    cases = body.get("cases", [])
    predictions = []
    labels = competition_config.label_set or ["category_a", "category_b", "category_c"]

    for idx, c in enumerate(cases):
        cid = c.get("case_id", f"MOCK_{idx}")
        # Predict deterministically
        pred_label = labels[idx % len(labels)]
        predictions.append({"case_id": cid, "prediction": pred_label})

    return {
        "request_id": body.get("request_id"),
        "version": "v1.0.0",
        "predictions": predictions,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=settings.APP_HOST, port=settings.APP_PORT, reload=True)
