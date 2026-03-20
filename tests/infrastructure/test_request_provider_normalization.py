"""Focused tests for provider-machine normalization in request queries."""

from unittest.mock import MagicMock

from application.queries.handlers import GetRequestHandler


def _make_handler() -> GetRequestHandler:
    container = MagicMock()
    container.get.side_effect = Exception("unused in this test")
    return GetRequestHandler(
        uow_factory=MagicMock(),
        logger=MagicMock(),
        error_handler=MagicMock(),
        container=container,
    )


def test_create_machine_from_provider_data_preserves_azure_provider_type():
    handler = _make_handler()
    request = MagicMock()
    request.request_id = "req-1"
    request.template_id = "azure-vmss-test"
    request.provider_type = "azure"
    request.resource_ids = ["vmss-a", "vmss-b"]

    machine = handler._create_machine_from_provider_data(
        {
            "instance_id": "vmss-instance-1",
            "status": "pending",
            "instance_type": "Standard_D4s_v5",
            "provider_data": {"resource_group": "test-rg"},
        },
        request,
    )

    assert machine.provider_type == "azure"
    assert str(machine.instance_id.value) == "vmss-instance-1"
    assert machine.instance_type.value == "Standard_D4s_v5"
    assert machine.image_id == "unknown"
