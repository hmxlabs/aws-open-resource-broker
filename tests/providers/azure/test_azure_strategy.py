"""Tests for the Azure Provider Strategy.

Uses mock objects (no real Azure SDK) to test the full strategy lifecycle:
initialise, execute each operation type, health checks, capabilities, cleanup.
"""

import asyncio

import pytest
from unittest.mock import MagicMock

from providers.azure.configuration.config import AzureProviderConfig
from providers.azure.strategy.azure_provider_strategy import AzureProviderStrategy
from providers.base.strategy import (
    ProviderOperation,
    ProviderOperationType,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def azure_config():
    return AzureProviderConfig(
        subscription_id="12345678-1234-1234-1234-123456789012",
        resource_group="test-rg",
        region="eastus2",
    )


@pytest.fixture
def logger():
    return MagicMock()


@pytest.fixture
def strategy(azure_config, logger):
    s = AzureProviderStrategy(config=azure_config, logger=logger)
    s.initialize()
    return s


def _run(coro):
    """Helper to run a coroutine in a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------


class TestInitialization:
    def test_requires_azure_config(self, logger):
        with pytest.raises(ValueError, match="AzureProviderConfig"):
            AzureProviderStrategy(config={"region": "x"}, logger=logger)

    def test_not_initialized_returns_error(self, azure_config, logger):
        s = AzureProviderStrategy(config=azure_config, logger=logger)
        # Do NOT call s.initialize()
        op = ProviderOperation(
            operation_type=ProviderOperationType.HEALTH_CHECK,
            parameters={},
        )
        result = _run(s.execute_operation(op))
        assert not result.success
        assert result.error_code == "NOT_INITIALIZED"


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


class TestCapabilities:
    def test_supported_operations(self, strategy):
        caps = strategy.get_capabilities()
        assert caps.provider_type == "azure"
        assert ProviderOperationType.CREATE_INSTANCES in caps.supported_operations
        assert ProviderOperationType.TERMINATE_INSTANCES in caps.supported_operations
        assert ProviderOperationType.HEALTH_CHECK in caps.supported_operations

    def test_features(self, strategy):
        caps = strategy.get_capabilities()
        assert caps.features["spot_instances"] is True
        assert caps.features["supports_linux"] is True


class TestCapacityMetadata:
    def test_vmss_capacity_uses_provisioned_instance_count(self, strategy):
        strategy._resource_manager = MagicMock()
        strategy._resource_manager.get_vmss_capacity.return_value = {
            "capacity": 10,
            "provisioned_instance_count": 7,
            "provisioning_state": "Updating",
        }

        metadata = {}
        strategy._augment_vmss_capacity_metadata(metadata, ["vmss-demo"])

        assert metadata["fleet_capacity_fulfilment"] == {
            "target_capacity_units": 10,
            "fulfilled_capacity_units": 7,
            "provisioned_instance_count": 7,
            "state": "Updating",
        }

    def test_describe_resource_instances_surfaces_vmss_errors_without_instances(self, strategy):
        handler = MagicMock()
        handler.check_hosts_status.return_value = []
        handler.get_vmss_resource_errors.return_value = [
            {
                "error_code": "ProvisioningStateFailed",
                "error_message": "VMSS provisioning failed",
            }
        ]
        strategy._handlers["VMSS"] = handler
        strategy._resource_manager = MagicMock()
        strategy._resource_manager.get_vmss_capacity.return_value = {
            "capacity": 3,
            "provisioned_instance_count": 0,
            "provisioning_state": "Failed",
        }

        op = ProviderOperation(
            operation_type=ProviderOperationType.DESCRIBE_RESOURCE_INSTANCES,
            parameters={
                "resource_ids": ["vmss-demo"],
                "provider_api": "VMSS",
                "resource_group": "test-rg",
                "template_id": "tmpl-1",
            },
        )

        result = _run(strategy.execute_operation(op))

        assert result.success
        assert result.data["instances"] == []
        assert result.metadata["fleet_errors"][0]["error_code"] == "ProvisioningStateFailed"

    def test_build_provisioning_error_payload_uses_sdk_error_code(self, strategy):
        exc = Exception("fallback message")
        exc.error_code = "AllocationFailed"
        exc.status_code = 409

        payload = strategy._build_provisioning_error_payload(exc)

        assert payload["error_code"] == "AllocationFailed"
        assert payload["status_code"] == 409
        assert payload["raw_error_code"] == "AllocationFailed"

    def test_describe_resource_instances_adds_shortfall_summary(self, strategy):
        handler = MagicMock()
        handler.check_hosts_status.return_value = [
            {
                "instance_id": "vm-1",
                "status": "running",
                "private_ip": None,
                "public_ip": None,
                "launch_time": None,
                "instance_type": "Standard_D4s_v5",
                "subnet_id": None,
                "vpc_id": None,
                "provider_data": {
                    "fleet_errors": [
                        {
                            "error_code": "AllocationFailed",
                            "error_message": "No capacity in selected zone",
                        }
                    ]
                },
            }
        ]
        strategy._handlers["VMSS"] = handler
        strategy._resource_manager = MagicMock()
        strategy._resource_manager.get_vmss_capacity.return_value = {
            "capacity": 3,
            "provisioned_instance_count": 1,
            "provisioning_state": "Updating",
        }

        op = ProviderOperation(
            operation_type=ProviderOperationType.DESCRIBE_RESOURCE_INSTANCES,
            parameters={
                "resource_ids": ["vmss-demo"],
                "provider_api": "VMSS",
                "resource_group": "test-rg",
                "template_id": "tmpl-1",
            },
        )

        result = _run(strategy.execute_operation(op))

        assert result.success
        assert result.metadata["capacity_shortfall"]["missing_capacity_units"] == 2
        assert result.metadata["capacity_shortfall"]["likely_causes"] == ["AllocationFailed"]


# ---------------------------------------------------------------------------
# VALIDATE_TEMPLATE
# ---------------------------------------------------------------------------


class TestValidateTemplate:
    def test_valid_template(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.VALIDATE_TEMPLATE,
            parameters={
                "template_config": {
                    "template_id": "t1",
                    "vm_size": "Standard_D4s_v5",
                    "resource_group": "rg",
                    "location": "eastus2",
                    "image": {
                        "publisher": "Canonical",
                        "offer": "0001-com-ubuntu-server-jammy",
                        "sku": "22_04-lts-gen2",
                        "version": "latest",
                    },
                },
            },
        )
        result = _run(strategy.execute_operation(op))
        assert result.success
        assert result.data["valid"] is True
        assert result.data["errors"] == []

    def test_invalid_template_missing_fields(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.VALIDATE_TEMPLATE,
            parameters={
                "template_config": {"template_id": "bad"},
            },
        )
        result = _run(strategy.execute_operation(op))
        assert result.success  # validation itself doesn't fail the operation
        assert result.data["valid"] is False
        assert len(result.data["errors"]) > 0

    def test_missing_template_config(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.VALIDATE_TEMPLATE,
            parameters={},
        )
        result = _run(strategy.execute_operation(op))
        assert not result.success
        assert result.error_code == "MISSING_TEMPLATE_CONFIG"


# ---------------------------------------------------------------------------
# GET_AVAILABLE_TEMPLATES
# ---------------------------------------------------------------------------


class TestGetAvailableTemplates:
    def test_returns_fallback_templates(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.GET_AVAILABLE_TEMPLATES,
            parameters={},
        )
        result = _run(strategy.execute_operation(op))
        assert result.success
        assert isinstance(result.data["templates"], list)
        assert result.data["count"] >= 1


# ---------------------------------------------------------------------------
# UNSUPPORTED_OPERATION
# ---------------------------------------------------------------------------


class TestUnsupportedOperation:
    def test_unsupported_operation(self, strategy):
        op = ProviderOperation(
            operation_type="totally_unknown",
            parameters={},
        )
        result = _run(strategy.execute_operation(op))
        assert not result.success
        assert result.error_code == "UNSUPPORTED_OPERATION"


# ---------------------------------------------------------------------------
# CREATE_INSTANCES (with missing config → error path)
# ---------------------------------------------------------------------------


class TestCreateInstances:
    def test_missing_template_config_returns_error(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.CREATE_INSTANCES,
            parameters={},
        )
        result = _run(strategy.execute_operation(op))
        assert not result.success
        assert result.error_code == "MISSING_TEMPLATE_CONFIG"

    def test_dry_run_short_circuits_before_handler(self, azure_config, logger):
        strategy = AzureProviderStrategy(config=azure_config, logger=logger)
        strategy.initialize()

        handler = MagicMock()
        strategy._handlers = {"VMSS": handler}

        op = ProviderOperation(
            operation_type=ProviderOperationType.CREATE_INSTANCES,
            parameters={
                "template_config": {
                    "template_id": "azure-vmss-test",
                    "provider_api": "VMSS",
                    "vm_size": "Standard_D4s_v5",
                    "resource_group": "test-rg",
                    "location": "eastus2",
                    "ssh_public_keys": [
                        "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC7 test@host"
                    ],
                    "image": {
                        "publisher": "Canonical",
                        "offer": "0001-com-ubuntu-server-jammy",
                        "sku": "22_04-lts-gen2",
                        "version": "latest",
                    },
                },
                "count": 2,
            },
            context={"dry_run": True},
        )

        result = _run(strategy.execute_operation(op))

        assert result.success
        assert result.data["resource_ids"] == ["dry-run-resource-id"]
        assert result.data["count"] == 2
        assert result.metadata["method"] == "dry_run"
        assert result.metadata["provider_data"] == {"dry_run": True}
        handler.acquire_hosts.assert_not_called()


# ---------------------------------------------------------------------------
# TERMINATE_INSTANCES (with missing ids → error path)
# ---------------------------------------------------------------------------


class TestTerminateInstances:
    def test_missing_instance_ids_returns_error(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.TERMINATE_INSTANCES,
            parameters={},
        )
        result = _run(strategy.execute_operation(op))
        assert not result.success
        assert result.error_code == "MISSING_INSTANCE_IDS"

    def test_fallback_handler_uses_grouped_resource_ids(self, azure_config, logger):
        strategy = AzureProviderStrategy(config=azure_config, logger=logger)
        strategy.initialize()

        handler = MagicMock()
        strategy._handlers = {"VMSS": handler}

        op = ProviderOperation(
            operation_type=ProviderOperationType.TERMINATE_INSTANCES,
            parameters={
                "instance_ids": ["orb-1"],
                "provider_api": "VMSS",
                "resource_mapping": {
                    "orb-1": ("vmss-prod-b", 1),
                },
            },
        )

        result = _run(strategy.execute_operation(op))

        assert result.success
        handler.release_hosts.assert_called_once_with(
            machine_ids=["orb-1"],
            resource_id="vmss-prod-b",
            context={"resource_group": "test-rg", "resource_id": "vmss-prod-b"},
        )

    def test_dry_run_short_circuits_before_release(self, azure_config, logger):
        strategy = AzureProviderStrategy(config=azure_config, logger=logger)
        strategy.initialize()

        handler = MagicMock()
        strategy._handlers = {"VMSS": handler}

        op = ProviderOperation(
            operation_type=ProviderOperationType.TERMINATE_INSTANCES,
            parameters={
                "instance_ids": ["orb-1", "orb-2"],
                "provider_api": "VMSS",
            },
            context={"dry_run": True},
        )

        result = _run(strategy.execute_operation(op))

        assert result.success
        assert result.data["terminated_count"] == 2
        assert result.metadata["method"] == "dry_run"
        handler.release_hosts.assert_not_called()


# ---------------------------------------------------------------------------
# GET_INSTANCE_STATUS (with missing ids → error path)
# ---------------------------------------------------------------------------


class TestGetInstanceStatus:
    def test_missing_instance_ids_returns_error(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.GET_INSTANCE_STATUS,
            parameters={},
        )
        result = _run(strategy.execute_operation(op))
        assert not result.success
        assert result.error_code == "MISSING_INSTANCE_IDS"

    def test_dry_run_short_circuits_status_lookup(self, azure_config, logger):
        strategy = AzureProviderStrategy(config=azure_config, logger=logger)
        strategy.initialize()

        op = ProviderOperation(
            operation_type=ProviderOperationType.GET_INSTANCE_STATUS,
            parameters={"instance_ids": ["vm-1", "vm-2"]},
            context={"dry_run": True},
        )

        result = _run(strategy.execute_operation(op))

        assert result.success
        assert result.data["queried_count"] == 2
        assert [m["instance_id"] for m in result.data["machines"]] == ["vm-1", "vm-2"]
        assert result.metadata["method"] == "dry_run"


# ---------------------------------------------------------------------------
# DESCRIBE_RESOURCE_INSTANCES (with missing resource_ids → error path)
# ---------------------------------------------------------------------------


class TestDescribeResourceInstances:
    def test_missing_resource_ids_returns_error(self, strategy):
        op = ProviderOperation(
            operation_type=ProviderOperationType.DESCRIBE_RESOURCE_INSTANCES,
            parameters={},
        )
        result = _run(strategy.execute_operation(op))
        assert not result.success
        assert result.error_code == "MISSING_RESOURCE_IDS"

    def test_dry_run_short_circuits_resource_discovery(self, azure_config, logger):
        strategy = AzureProviderStrategy(config=azure_config, logger=logger)
        strategy.initialize()

        handler = MagicMock()
        strategy._handlers = {"VMSS": handler}

        op = ProviderOperation(
            operation_type=ProviderOperationType.DESCRIBE_RESOURCE_INSTANCES,
            parameters={
                "resource_ids": ["vmss-test"],
                "provider_api": "VMSS",
            },
            context={"dry_run": True},
        )

        result = _run(strategy.execute_operation(op))

        assert result.success
        assert result.data["instances"] == []
        assert result.metadata["method"] == "dry_run"
        handler.check_hosts_status.assert_not_called()


# ---------------------------------------------------------------------------
# Provider naming
# ---------------------------------------------------------------------------


class TestProviderNaming:
    def test_generate_provider_name(self, strategy):
        name = strategy.generate_provider_name({
            "subscription_id": "12345678-abcd",
            "region": "westeurope",
        })
        assert name.startswith("azure_")
        assert "westeurope" in name

    def test_parse_provider_name(self, strategy):
        parsed = strategy.parse_provider_name("azure_12345678_westeurope")
        assert parsed["type"] == "azure"
        assert parsed["subscription_id"] == "12345678"
        assert parsed["region"] == "westeurope"

    def test_get_provider_name_pattern(self, strategy):
        pattern = strategy.get_provider_name_pattern()
        assert "{type}" in pattern
        assert "{region}" in pattern


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    def test_cleanup_resets_state(self, strategy):
        strategy.cleanup()
        assert strategy._initialized is False
        assert strategy._handlers == {}
        assert strategy._client is None
