"""Azure SDK VM to ORB machine conversion."""

from __future__ import annotations

from typing import Any, Protocol, cast

from orb.domain.base.ports import LoggingPort
from orb.domain.machine.machine_status import MachineStatus
from orb.providers.azure.infrastructure.azure_client import AzureClient


class _AzureVmWithName(Protocol):
    name: str | None


class AzureMachineConversionService:
    """Convert Azure SDK VM objects into the shared machine shape."""

    def __init__(self, logger: LoggingPort) -> None:
        self._logger = logger

    @staticmethod
    def _resolve_power_state(vm: Any) -> str:
        status = MachineStatus.UNKNOWN.value
        instance_view = vm.instance_view
        if not instance_view or not hasattr(instance_view, "statuses"):
            return status

        state_map = {
            "PowerState/running": MachineStatus.RUNNING,
            "PowerState/starting": MachineStatus.PENDING,
            "PowerState/stopping": MachineStatus.STOPPING,
            "PowerState/stopped": MachineStatus.STOPPED,
            "PowerState/deallocating": MachineStatus.SHUTTING_DOWN,
            "PowerState/deallocated": MachineStatus.STOPPED,
        }
        for vm_status in instance_view.statuses:
            code = vm_status.code or ""
            if code.startswith("PowerState/"):
                return state_map.get(code, MachineStatus.UNKNOWN).value
        return status

    def convert_sdk_vm(self, vm: Any, azure_client: AzureClient) -> dict[str, Any]:
        network_identity = azure_client.resolve_network_identity_from_vm(vm)
        vm_name = cast(_AzureVmWithName, vm).name
        hardware_profile = vm.hardware_profile

        return {
            "instance_id": vm.vm_id,
            "status": self._resolve_power_state(vm),
            "private_ip": network_identity["private_ip"],
            "public_ip": network_identity["public_ip"],
            "launch_time": None,
            "instance_type": hardware_profile.vm_size if hardware_profile else None,
            "subnet_id": network_identity["subnet_id"],
            "vpc_id": network_identity["vnet_id"],
            "availability_zone": (vm.zones or [None])[0],
            "provider_type": "azure",
            "provider_data": {
                "vm_name": vm_name,
                "location": vm.location,
                "provisioning_state": vm.provisioning_state,
                "nic_id": network_identity["nic_id"],
                "nic_name": network_identity["nic_name"],
                "vnet_id": network_identity["vnet_id"],
            },
        }
