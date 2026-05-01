"""Machine status → HostFactory result mapping.

Single source of truth for the status→result translation used across the
application layer (DTOs, query handlers) and infrastructure formatters.
"""


def map_machine_status_to_result(
    status: str | None, request_type: str | None = None
) -> str:
    """Map machine status to HostFactory result field.

    Args:
        status: Domain machine status string (e.g. ``"running"``, ``"pending"``).
        request_type: Optional request type string.  When ``"return"``, terminated
            and stopped states map to ``"succeed"`` rather than ``"fail"``.

    Returns:
        One of ``"succeed"``, ``"executing"``, or ``"fail"``.
    """
    if request_type == "return":
        if status in ["terminated", "stopped"]:
            return "succeed"
        elif status in ["shutting-down", "stopping", "pending", "terminating", "running"]:
            return "executing"
        else:
            return "fail"
    elif status == "running":
        return "succeed"
    elif status in ["pending", "launching"]:
        return "executing"
    elif status in ["terminated", "failed", "error"]:
        return "fail"
    else:
        return "executing"
