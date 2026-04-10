"""Typed internal data structures for the GCP provider."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict


@dataclass(frozen=True)
class GCPInstanceRecord:
    """Normalized instance data returned from the Compute API."""

    name: str
    status: str | None = None
    self_link: str | None = None


@dataclass(frozen=True)
class GCPManagedInstanceRecord:
    """Normalized managed-instance data returned from a MIG."""

    instance_url: str
    instance_status: str | None = None
    current_action: str | None = None


class GCPHandlerContext(TypedDict, total=False):
    """Provider-owned context needed to operate on existing GCP resources."""

    project_id: str
    region: str
    zone: str
    scope: str
    mig_name: str
    instance_template_name: str
    provider_api: str


class GCPInstanceStatus(TypedDict):
    """Normalized status record surfaced by GCP handlers."""

    instance_id: str
    status: str
    provider_data: dict[str, str]


class GCPCreateHandlerResult(TypedDict, total=False):
    """Result returned from a GCP acquire_hosts operation."""

    resource_ids: list[str]
    instances: list[GCPInstanceStatus]
    provider_data: dict[str, str | int | bool]
    failed_operations: list[GCPFailedOperation]


class GCPFailedOperation(TypedDict):
    """Structured failure record for a per-target GCP batch operation."""

    target_id: str
    error_code: str
    error_message: str
    operation: str


class GCPMutationResult(TypedDict, total=False):
    """Result returned from GCP mutation operations."""

    terminated_ids: list[str]
    started_instance_ids: list[str]
    stopped_instance_ids: list[str]
    results: dict[str, bool]
    operations: list[dict[str, str | None]]
    failed_operations: list[GCPFailedOperation]
    warning: str
