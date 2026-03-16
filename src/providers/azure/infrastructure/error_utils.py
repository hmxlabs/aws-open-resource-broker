"""Helpers for normalizing Azure SDK / ARM error payloads."""

from __future__ import annotations

from typing import Any


def extract_azure_error_details(exc: Exception) -> dict[str, Any]:
    """Extract Azure SDK error details from common exception shapes."""
    error = getattr(exc, "error", None)
    response = getattr(exc, "response", None)

    raw_error_code = (
        getattr(exc, "error_code", None)
        or getattr(error, "code", None)
        or getattr(exc, "code", None)
    )
    status_code = getattr(exc, "status_code", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)

    message = (
        getattr(error, "message", None)
        or getattr(exc, "message", None)
        or str(exc)
    )

    return {
        "raw_error_code": str(raw_error_code) if raw_error_code not in (None, "") else None,
        "status_code": status_code,
        "message": str(message),
    }


def canonical_azure_error_code(exc: Exception) -> str:
    """Return a stable Azure provisioning error code."""
    details = extract_azure_error_details(exc)
    raw_error_code = details["raw_error_code"]
    status_code = details["status_code"]
    message = details["message"].lower()

    if raw_error_code:
        return raw_error_code
    if status_code == 429:
        return "TooManyRequests"
    if status_code == 404:
        return "ResourceNotFound"
    if status_code == 403:
        return "AuthorizationFailed"
    if "quota" in message or "exceed" in message:
        return "QuotaExceeded"
    if "allocationfailed" in message or "insufficient" in message:
        return "AllocationFailed"
    if "validation" in message or "invalid" in message:
        return "InvalidRequest"
    return type(exc).__name__

