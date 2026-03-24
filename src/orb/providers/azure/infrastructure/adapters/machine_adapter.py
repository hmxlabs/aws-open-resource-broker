"""Azure Machine Adapter.

Provides Azure-specific machine normalization and helper operations.
"""

from __future__ import annotations

from typing import Any, Optional

from orb.domain.base.dependency_injection import injectable
from orb.domain.base.ports import LoggingPort
from orb.domain.machine.aggregate import Machine
from orb.domain.machine.machine_status import MachineStatus
from orb.providers.azure.exceptions.azure_exceptions import (
    AzureError,
    NetworkError,
    RateLimitError,
    VMNotFoundError,
)
from orb.providers.azure.infrastructure.azure_client import AzureClient


# Azure power-state codes → domain MachineStatus
_STATUS_MAP: dict[str, MachineStatus] = {
    "pending": MachineStatus.PENDING,
    "running": MachineStatus.RUNNING,
    "stopping": MachineStatus.STOPPING,
    "stopped": MachineStatus.STOPPED,
    "shutting-down": MachineStatus.SHUTTING_DOWN,
    "terminated": MachineStatus.TERMINATED,
    "failed": MachineStatus.FAILED,
    "unknown": MachineStatus.UNKNOWN,
}


@injectable
class AzureMachineAdapter:
    """Adapter for Azure-specific machine operations."""

    def __init__(self, azure_client: AzureClient, logger: LoggingPort) -> None:
        self._azure_client = azure_client
        self._logger = logger

    def create_machine_from_azure_instance(
        self,
        azure_instance_data: dict[str, Any],
        request_id: str,
        provider_api: str,
        resource_id: str,
    ) -> dict[str, Any]:
        """Convert Azure instance data into machine domain data."""
        try:
            machine_data = self.convert_azure_instance_to_machine(azure_instance_data)
            machine_data.update({
                "request_id": request_id,
                "provider_api": provider_api,
                "resource_id": resource_id,
            })

            if not machine_data.get("name"):
                machine_data["name"] = machine_data.get(
                    "private_ip", machine_data.get("instance_id", "")
                )

            if "launch_time" not in machine_data:
                machine_data["launch_time"] = None

            metadata = dict(machine_data.get("metadata", {}) or {})
            if machine_data.get("availability_zone"):
                metadata.setdefault("availability_zone", machine_data["availability_zone"])
            if machine_data.get("subnet_id"):
                metadata.setdefault("subnet_id", machine_data["subnet_id"])
            if machine_data.get("vpc_id"):
                metadata.setdefault("vpc_id", machine_data["vpc_id"])
            machine_data["metadata"] = metadata

            return machine_data
        except AzureError:
            raise
        except Exception as exc:
            self._logger.error("Failed to create machine from Azure instance: %s", exc)
            raise AzureError(f"Failed to create machine from Azure instance: {exc!s}") from exc

    @staticmethod
    def convert_azure_instance_to_machine(azure_instance: dict[str, Any]) -> dict[str, Any]:
        """Convert normalized Azure instance data into machine format."""
        if not isinstance(azure_instance, dict):
            raise AzureError(
                "Azure machine adapter expects normalized dict instance data from handlers"
            )

        data = azure_instance.copy()

        instance_id = data.get("instance_id") or data.get("vm_id") or data.get("name")
        if not instance_id:
            raise AzureError("Missing required Azure instance identifier")

        raw_status = str(data.get("status", "unknown")).strip().lower() or "unknown"
        domain_status = _STATUS_MAP.get(raw_status, MachineStatus.UNKNOWN)

        instance_type = data.get("instance_type") or "unknown"
        provider_data = dict(data.get("provider_data", {}) or {})
        metadata = dict(data.get("metadata", {}) or {})

        availability_zone = data.get("availability_zone")
        subnet_id = data.get("subnet_id")
        vpc_id = data.get("vpc_id")

        if availability_zone:
            metadata.setdefault("availability_zone", availability_zone)
        if subnet_id:
            metadata.setdefault("subnet_id", subnet_id)
        if vpc_id:
            metadata.setdefault("vpc_id", vpc_id)

        return {
            "instance_id": str(instance_id),
            "name": data.get("name") or data.get("private_ip") or str(instance_id),
            "status": domain_status.value,
            "private_ip": data.get("private_ip"),
            "public_ip": data.get("public_ip"),
            "launch_time": data.get("launch_time"),
            "instance_type": instance_type,
            "subnet_id": subnet_id,
            "vpc_id": vpc_id,
            "availability_zone": availability_zone,
            "provider_type": "azure",
            "provider_data": provider_data,
            "metadata": metadata,
        }

    def perform_health_check(self, machine: Machine) -> dict[str, Any]:
        """Perform a basic Azure VM health check."""
        self._logger.debug("Performing Azure health check for machine: %s", machine.machine_id)

        resource_group = self._resolve_resource_group(machine)
        vm_name = self._resolve_vm_name(machine)

        try:
            vm = self._azure_client.compute_client.virtual_machines.get(
                resource_group_name=resource_group,
                vm_name=vm_name,
                expand="instanceView",
            )
        except Exception as exc:
            self._raise_azure_lookup_error(machine, exc)

        statuses = getattr(getattr(vm, "instance_view", None), "statuses", []) or []
        system_status = self._find_status_code(statuses, "ProvisioningState/")
        power_status = self._find_status_code(statuses, "PowerState/")

        return {
            "system": {
                "status": system_status in (None, "ProvisioningState/succeeded"),
                "details": {"status": system_status or "unknown"},
            },
            "instance": {
                "status": power_status in (None, "PowerState/running"),
                "details": {"status": power_status or "unknown"},
            },
        }

    @staticmethod
    def _find_status_code(statuses: list[Any], prefix: str) -> Optional[str]:
        for status in statuses:
            code = getattr(status, "code", None)
            if code and str(code).startswith(prefix):
                return str(code)
        return None

    def _resolve_resource_group(self, machine: Machine) -> str:
        resource_group = (
            machine.provider_data.get("resource_group")
            or machine.metadata.get("resource_group")
            or self._azure_client.resource_group
        )
        if not resource_group:
            raise AzureError("resource_group is required for Azure machine operations")
        return str(resource_group)

    @staticmethod
    def _resolve_vm_name(machine: Machine) -> str:
        return str(
            machine.provider_data.get("vm_name")
            or machine.get_provider_data("vm_name")
            or machine.machine_id
        )

    @staticmethod
    def _raise_azure_lookup_error(machine: Machine, exc: Exception) -> None:
        message = str(exc)
        lower = message.lower()
        if "notfound" in lower or "could not be found" in lower:
            raise VMNotFoundError(
                f"Azure VM not found: {machine.machine_id}",
                instance_id=str(machine.machine_id),
            ) from exc
        if "429" in lower or "throttl" in lower:
            raise RateLimitError(f"Azure rate limit exceeded: {message}") from exc
        if "timeout" in lower or "connection" in lower or "network" in lower:
            raise NetworkError(f"Azure network error: {message}") from exc
        raise AzureError(f"Azure health check failed: {message}") from exc
