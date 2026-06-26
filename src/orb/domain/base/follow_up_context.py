"""Typed follow-up context for provider operations that require background tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class TerminationFollowUpContext:
    """Context for a return-machines follow-up."""

    follow_up_kind: Literal["termination"] = field(default="termination", init=False)
    pending_instance_ids: list[str] = field(default_factory=list)
    expected_terminal_state: str = "terminated"
    poll_after: datetime | None = None
    provider_handle: str | None = None


@dataclass(frozen=True)
class DeploymentPollingFollowUpContext:
    """Context for an acquire follow-up where the fleet is still initialising."""

    follow_up_kind: Literal["deployment_polling"] = field(default="deployment_polling", init=False)
    pending_resource_ids: list[str] = field(default_factory=list)
    expected_terminal_state: str = "running"
    poll_after: datetime | None = None
    provider_handle: str | None = None


FollowUpContext = TerminationFollowUpContext | DeploymentPollingFollowUpContext
