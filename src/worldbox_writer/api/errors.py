"""Framework-independent API errors raised by application services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiError(Exception):
    """Error with HTTP-compatible semantics, without importing FastAPI in services."""

    status_code: int
    detail: str

    def __str__(self) -> str:
        return self.detail
