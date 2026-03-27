"""Helpers for durable provider follow-up context stored on requests."""

from __future__ import annotations

from typing import Any

FOLLOW_UP_CONTEXT_KEY = "follow_up_context"


def get_request_follow_up_context(request: Any) -> dict[str, Any]:
    """Return durable provider follow-up context for a request."""
    request_provider_data = getattr(request, "provider_data", {}) or {}
    if not isinstance(request_provider_data, dict):
        return {}

    follow_up_context = request_provider_data.get(FOLLOW_UP_CONTEXT_KEY)
    if not isinstance(follow_up_context, dict):
        return {}

    return dict(follow_up_context)


def merge_request_metadata_with_follow_up_context(request: Any) -> dict[str, Any]:
    """Merge request metadata with durable provider follow-up context."""
    request_metadata = dict(getattr(request, "metadata", {}) or {})
    request_metadata = {**get_request_follow_up_context(request), **request_metadata}
    return request_metadata


def with_request_follow_up_context(request: Any, updates: dict[str, Any]) -> Any:
    """Return a request with merged durable provider follow-up context."""
    if not updates:
        return request

    request_provider_data = dict(getattr(request, "provider_data", {}) or {})
    follow_up_context = get_request_follow_up_context(request)
    for key, value in updates.items():
        if value not in (None, ""):
            follow_up_context[key] = value

    request_provider_data[FOLLOW_UP_CONTEXT_KEY] = follow_up_context
    return request.set_provider_data(request_provider_data)
