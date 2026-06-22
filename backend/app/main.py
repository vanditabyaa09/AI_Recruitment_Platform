import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.gemini import gemini
from app.routers import router

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("recruitiq")

settings = get_settings()

app = FastAPI(
    title="RecruitIQ AI",
    description="AI-Augmented Recruitment Platform — screen CVs, rank semantically, explain why.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_origin_regex=settings.cors_origin_regex or None,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
async def startup():
    mode = f"Gemini ({settings.gemini_model})" if gemini.available else "OFFLINE heuristic mode"
    logger.info("RecruitIQ AI started — AI backend: %s", mode)


@app.get("/health")
async def health():
    return {"status": "healthy", "ai": gemini.available, "model": settings.gemini_model}


@app.get("/")
async def root():
    return {
        "name": "RecruitIQ AI",
        "tagline": "Screen 1,000 CVs. Surface the 10 who matter. Explain why.",
        "docs": "/docs",
        "health": "/health",
        "ai_enabled": gemini.available,
    }
