"""Shared structural typing helpers for Azure SDK object shapes.

These protocols describe the small attribute subsets ORB consumes from the
Azure SDK models. Keeping them here centralizes the cast boundary for Azure's
generated model types instead of redefining local one-off protocols in each
handler/service.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol, cast


class AzureStatusWithCodeProtocol(Protocol):
    """Azure status-like object exposing a ``code`` attribute."""

    code: str | None


class AzureVmWithNameProtocol(Protocol):
    """Azure VM-like object exposing a ``name`` attribute."""

    name: str | None


class AzureVmWithIdentityProtocol(Protocol):
    """Azure VM-like object exposing ``name`` and ``vm_id`` attributes."""

    name: Optional[str]
    vm_id: Optional[str]


class AzureInstanceViewWithStatusesProtocol(Protocol):
    """Azure instance-view-like object exposing ``statuses``."""

    statuses: list[Any]


def instance_view_statuses(instance_view: object | None) -> list[Any] | None:
    """Return Azure instance-view statuses when the object shape supports them."""
    if instance_view is None:
        return None
    return cast(AzureInstanceViewWithStatusesProtocol, instance_view).statuses
