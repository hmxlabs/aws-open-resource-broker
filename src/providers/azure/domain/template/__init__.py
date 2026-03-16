"""Azure template domain - VMSS-based template configuration."""

from providers.azure.domain.template.azure_template_aggregate import AzureTemplate
from providers.azure.domain.template.value_objects import (
    AzureAllocationStrategy,
    AzureEvictionPolicy,
    AzureOSDiskType,
    AzurePriority,
    AzureProviderApi,
    AzureSecurityType,
    AzureVMSSOrchestrationMode,
)

__all__: list[str] = [
    "AzureAllocationStrategy",
    "AzureEvictionPolicy",
    "AzureOSDiskType",
    "AzurePriority",
    "AzureProviderApi",
    "AzureSecurityType",
    "AzureTemplate",
    "AzureVMSSOrchestrationMode",
]

