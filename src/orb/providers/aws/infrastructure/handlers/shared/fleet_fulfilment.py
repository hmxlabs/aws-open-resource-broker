"""Shared fleet fulfilment computation helpers.

Both EC2 Fleet (Maintain/Request types) and Spot Fleet share identical
capacity-based fulfilment semantics: FulfilledCapacity >= TargetCapacity AND
no pending or failed instances → fulfilled.  The only difference is the label
used in human-readable messages.

``compute_ec2fleet_fulfilment`` handles the full EC2 Fleet decision tree,
dispatching to ``compute_capacity_based_fulfilment`` for Maintain/Request fleet
types and using count-based logic for Instant fleets.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from orb.providers.aws.domain.template.value_objects import AWSFleetType

from orb.domain.base.provider_fulfilment import ProviderFulfilment


def compute_capacity_based_fulfilment(
    target_capacity: Optional[int],
    fulfilled_capacity: float,
    running_count: int,
    pending_count: int,
    failed_count: int,
    provider_label: str,
) -> ProviderFulfilment:
    """Compute ProviderFulfilment for a capacity-unit based fleet.

    Used by EC2 Fleet (Maintain/Request) and Spot Fleet handlers.

    Args:
        target_capacity: The fleet's TargetCapacity, or None if unknown.
        fulfilled_capacity: The fleet's FulfilledCapacity as reported by AWS.
        running_count: Number of instances whose status is "running".
        pending_count: Number of instances whose status is "pending" or "starting".
        failed_count: Number of instances whose status is "failed" or "error".
        provider_label: Label used in messages, e.g. "Fleet" or "Spot Fleet".
    """
    target_units = target_capacity if target_capacity is not None else int(fulfilled_capacity)
    fleet_fully_fulfilled = target_capacity is not None and fulfilled_capacity >= target_capacity

    if fleet_fully_fulfilled and pending_count == 0 and failed_count == 0:
        return ProviderFulfilment(
            state="fulfilled",
            message=(
                f"{provider_label} fulfilled: {running_count} instance(s) running "
                f"({fulfilled_capacity}/{target_capacity} capacity units)"
            ),
            target_units=target_units,
            fulfilled_units=int(fulfilled_capacity),
            running_count=running_count,
            pending_count=pending_count,
            failed_count=failed_count,
        )
    elif failed_count > 0 and running_count == 0 and pending_count == 0:
        return ProviderFulfilment(
            state="failed",
            message=f"{provider_label} failed: {failed_count} instance(s) failed",
            target_units=target_units,
            fulfilled_units=int(fulfilled_capacity),
            running_count=running_count,
            pending_count=pending_count,
            failed_count=failed_count,
        )
    else:
        return ProviderFulfilment(
            state="in_progress",
            message=(
                f"{provider_label}: {running_count} running, {pending_count} pending "
                f"({fulfilled_capacity}/{target_units} capacity units)"
            ),
            target_units=target_units,
            fulfilled_units=int(fulfilled_capacity),
            running_count=running_count,
            pending_count=pending_count,
            failed_count=failed_count,
        )


def compute_ec2fleet_fulfilment(
    fleet_type: "AWSFleetType | None",
    instances: list[dict[str, Any]],
    target_capacity: Optional[int],
    fulfilled_capacity: float,
    requested_count: int,
) -> ProviderFulfilment:
    """Compute ProviderFulfilment for an EC2 Fleet request.

    Instant fleets use count-based semantics (same as RunInstances):
    ``running_count >= requested_count`` and ``failed_count == 0`` → fulfilled.

    Maintain / Request fleets use capacity-unit semantics delegated to
    :func:`compute_capacity_based_fulfilment`.

    Args:
        fleet_type: The ``AWSFleetType`` enum value, or ``None`` if unknown.
        instances: List of instance-status dicts (each must have a ``"status"`` key).
        target_capacity: The fleet's TargetCapacity, or None if unknown.
        fulfilled_capacity: The fleet's FulfilledCapacity as reported by AWS.
        requested_count: Number of instances originally requested.
    """
    # Import here to avoid a circular dependency at module load time.
    # fleet_fulfilment is in ``shared/`` and aws_template_aggregate is a peer
    # domain object — the TYPE_CHECKING guard above keeps pyright happy for
    # type annotations while this runtime import is negligible (cached).
    from orb.providers.aws.domain.template.value_objects import AWSFleetType

    running_count = sum(1 for i in instances if i.get("status") == "running")
    pending_count = sum(1 for i in instances if i.get("status") in ("pending", "starting"))
    failed_count = sum(1 for i in instances if i.get("status") in ("failed", "error"))
    target_units = target_capacity if target_capacity is not None else requested_count

    if fleet_type == AWSFleetType.INSTANT:
        # Instant fleet: synchronous result, count-based (same as RunInstances)
        if running_count >= requested_count and failed_count == 0:
            return ProviderFulfilment(
                state="fulfilled",
                message=f"Instant fleet: {running_count} instance(s) running",
                target_units=target_units,
                fulfilled_units=running_count,
                running_count=running_count,
                pending_count=pending_count,
                failed_count=failed_count,
            )
        elif pending_count > 0:
            return ProviderFulfilment(
                state="in_progress",
                message=f"Instant fleet: {running_count}/{requested_count} running, {pending_count} pending",
                target_units=target_units,
                fulfilled_units=running_count,
                running_count=running_count,
                pending_count=pending_count,
                failed_count=failed_count,
            )
        # requires_async_polling=True for instant — pending state must be observed
        elif running_count > 0:
            return ProviderFulfilment(
                state="partial",
                message=f"Instant fleet: {running_count}/{requested_count} instance(s) running",
                target_units=target_units,
                fulfilled_units=running_count,
                running_count=running_count,
                pending_count=pending_count,
                failed_count=failed_count,
            )
        elif not instances:
            return ProviderFulfilment(
                state="in_progress",
                message="Instant fleet: waiting for instances",
                target_units=target_units,
                fulfilled_units=0,
                running_count=0,
                pending_count=0,
                failed_count=0,
            )
        else:
            return ProviderFulfilment(
                state="failed",
                message="Instant fleet: all instances failed",
                target_units=target_units,
                fulfilled_units=0,
                running_count=running_count,
                pending_count=pending_count,
                failed_count=failed_count,
            )
    else:
        # Maintain / Request fleet: capacity-unit based fulfilment
        return compute_capacity_based_fulfilment(
            target_capacity=target_capacity,
            fulfilled_capacity=fulfilled_capacity,
            running_count=running_count,
            pending_count=pending_count,
            failed_count=failed_count,
            provider_label="Fleet",
        )
