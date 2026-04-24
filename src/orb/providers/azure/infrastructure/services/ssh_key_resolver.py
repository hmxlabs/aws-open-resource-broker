"""SSH key resolution service.

Resolves Azure SSH Public Key resource names to actual key data via
the Compute SDK, keeping infrastructure concerns out of the domain model.
"""

from __future__ import annotations

from typing import NoReturn

from typing import Any


def _azure_resource_not_found_error_type() -> type[Exception]:
    """Resolve the Azure SDK's not-found exception lazily."""
    from azure.core.exceptions import ResourceNotFoundError

    return ResourceNotFoundError


def _azure_http_response_error_type() -> type[Exception]:
    """Resolve the Azure SDK's HTTP response exception lazily."""
    from azure.core.exceptions import HttpResponseError

    return HttpResponseError


def _validate_ssh_key_request(
    *,
    ssh_key_name: str | None,
    ssh_public_keys: list[str],
) -> list[str]:
    """Return inline keys or raise when no resolvable key source is configured."""
    if ssh_public_keys:
        return list(ssh_public_keys)

    if not ssh_key_name:
        raise ValueError(
            "Cannot resolve SSH keys: neither 'ssh_key_name' nor "
            "'ssh_public_keys' is set on the template."
        )
    return []


def _extract_key_data(
    *,
    ssh_resource: Any,
    ssh_key_name: str,
    resource_group: str,
) -> list[str]:
    """Validate resolved Azure SSH key payload and return it in ORB list form."""
    key_data: str = ssh_resource.public_key
    if not key_data:
        raise ValueError(
            f"Azure SSH Public Key resource '{ssh_key_name}' "
            f"in resource group '{resource_group}' exists but "
            f"contains no public key data."
        )
    return [key_data]


def _translate_ssh_key_resolution_error(
    *,
    exc: Exception,
    ssh_key_name: str,
    resource_group: str,
) -> ValueError | NoReturn:
    """Translate Azure SDK lookup failures into stable provider-facing errors."""
    if isinstance(exc, _azure_resource_not_found_error_type()):
        return ValueError(
            f"Azure SSH Public Key resource '{ssh_key_name}' "
            f"in resource group '{resource_group}' was not found. "
            f"Ensure the resource exists and the caller has "
            f"'Microsoft.Compute/sshPublicKeys/read' permission."
        )
    if isinstance(exc, _azure_http_response_error_type()):
        return ValueError(
            f"Failed to resolve Azure SSH Public Key '{ssh_key_name}' "
            f"in resource group '{resource_group}': {exc}"
        )
    raise exc


async def resolve_ssh_keys_async(
    *,
    ssh_key_name: str | None,
    ssh_public_keys: list[str],
    resource_group: str,
    compute_client: Any,
) -> list[str]:
    """Async variant of ``resolve_ssh_keys`` for the Azure async SDK clients."""
    inline_keys = _validate_ssh_key_request(
        ssh_key_name=ssh_key_name,
        ssh_public_keys=ssh_public_keys,
    )
    if inline_keys:
        return inline_keys

    try:
        ssh_resource = await compute_client.ssh_public_keys.get(
            resource_group_name=resource_group,
            ssh_public_key_name=ssh_key_name,
        )
        return _extract_key_data(
            ssh_resource=ssh_resource,
            ssh_key_name=str(ssh_key_name),
            resource_group=resource_group,
        )
    except Exception as exc:
        translated = _translate_ssh_key_resolution_error(
            exc=exc,
            ssh_key_name=str(ssh_key_name),
            resource_group=resource_group,
        )
        raise translated from exc
