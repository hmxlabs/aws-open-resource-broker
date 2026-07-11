"""Tests for DeploymentStatusResolver.compute_fulfilment failure detection.

Focus: a crash-looping Deployment whose controller keeps respawning pods
leaves the instance list as a mix of failed + pending.  The resolver must
report ``failed`` rather than masking it as perpetual ``in_progress``.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from orb.providers.k8s.infrastructure.handlers.deployment_status import (
    DeploymentStatusResolver,
)


def _resolver() -> DeploymentStatusResolver:
    return DeploymentStatusResolver(MagicMock())


def _inst(status: str) -> dict:
    return {"status": status}


def test_mixed_failed_and_pending_with_no_ready_is_failed() -> None:
    """failed + pending, nothing ready → failed (was perpetual in_progress)."""
    resolver = _resolver()
    instances = [_inst("failed"), _inst("failed"), _inst("pending")]
    result = resolver.compute_fulfilment(instances, requested_count=3)
    assert result.state == "failed"
    assert result.failed_count == 2
    assert result.pending_count == 1


def test_all_pending_no_failures_still_in_progress() -> None:
    """No failures yet — genuine scale-up stays in_progress."""
    resolver = _resolver()
    instances = [_inst("pending"), _inst("pending")]
    result = resolver.compute_fulfilment(instances, requested_count=2)
    assert result.state == "in_progress"


def test_some_ready_with_failure_is_not_failed() -> None:
    """At least one replica ready → not the not-progressing branch."""
    resolver = _resolver()
    instances = [_inst("running"), _inst("failed"), _inst("pending")]
    result = resolver.compute_fulfilment(
        instances, requested_count=3, controller_view={"ready_replicas": 1}
    )
    assert result.state != "failed"


def test_all_failed_is_failed() -> None:
    """The pre-existing all-failed branch still fires."""
    resolver = _resolver()
    instances = [_inst("failed"), _inst("failed")]
    result = resolver.compute_fulfilment(instances, requested_count=2)
    assert result.state == "failed"
