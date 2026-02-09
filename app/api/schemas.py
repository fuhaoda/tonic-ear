"""Request/response schemas for API routes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator

from app.domain.music import KEY_OFFSETS


class SessionCreateRequest(BaseModel):
    moduleId: str
    gender: Literal["male", "female"]
    key: str
    temperament: Literal["equal_temperament"]

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if value not in KEY_OFFSETS:
            raise ValueError(f"Unknown key '{value}'")
        return value
