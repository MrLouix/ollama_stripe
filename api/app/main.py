"""FastAPI application entry point"""

from fastapi import FastAPI
from app.config import settings
from app.api.v1 import chat

app = FastAPI(
    title="Ollama SaaS Gateway",
    description="API Gateway for monetizing local Ollama LLM instances",
    version="0.1.0",
)

# Include API v1 routers
app.include_router(chat.router, prefix="/v1", tags=["chat"])


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "Ollama SaaS Gateway",
        "version": "0.1.0",
        "status": "ok"
    }


@app.get("/healthz")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}


@app.get("/readyz")
async def readiness_check():
    """Readiness check endpoint - will verify DB, Redis, and Ollama when implemented"""
    # TODO: Add actual checks for DB, Redis, and Ollama
    return {"status": "ready"}
