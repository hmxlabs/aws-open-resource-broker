"""Azure DefaultAzureCredential authentication strategy.

Uses the shared Azure infrastructure credential factory so auth and
provider-runtime flows construct the same credential shape.
"""

from typing import Optional

from orb.domain.base.dependency_injection import injectable
from orb.domain.base.ports import LoggingPort
from orb.infrastructure.adapters.ports.auth import (
    AuthContext,
    AuthPort,
    AuthResult,
    AuthStatus,
)
from orb.providers.azure.infrastructure.credential_factory import (
    AzureCredentialProtocol,
    create_default_azure_credential,
    get_default_azure_credential_error_types,
)

EXPECTED_AZURE_AUTH_EXCEPTIONS = (
    ImportError,
    *get_default_azure_credential_error_types(),
)


@injectable
class AzureAuthStrategy(AuthPort):
    """Authentication strategy using Azure DefaultAzureCredential."""

    def __init__(
        self,
        logger: LoggingPort,
        client_id: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self._logger = logger
        self.client_id = client_id
        self.enabled = enabled

    def _create_credential(self) -> AzureCredentialProtocol:
        """Create a short-lived Azure credential for one auth operation."""
        return create_default_azure_credential(
            client_id=self.client_id,
            logger=self._logger,
        )

    async def authenticate(self, context: AuthContext) -> AuthResult:
        if not self.enabled:
            return AuthResult(
                status=AuthStatus.FAILED,
                error_message="Azure auth strategy disabled",
            )
        try:
            credential = self._create_credential()
            try:
                token = credential.get_token("https://management.azure.com/.default")
            finally:
                credential.close()

            return AuthResult(
                status=AuthStatus.SUCCESS,
                user_id=self.client_id or "azure-identity",
                token=token.token,
                user_roles=["provider"],
                permissions=["Microsoft.Compute/*", "Microsoft.Network/*"],
                metadata={
                    "strategy": "azure_default_credential",
                },
            )
        except EXPECTED_AZURE_AUTH_EXCEPTIONS as exc:
            self._logger.error("Azure authentication failed: %s", exc)
            return AuthResult(
                status=AuthStatus.FAILED,
                error_message=f"Azure authentication failed: {exc}",
            )

    async def validate_token(self, token: str) -> AuthResult:
        """Token validation is handled by Azure SDK internally."""
        return AuthResult(
            status=AuthStatus.SUCCESS,
            token=token,
            metadata={"strategy": "azure_default_credential"},
        )

    async def refresh_token(self, refresh_token: str) -> AuthResult:
        """DefaultAzureCredential handles token refresh automatically."""
        try:
            credential = self._create_credential()
            try:
                token = credential.get_token("https://management.azure.com/.default")
            finally:
                credential.close()
            return AuthResult(
                status=AuthStatus.SUCCESS,
                token=token.token,
                metadata={"strategy": "azure_default_credential", "refreshed": True},
            )
        except EXPECTED_AZURE_AUTH_EXCEPTIONS as exc:
            return AuthResult(
                status=AuthStatus.FAILED,
                error_message=f"Token refresh failed: {exc}",
            )

    async def revoke_token(self, token: str) -> bool:
        """Azure ARM tokens cannot be revoked directly."""
        self._logger.debug("Token revocation not supported for Azure ARM tokens")
        return False

    def get_strategy_name(self) -> str:
        return "azure_default_credential"

    def is_enabled(self) -> bool:
        return self.enabled
