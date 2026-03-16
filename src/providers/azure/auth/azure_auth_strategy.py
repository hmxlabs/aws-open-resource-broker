"""Azure DefaultAzureCredential authentication strategy.

Uses the ``azure-identity`` ``DefaultAzureCredential`` chain which
automatically covers managed identity, VS Code credential, Azure CLI,
environment variables, and workload identity federation.
"""

from typing import Any, Optional

from domain.base.dependency_injection import injectable
from domain.base.ports import LoggingPort
from infrastructure.adapters.ports.auth import (
    AuthContext,
    AuthPort,
    AuthResult,
    AuthStatus,
)


@injectable
class AzureAuthStrategy(AuthPort):
    """Authentication strategy using Azure DefaultAzureCredential."""

    def __init__(
        self,
        logger: LoggingPort,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        enabled: bool = True,
    ) -> None:
        self._logger = logger
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.enabled = enabled
        self._credential = None

    def _get_credential(self) -> Any:
        """Lazily create the Azure credential."""
        if self._credential is None:
            try:
                from azure.identity import DefaultAzureCredential

                self._credential = DefaultAzureCredential()
            except ImportError:
                self._logger.error("azure-identity package is not installed")
                raise
        return self._credential

    async def authenticate(self, context: AuthContext) -> AuthResult:
        if not self.enabled:
            return AuthResult(
                status=AuthStatus.FAILED,
                error_message="Azure auth strategy disabled",
            )
        try:
            credential = self._get_credential()
            token = credential.get_token("https://management.azure.com/.default")

            return AuthResult(
                status=AuthStatus.SUCCESS,
                user_id=self.client_id or "azure-identity",
                token=token.token,
                user_roles=["provider"],
                permissions=["Microsoft.Compute/*", "Microsoft.Network/*"],
                metadata={
                    "strategy": "azure_default_credential",
                    "tenant_id": self.tenant_id,
                },
            )
        except Exception as exc:
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
            credential = self._get_credential()
            token = credential.get_token("https://management.azure.com/.default")
            return AuthResult(
                status=AuthStatus.SUCCESS,
                token=token.token,
                metadata={"strategy": "azure_default_credential", "refreshed": True},
            )
        except Exception as exc:
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

