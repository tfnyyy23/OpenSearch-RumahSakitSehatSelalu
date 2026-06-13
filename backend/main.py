"""
main.py
-------
FastAPI entry point for Hospital QA System.
Run locally:
    uvicorn backend.main:app --reload --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import qa

app = FastAPI(
    title="Hospital QA System -- Analisis Biaya Operasional",
    description="QA system berbasis OpenSearch + Gemini untuk analisis biaya operasional Rumah Sakit Sehat Selalu.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # ganti dengan domain spesifik di production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(qa.router, prefix="/api", tags=["QA"])


@app.get("/")
async def root():
    return {
        "service": "Hospital QA System",
        "status":  "running",
        "docs":    "/docs",
    }