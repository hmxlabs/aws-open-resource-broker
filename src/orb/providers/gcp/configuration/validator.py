"""GCP configuration and template validation helpers."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from orb.providers.gcp.configuration.config import GCPProviderConfig
from orb.providers.gcp.domain.template.gcp_template_aggregate import GCPTemplate


def validate_gcp_config(config: GCPProviderConfig) -> dict[str, Any]:
    """Validate GCP provider configuration."""
    errors: list[str] = []
    warnings: list[str] = []

    if not config.project_id:
        errors.append("project_id is required for GCP operations")
    if not config.region:
        errors.append("region is required for GCP operations")
    return {"valid": len(errors) == 0, "errors": errors, "warnings": warnings}


def validate_gcp_template(template_config: dict[str, Any]) -> dict[str, Any]:
    """Validate a GCP template configuration."""
    warnings: list[str] = []
    provisioning_model = template_config.get("provisioning_model")
    if provisioning_model and provisioning_model not in {"STANDARD", "SPOT"}:
        warnings.append(
            "provisioning_model should usually be 'STANDARD' or 'SPOT' "
            "(Spot VMs: https://cloud.google.com/compute/docs/instances/spot)"
        )

    try:
        GCPTemplate.model_validate(template_config)
        errors: list[str] = []
    except ValidationError as exc:
        errors = []
        for issue in exc.errors():
            message = issue.get("msg", "Validation error")
            location = ".".join(str(part) for part in issue.get("loc", []))
            errors.append(f"{location}: {message}" if location else message)
    except Exception as exc:
        errors = [str(exc)]

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "validated_fields": list(template_config.keys()),
    }
