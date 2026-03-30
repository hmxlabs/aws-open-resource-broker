"""Azure credential construction owned by Azure infrastructure."""

from __future__ import annotations

from typing import Any, Optional, Protocol

from orb.domain.base.ports import LoggingPort


class AzureCredentialProtocol(Protocol):
    """Credential surface required by Azure provider code."""

    def get_token(self, *scopes: str, **kwargs: Any) -> Any: ...

    def close(self) -> None: ...


def get_default_azure_credential_error_types() -> tuple[type[Exception], ...]:
    """Return the expected Azure SDK exception types for credential operations."""
    try:
        from azure.core.exceptions import ClientAuthenticationError
        from azure.identity import CredentialUnavailableError
    except ImportError:
        return ()

    return CredentialUnavailableError, ClientAuthenticationError


def create_default_azure_credential(
    *,
    client_id: Optional[str],
    logger: LoggingPort,
) -> AzureCredentialProtocol:
    """Create the canonical Azure DefaultAzureCredential for ORB Azure flows."""
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        logger.error("azure-identity package is not installed")
        raise

    credential_kwargs: dict[str, Any] = {}
    if client_id:
        credential_kwargs["managed_identity_client_id"] = client_id

    credential = DefaultAzureCredential(**credential_kwargs)
    logger.info("Azure DefaultAzureCredential initialised")
    return credential
