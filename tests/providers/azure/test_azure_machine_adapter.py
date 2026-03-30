"""Focused tests for AzureMachineAdapter."""

from unittest.mock import MagicMock

import pytest

from orb.domain.base.value_objects import InstanceId, InstanceType
from orb.domain.machine.aggregate import Machine
from orb.providers.azure.exceptions.azure_exceptions import AzureError, VMNotFoundError
from orb.providers.azure.infrastructure.adapters.machine_adapter import AzureMachineAdapter


def test_create_machine_from_normalized_instance_adds_metadata():
    azure_client = MagicMock()
    adapter = AzureMachineAdapter(azure_client=azure_client, logger=MagicMock())

    result = adapter.create_machine_from_azure_instance(
        {
            "instance_id": "vm-1",
            "status": "running",
            "private_ip": "10.0.0.4",
            "instance_type": "Standard_D4s_v5",
            "provider_data": {"resource_group": "rg"},
        },
        request_id="req-1",
        provider_api="SingleVM",
        resource_id="vm-1",
    )

    assert result["instance_id"] == "vm-1"
    assert result["request_id"] == "req-1"
    assert result["provider_api"] == "SingleVM"
    assert result["resource_id"] == "vm-1"
    assert result["status"] == "running"
    assert result["name"] == "10.0.0.4"


def test_convert_normalized_dict_to_machine():
    azure_client = MagicMock()
    adapter = AzureMachineAdapter(azure_client=azure_client, logger=MagicMock())

    result = adapter.convert_azure_instance_to_machine({
        "instance_id": "vm-guid",
        "name": "vm-name",
        "status": "running",
        "instance_type": "Standard_D4s_v5",
        "availability_zone": "1",
        "provider_data": {"location": "eastus2"},
    })

    assert result["instance_id"] == "vm-guid"
    assert result["name"] == "vm-name"
    assert result["status"] == "running"
    assert result["instance_type"] == "Standard_D4s_v5"
    assert result["availability_zone"] == "1"


def test_convert_rejects_missing_identifier():
    azure_client = MagicMock()
    adapter = AzureMachineAdapter(azure_client=azure_client, logger=MagicMock())

    with pytest.raises(AzureError, match="Missing required Azure instance identifier"):
        adapter.convert_azure_instance_to_machine({"status": "running"})


def test_convert_rejects_non_dict_input():
    azure_client = MagicMock()
    adapter = AzureMachineAdapter(azure_client=azure_client, logger=MagicMock())

    with pytest.raises(AzureError, match="expects normalized dict instance data"):
        adapter.convert_azure_instance_to_machine(MagicMock())


def test_perform_health_check_maps_power_and_provisioning_status():
    azure_client = MagicMock()
    azure_client.resource_group = "rg"
    vm = MagicMock()
    power = MagicMock()
    power.code = "PowerState/running"
    provisioning = MagicMock()
    provisioning.code = "ProvisioningState/succeeded"
    vm.instance_view.statuses = [provisioning, power]
    azure_client.compute_client.virtual_machines.get.return_value = vm

    adapter = AzureMachineAdapter(azure_client=azure_client, logger=MagicMock())
    machine = Machine(
        instance_id=InstanceId(value="vm-1"),
        template_id="tpl-1",
        provider_type="azure",
        provider_name="azure-default",
        instance_type=InstanceType(value="Standard_D4s_v5"),
        image_id="img-1",
        provider_data={"resource_group": "rg", "vm_name": "vm-1"},
    )

    result = adapter.perform_health_check(machine)

    assert result["system"]["status"] is True
    assert result["instance"]["status"] is True


def test_perform_health_check_raises_vm_not_found():
    from azure.core.exceptions import ResourceNotFoundError

    azure_client = MagicMock()
    azure_client.resource_group = "rg"
    azure_client.compute_client.virtual_machines.get.side_effect = ResourceNotFoundError("NotFound")
    adapter = AzureMachineAdapter(azure_client=azure_client, logger=MagicMock())
    machine = Machine(
        instance_id=InstanceId(value="vm-1"),
        template_id="tpl-1",
        provider_type="azure",
        provider_name="azure-default",
        instance_type=InstanceType(value="Standard_D4s_v5"),
        image_id="img-1",
        provider_data={"resource_group": "rg"},
    )

    with pytest.raises(VMNotFoundError):
        adapter.perform_health_check(machine)

