"""API routes for Tonic Ear."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.schemas import SessionCreateRequest
from app.domain.generator import generate_session, get_meta, validate_temperament

router = APIRouter(prefix="/api/v1", tags=["TonicEar"])


@router.get("/meta")
def get_metadata() -> dict:
    return get_meta()


@router.post("/session")
def create_session(payload: SessionCreateRequest) -> dict:
    try:
        validate_temperament(payload.temperament)
        return generate_session(
            module_id=payload.moduleId,
            gender=payload.gender,
            key=payload.key,
            temperament=payload.temperament,
            instrument=payload.instrument,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
