"""FastAPI application entrypoint for Tonic Ear."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router as api_router

BASE_DIR = Path(__file__).resolve().parents[1]
WEB_DIR = BASE_DIR / "web"
ASSETS_DIR = WEB_DIR / "assets"

app = FastAPI(title="Tonic Ear", version="1.0.0")
app.include_router(api_router)

app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
