"""Azure domain layer."""

from providers.azure.domain.template import (
    AzureAllocationStrategy,
    AzureEvictionPolicy,
    AzureOSDiskType,
    AzurePriority,
    AzureProviderApi,
    AzureSecurityType,
    AzureTemplate,
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

