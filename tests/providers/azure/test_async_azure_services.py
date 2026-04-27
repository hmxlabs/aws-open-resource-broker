"""Direct async coverage for Azure async service entry points."""

import asyncio
import builtins
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from orb.providers.azure.domain.template.value_objects import AzureProviderApi
from orb.providers.azure.exceptions.azure_exceptions import AzureValidationError
from orb.providers.azure.infrastructure.handlers.azure_handler import AzureReleaseContext
from orb.providers.azure.infrastructure.services.azure_deployment_service import (
    AzureDeploymentService,
)
from orb.providers.azure.services.health_check_service import AzureHealthCheckService
from orb.providers.azure.services.inventory_query_service import AzureInventoryQueryService
from orb.providers.azure.services.inventory_service import AzureReadOperationContext
from orb.providers.azure.services.provisioning_service import (
    AzureProvisioningService,
    CreateOperationContext,
)
from orb.providers.azure.services.termination_dispatch_service import (
    AzureTerminationDispatchService,
)
from tests.providers.azure.strategy_test_support import make_azure_template


def _make_template(**overrides):
    return make_azure_template(
        template_id="azure-service-test",
        provider_api="SingleVM",
        ssh_public_keys=["ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABg service@test"],
        **overrides,
    )


@pytest.fixture
def resource_metadata_service() -> MagicMock:
    service = MagicMock()
    service.augment_vmss_capacity_metadata_async = AsyncMock()
    service.augment_single_vm_deployment_metadata_async = AsyncMock()
    return service


@pytest.mark.asyncio
async def test_dispatch_async_collects_provider_data_and_records_cleanup():
    service = AzureTerminationDispatchService(
        logger=MagicMock(),
        record_pending_cleanup=MagicMock(),
    )
    handler = MagicMock()
    handler.release_hosts_async = AsyncMock(
        return_value={"provider_data": {"operation_status": "submitted"}}
    )

    result = await service.dispatch_async(
        handler=handler,
        instance_ids=["vm-1"],
        grouped_resource_mapping={"vmss-1": ["vm-1"]},
        default_resource_id="vmss-1",
        context=AzureReleaseContext(resource_group="test-rg"),
    )

    assert result == [{"operation_status": "submitted"}]


@pytest.mark.asyncio
async def test_dispatch_async_fans_out_across_multiple_resource_groups():
    cleanup_recorder = MagicMock()
    service = AzureTerminationDispatchService(
        logger=MagicMock(),
        record_pending_cleanup=cleanup_recorder,
    )
    handler = MagicMock()
    handler.release_hosts_async = AsyncMock(
        side_effect=[
            {"provider_data": {"resource_id": "vmss-1"}},
            {"provider_data": {"resource_id": "vmss-2"}},
        ]
    )

    result = await service.dispatch_async(
        handler=handler,
        instance_ids=["vm-1", "vm-2"],
        grouped_resource_mapping={"vmss-1": ["vm-1"], "vmss-2": ["vm-2"]},
        default_resource_id="vmss-ignored",
        context=AzureReleaseContext(resource_group="test-rg"),
    )

    assert result == [{"resource_id": "vmss-1"}, {"resource_id": "vmss-2"}]
    assert handler.release_hosts_async.await_count == 2
    cleanup_recorder.assert_called()


@pytest.mark.asyncio
async def test_dispatch_async_preserves_group_order_when_release_calls_complete_out_of_order():
    cleanup_recorder = MagicMock()
    service = AzureTerminationDispatchService(
        logger=MagicMock(),
        record_pending_cleanup=cleanup_recorder,
    )
    handler = MagicMock()

    async def release_hosts_async(*, machine_ids, resource_id, context):
        _ = machine_ids, context
        if resource_id == "vmss-1":
            await asyncio.sleep(0.02)
        return {"provider_data": {"resource_id": resource_id}}

    handler.release_hosts_async = AsyncMock(side_effect=release_hosts_async)

    result = await service.dispatch_async(
        handler=handler,
        instance_ids=["vm-1", "vm-2"],
        grouped_resource_mapping={"vmss-1": ["vm-1"], "vmss-2": ["vm-2"]},
        default_resource_id="vmss-ignored",
        context=AzureReleaseContext(resource_group="test-rg"),
    )

    assert result == [{"resource_id": "vmss-1"}, {"resource_id": "vmss-2"}]
    assert cleanup_recorder.call_args_list[0].args[0]["provider_data"]["resource_id"] == "vmss-1"
    assert cleanup_recorder.call_args_list[1].args[0]["provider_data"]["resource_id"] == "vmss-2"


@pytest.mark.asyncio
async def test_dispatch_async_preserves_partial_success_when_one_group_fails():
    cleanup_recorder = MagicMock()
    logger = MagicMock()
    service = AzureTerminationDispatchService(
        logger=logger,
        record_pending_cleanup=cleanup_recorder,
    )
    handler = MagicMock()
    handler.release_hosts_async = AsyncMock(
        side_effect=[
            {"provider_data": {"resource_id": "vmss-1"}},
            RuntimeError("delete failed"),
        ]
    )

    result = await service.dispatch_async(
        handler=handler,
        instance_ids=["vm-1", "vm-2"],
        grouped_resource_mapping={"vmss-1": ["vm-1"], "vmss-2": ["vm-2"]},
        default_resource_id="vmss-ignored",
        context=AzureReleaseContext(resource_group="test-rg"),
    )

    assert result == [{"resource_id": "vmss-1"}]
    cleanup_recorder.assert_called_once()
    logger.warning.assert_called()


@pytest.mark.asyncio
async def test_dispatch_async_raises_when_all_groups_fail():
    service = AzureTerminationDispatchService(
        logger=MagicMock(),
        record_pending_cleanup=MagicMock(),
    )
    handler = MagicMock()
    handler.release_hosts_async = AsyncMock(side_effect=RuntimeError("delete failed"))

    with pytest.raises(RuntimeError, match="delete failed"):
        await service.dispatch_async(
            handler=handler,
            instance_ids=["vm-1"],
            grouped_resource_mapping={"vmss-1": ["vm-1"]},
            default_resource_id="vmss-1",
            context=AzureReleaseContext(resource_group="test-rg"),
        )


@pytest.mark.asyncio
async def test_execute_create_handler_async_normalizes_handler_result():
    service = AzureProvisioningService()
    handler = MagicMock()
    handler.acquire_hosts_async = AsyncMock(
        return_value={
            "success": True,
            "resource_ids": ["vm-1"],
            "instances": [],
            "error_message": None,
            "provider_data": {"operation_status": "submitted"},
        }
    )
    create_context = CreateOperationContext(
        template_config={"provider_api": "SingleVM"},
        count=1,
        provider_api=AzureProviderApi.SINGLE_VM,
        provider_api_key="SingleVM",
        handler=handler,
        azure_template=_make_template(),
    )

    result = await service.execute_create_handler_async(
        create_context=create_context,
        request=MagicMock(),
    )

    assert result.success is True
    assert result.data["resource_ids"] == ["vm-1"]
    assert result.metadata["handler_used"] == "SingleVM"


@pytest.mark.asyncio
async def test_execute_create_handler_async_returns_provider_error_for_failed_handler_result():
    service = AzureProvisioningService()
    handler = MagicMock()
    handler.acquire_hosts_async = AsyncMock(
        return_value={
            "success": False,
            "resource_ids": [],
            "instances": [],
            "error_message": "quota exhausted",
            "provider_data": {"error_codes": ["AllocationFailed"]},
        }
    )
    create_context = CreateOperationContext(
        template_config={"provider_api": "SingleVM"},
        count=1,
        provider_api=AzureProviderApi.SINGLE_VM,
        provider_api_key="SingleVM",
        handler=handler,
        azure_template=_make_template(),
    )

    result = await service.execute_create_handler_async(
        create_context=create_context,
        request=MagicMock(),
    )

    assert result.success is False
    assert result.error_code == "PROVISIONING_ADAPTER_ERROR"
    assert result.error_message == "Provisioning failed: quota exhausted"
    assert result.metadata["provider_data"]["error_codes"] == ["AllocationFailed"]


@pytest.mark.asyncio
async def test_get_instance_status_async_uses_async_handler_dispatch(resource_metadata_service):
    service = AzureInventoryQueryService(
        logger=MagicMock(),
        provider_instance_name="azure-default",
        resource_metadata_service=resource_metadata_service,
    )
    handler = MagicMock()
    handler.check_hosts_status_async = AsyncMock(
        return_value=[{"instance_id": "vm-1", "provider_data": {"vm_name": "vm-1"}}]
    )
    read_context = AzureReadOperationContext(
        operation_name="get_instance_status",
        request_id="req-12345678-1234-1234-1234-123456789012",
        template_id="tpl-1",
        request_metadata={},
        cyclecloud_request_context=MagicMock(),
        provider_api=AzureProviderApi.SINGLE_VM,
        provider_api_key="SingleVM",
        resource_group="test-rg",
        instance_ids=["vm-1"],
        resource_ids=["vm-1"],
        direct_resource_id="vm-1",
    )

    result = await service.get_instance_status_async(
        read_context=read_context,
        resolve_handler=lambda *_args, **_kwargs: handler,
        vmss_cleanup_coordinator=MagicMock(),
    )

    assert result.success is True
    assert result.data["instances"][0]["instance_id"] == "vm-1"
    handler.check_hosts_status_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_instance_status_async_rejects_queries_without_provider_api(
    resource_metadata_service,
):
    service = AzureInventoryQueryService(
        logger=MagicMock(),
        provider_instance_name="azure-default",
        resource_metadata_service=resource_metadata_service,
    )
    read_context = AzureReadOperationContext(
        operation_name="get_instance_status",
        request_id="req-12345678-1234-1234-1234-123456789012",
        template_id="tpl-1",
        request_metadata={},
        cyclecloud_request_context=MagicMock(),
        provider_api=None,
        provider_api_key=None,
        resource_group="test-rg",
        instance_ids=["vm-1"],
    )
    with pytest.raises(AzureValidationError, match="provider_api-backed handler resolution"):
        await service.get_instance_status_async(
            read_context=read_context,
            resolve_handler=lambda *_args, **_kwargs: None,
            vmss_cleanup_coordinator=MagicMock(),
        )


@pytest.mark.asyncio
async def test_describe_resource_instances_async_builds_result_from_async_handler(
    resource_metadata_service,
):
    service = AzureInventoryQueryService(
        logger=MagicMock(),
        provider_instance_name="azure-default",
        resource_metadata_service=resource_metadata_service,
    )
    handler = MagicMock()
    handler.check_hosts_status_async = AsyncMock(
        return_value=[{"instance_id": "vm-1", "provider_data": {"vm_name": "vm-1"}}]
    )
    read_context = AzureReadOperationContext(
        operation_name="describe_resource_instances",
        request_id="req-12345678-1234-1234-1234-123456789012",
        template_id="tpl-1",
        request_metadata={"deployment_name": "dep-1"},
        cyclecloud_request_context=MagicMock(),
        provider_api=AzureProviderApi.SINGLE_VM,
        provider_api_key="SingleVM",
        resource_group="test-rg",
        resource_ids=["vm-1"],
    )

    result = await service.describe_resource_instances_async(
        read_context=read_context,
        resolve_handler=lambda *_args, **_kwargs: handler,
        vmss_cleanup_coordinator=MagicMock(),
        resource_manager=None,
        deployment_service=None,
    )

    assert result.success is True
    assert result.data["instances"][0]["instance_id"] == "vm-1"
    resource_metadata_service.augment_shortfall_metadata.assert_called_once()
    resource_metadata_service.augment_single_vm_deployment_metadata_async.assert_not_awaited()


@pytest.mark.asyncio
async def test_submit_template_deployment_async_uses_async_resources_api():
    azure_client = MagicMock()
    async_resource_client = MagicMock()
    async_resource_client.resources.begin_create_or_update = AsyncMock()
    azure_client.get_async_resource_client = AsyncMock(return_value=async_resource_client)
    service = AzureDeploymentService(azure_client=azure_client, logger=MagicMock())

    deployment_name = await service.submit_template_deployment_async(
        resource_group="test-rg",
        deployment_name="dep-1",
        template={"resources": []},
        parameters={"vmName": {"value": "vm-1"}},
    )

    assert deployment_name == "dep-1"
    async_resource_client.resources.begin_create_or_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_deployment_status_async_extracts_provisioning_and_error_fields():
    azure_client = MagicMock()
    async_resource_client = MagicMock()
    async_resource_client.resources.get = AsyncMock(
        return_value=SimpleNamespace(
            properties={
                "provisioningState": "Failed",
                "error": {
                    "code": "DeploymentFailed",
                    "message": "template validation failed",
                },
            }
        )
    )
    azure_client.get_async_resource_client = AsyncMock(return_value=async_resource_client)
    service = AzureDeploymentService(azure_client=azure_client, logger=MagicMock())

    status = await service.get_deployment_status_async(
        resource_group="test-rg",
        deployment_name="dep-1",
    )

    assert status == {
        "provisioning_state": "Failed",
        "error_code": "DeploymentFailed",
        "error_message": "template validation failed",
    }


@pytest.mark.asyncio
async def test_describe_resource_instances_async_awaits_vmss_async_metadata_and_cleanup(
    resource_metadata_service,
):
    service = AzureInventoryQueryService(
        logger=MagicMock(),
        provider_instance_name="azure-default",
        resource_metadata_service=resource_metadata_service,
    )
    handler = MagicMock()
    handler.check_hosts_status_async = AsyncMock(return_value=[])
    handler.get_vmss_resource_errors_async = AsyncMock(
        return_value=[{"error_code": "ProvisioningStateFailed"}]
    )
    cleanup = MagicMock()
    cleanup.reconcile = AsyncMock()
    read_context = AzureReadOperationContext(
        operation_name="describe_resource_instances",
        request_id="req-12345678-1234-1234-1234-123456789012",
        template_id="tpl-1",
        request_metadata={},
        cyclecloud_request_context=MagicMock(),
        provider_api=AzureProviderApi.VMSS,
        provider_api_key="VMSS",
        resource_group="test-rg",
        resource_ids=["vmss-1"],
    )

    result = await service.describe_resource_instances_async(
        read_context=read_context,
        resolve_handler=lambda *_args, **_kwargs: handler,
        vmss_cleanup_coordinator=cleanup,
        resource_manager=MagicMock(),
        deployment_service=None,
    )

    assert result.success is True
    assert result.metadata["fleet_errors"] == [{"error_code": "ProvisioningStateFailed"}]
    handler.get_vmss_resource_errors_async.assert_awaited_once_with("test-rg", "vmss-1")
    resource_metadata_service.augment_vmss_capacity_metadata_async.assert_awaited_once()
    cleanup.reconcile.assert_awaited_once()


@pytest.mark.asyncio
async def test_describe_resource_instances_async_uses_empty_vmss_error_list_without_override(
    resource_metadata_service,
):
    service = AzureInventoryQueryService(
        logger=MagicMock(),
        provider_instance_name="azure-default",
        resource_metadata_service=resource_metadata_service,
    )
    handler = MagicMock()
    handler.check_hosts_status_async = AsyncMock(return_value=[])
    handler.get_vmss_resource_errors_async = AsyncMock(return_value=[])
    read_context = AzureReadOperationContext(
        operation_name="describe_resource_instances",
        request_id="req-12345678-1234-1234-1234-123456789012",
        template_id="tpl-1",
        request_metadata={},
        cyclecloud_request_context=MagicMock(),
        provider_api=AzureProviderApi.VMSS,
        provider_api_key="VMSS",
        resource_group="test-rg",
        resource_ids=["vmss-1"],
    )

    result = await service.describe_resource_instances_async(
        read_context=read_context,
        resolve_handler=lambda *_args, **_kwargs: handler,
        vmss_cleanup_coordinator=MagicMock(reconcile=AsyncMock()),
        resource_manager=MagicMock(),
        deployment_service=None,
    )

    assert result.success is True
    assert "fleet_errors" not in result.metadata
    handler.get_vmss_resource_errors_async.assert_awaited_once_with("test-rg", "vmss-1")


@pytest.mark.asyncio
async def test_describe_resource_instances_async_warns_when_vmss_handler_lacks_error_reader(
    resource_metadata_service,
):
    logger = MagicMock()
    service = AzureInventoryQueryService(
        logger=logger,
        provider_instance_name="azure-default",
        resource_metadata_service=resource_metadata_service,
    )
    handler = MagicMock(spec=["check_hosts_status_async"])
    handler.check_hosts_status_async = AsyncMock(return_value=[])
    read_context = AzureReadOperationContext(
        operation_name="describe_resource_instances",
        request_id="req-12345678-1234-1234-1234-123456789012",
        template_id="tpl-1",
        request_metadata={},
        cyclecloud_request_context=MagicMock(),
        provider_api=AzureProviderApi.VMSS,
        provider_api_key="VMSS",
        resource_group="test-rg",
        resource_ids=["vmss-1"],
    )

    result = await service.describe_resource_instances_async(
        read_context=read_context,
        resolve_handler=lambda *_args, **_kwargs: handler,
        vmss_cleanup_coordinator=MagicMock(reconcile=AsyncMock()),
        resource_manager=MagicMock(),
        deployment_service=None,
    )

    assert result.success is True
    assert "fleet_errors" not in result.metadata
    logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_health_check_async_uses_async_credential_validation():
    config = MagicMock()
    config.region = "eastus2"
    service = AzureHealthCheckService(config=config, logger=MagicMock())
    azure_client = MagicMock()
    azure_client.validate_credentials_async = AsyncMock(return_value=True)

    result = await service.check_health_async(azure_client)

    assert result.is_healthy is True
    azure_client.validate_credentials_async.assert_awaited_once()


def test_health_check_sync_uses_client_credential_validation_bridge():
    config = MagicMock()
    config.region = "eastus2"
    service = AzureHealthCheckService(config=config, logger=MagicMock())
    azure_client = MagicMock()
    azure_client.validate_credentials_async = AsyncMock(return_value=True)

    result = service.check_health(azure_client)

    assert result.is_healthy is True
    azure_client.validate_credentials_async.assert_awaited_once()


@pytest.mark.asyncio
async def test_health_check_sync_bridge_raises_exception_group_from_thread():
    async def failing_validation():
        raise RuntimeError("credential boom")

    with pytest.raises(builtins.ExceptionGroup) as exc_info:
        AzureHealthCheckService._run_coro_sync(failing_validation())

    assert len(exc_info.value.exceptions) == 1
    assert isinstance(exc_info.value.exceptions[0], RuntimeError)
