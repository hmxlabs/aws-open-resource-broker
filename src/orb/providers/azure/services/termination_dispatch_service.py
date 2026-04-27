"""Azure termination dispatch helpers."""

from __future__ import annotations

import asyncio
import builtins
from typing import Callable

from orb.domain.base.ports import LoggingPort
from orb.providers.azure.infrastructure.handlers.azure_handler import (
    AzureHandler,
    AzureReleaseContext,
    AzureReleaseProviderData,
    AzureReleaseHostsResult,
)


class AzureTerminationDispatchService:
    """Own the handler fan-out used by Azure termination flows."""

    def __init__(
        self,
        logger: LoggingPort,
        record_pending_cleanup: Callable[[AzureReleaseHostsResult | None], None],
    ) -> None:
        self._logger = logger
        self._record_pending_cleanup = record_pending_cleanup

    async def dispatch_async(
        self,
        *,
        handler: AzureHandler,
        instance_ids: list[str],
        grouped_resource_mapping: dict[str, list[str]],
        default_resource_id: str,
        context: AzureReleaseContext,
    ) -> list[AzureReleaseProviderData]:
        """Fan out async release_hosts calls per resource and collect provider data."""
        termination_provider_data: list[AzureReleaseProviderData] = []
        dispatch_failures: list[Exception] = []

        dispatch_groups = grouped_resource_mapping or {default_resource_id: instance_ids}
        handler_results = await asyncio.gather(
            *[
                handler.release_hosts_async(
                    machine_ids=mapped_instance_ids,
                    resource_id=resource_id,
                    context=context,
                )
                for resource_id, mapped_instance_ids in dispatch_groups.items()
            ],
            return_exceptions=True,
        )
        for handler_result in handler_results:
            if isinstance(handler_result, BaseException):
                if isinstance(handler_result, asyncio.CancelledError):
                    raise handler_result
                if not isinstance(handler_result, Exception):
                    raise handler_result
                dispatch_failures.append(handler_result)
                self._logger.warning(
                    "Azure termination dispatch group failed: %s",
                    handler_result,
                    exc_info=True,
                )
                continue
            self._record_pending_cleanup(handler_result)
            if handler_result is None:
                continue

            provider_data = handler_result.get("provider_data")
            if provider_data is not None:
                termination_provider_data.append(provider_data)

        if dispatch_failures and not termination_provider_data:
            if len(dispatch_failures) > 1:
                raise builtins.ExceptionGroup(
                    "All Azure termination dispatch groups failed",
                    dispatch_failures,
                )
            raise dispatch_failures[0]
        return termination_provider_data
