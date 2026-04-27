"""Azure provider health checks."""

from __future__ import annotations

import asyncio
import builtins
import threading
import time
from collections.abc import Coroutine
from typing import Any, TypeVar
from typing import Optional

from orb.domain.base.ports import LoggingPort
from orb.providers.azure.configuration.config import AzureProviderConfig
from orb.providers.azure.infrastructure.azure_client import AzureClient
from orb.providers.base.strategy import ProviderHealthStatus

_T = TypeVar("_T")


class AzureHealthCheckService:
    """Own the Azure provider health-check interaction."""

    def __init__(self, config: AzureProviderConfig, logger: LoggingPort) -> None:
        self._config = config
        self._logger = logger

    @staticmethod
    def _run_coro_sync(coro: Coroutine[Any, Any, _T]) -> _T | None:
        """Run a coroutine from sync API code without nesting event loops."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        values: list[_T] = []
        errors: list[BaseException] = []

        def _runner() -> None:
            try:
                values.append(asyncio.run(coro))
            except BaseException as exc:  # pragma: no cover - re-raised below
                errors.append(exc)

        thread = threading.Thread(target=_runner, daemon=True)
        thread.start()
        thread.join()
        if errors:
            if all(isinstance(error, Exception) for error in errors):
                raise builtins.ExceptionGroup(
                    "Azure health check coroutine failed",
                    [error for error in errors if isinstance(error, Exception)],
                )
            raise builtins.BaseExceptionGroup("Azure health check coroutine failed", errors)
        return values[0] if values else None

    def check_health(self, azure_client: Optional[AzureClient]) -> ProviderHealthStatus:
        """Perform a synchronous health check through the AzureClient credential path."""
        start_time = time.time()

        try:
            if not azure_client:
                return ProviderHealthStatus.unhealthy(
                    "Azure client initialization failed",
                    {"error": "client_initialization_failed"},
                )

            from orb.infrastructure.mocking.dry_run_context import is_dry_run_active

            if is_dry_run_active():
                response_time_ms = (time.time() - start_time) * 1000
                return ProviderHealthStatus.healthy(
                    f"Azure provider healthy (DRY-RUN) - Region: {self._config.region}",
                    response_time_ms,
                )

            credential_ok = bool(
                self._run_coro_sync(azure_client.validate_credentials_async())
            )
            if not credential_ok:
                response_time_ms = (time.time() - start_time) * 1000
                return ProviderHealthStatus.unhealthy(
                    "Azure provider unhealthy - credential validation failed",
                    {"error": "credential_validation_failed", "response_time_ms": response_time_ms},
                )

            response_time_ms = (time.time() - start_time) * 1000
            return ProviderHealthStatus.healthy(
                f"Azure provider healthy - Token fetched successfully in {response_time_ms}, "
                f"Region: {self._config.region}",
                response_time_ms,
            )
        except Exception as exc:
            self._logger.warning("Azure health check failed: %s", exc, exc_info=True)
            response_time_ms = (time.time() - start_time) * 1000
            return ProviderHealthStatus.unhealthy(
                f"Health check error: {exc!s}",
                {"error": str(exc), "response_time_ms": response_time_ms},
            )

    async def check_health_async(
        self, azure_client: Optional[AzureClient]
    ) -> ProviderHealthStatus:
        """Perform an async health check using the async Azure credential."""
        start_time = time.time()

        try:
            if not azure_client:
                return ProviderHealthStatus.unhealthy(
                    "Azure client initialization failed",
                    {"error": "client_initialization_failed"},
                )

            from orb.infrastructure.mocking.dry_run_context import is_dry_run_active

            if is_dry_run_active():
                response_time_ms = (time.time() - start_time) * 1000
                return ProviderHealthStatus.healthy(
                    f"Azure provider healthy (DRY-RUN) - Region: {self._config.region}",
                    response_time_ms,
                )

            credential_ok = await azure_client.validate_credentials_async()
            if not credential_ok:
                response_time_ms = (time.time() - start_time) * 1000
                return ProviderHealthStatus.unhealthy(
                    "Azure provider unhealthy - credential validation failed",
                    {"error": "credential_validation_failed", "response_time_ms": response_time_ms},
                )

            response_time_ms = (time.time() - start_time) * 1000
            return ProviderHealthStatus.healthy(
                f"Azure provider healthy - Token fetched successfully in {response_time_ms}, "
                f"Region: {self._config.region}",
                response_time_ms,
            )
        except Exception as exc:
            self._logger.warning("Azure health check failed: %s", exc, exc_info=True)
            response_time_ms = (time.time() - start_time) * 1000
            return ProviderHealthStatus.unhealthy(
                f"Health check error: {exc!s}",
                {"error": str(exc), "response_time_ms": response_time_ms},
            )
