"""Geev API errors.

All errors raised by this library derive from :class:`GeevError`, so callers
can catch a single base type and still inspect the details.
"""

from __future__ import annotations

from typing import Any


class GeevError(Exception):
    """Base class for every error raised by the library."""


class BadRequest(GeevError):
    """The server rejected the request (HTTP 4xx, or non-JSON/unexpected body)."""

    def __init__(self, message: str, *, status_code: int | None = None,
                 payload: Any = None, method: str | None = None,
                 url: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload
        self.method = method
        self.url = url

    def __str__(self) -> str:  # pragma: no cover - trivial formatting
        base = super().__str__()
        if self.status_code is not None:
            base += f"  [{self.status_code} {self.method or ''} {self.url or ''}]"
        if self.payload is not None:
            base += f": {self.payload!r}"
        return base


class ServerError(BadRequest):
    """The server failed (HTTP 5xx)."""


class AuthenticationError(BadRequest):
    """Login / token related failure (401, 403, wrong code, invalid token)."""


class ValidationError(BadRequest):
    """The user-supplied parameters are invalid (client-side)."""