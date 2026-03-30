"""Shared Azure strategy test fixtures."""

from unittest.mock import MagicMock

import pytest

from orb.providers.azure.configuration.config import AzureProviderConfig
from orb.providers.azure.strategy.azure_provider_strategy import AzureProviderStrategy


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
    provider_strategy = AzureProviderStrategy(
        config=azure_config,
        logger=logger,
        provider_instance_name="azure-default",
    )
    provider_strategy.initialize()
    return provider_strategy
