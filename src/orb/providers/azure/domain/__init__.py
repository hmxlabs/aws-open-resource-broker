"""Azure domain layer."""

from orb.providers.azure.domain.template import (
    AzureAllocationStrategy,
    AzureCapacityReservationGroupId,
    AzureDiskEncryptionSetId,
    AzureEvictionPolicy,
    AzureLocationName,
    AzureOSDiskType,
    AzurePriority,
    AzureProximityPlacementGroupId,
    AzureProviderApi,
    AzureResourceGroupName,
    AzureSecurityType,
    AzureTemplate,
    AzureUpgradePolicyMode,
    AzureVMSSOrchestrationMode,
)

__all__: list[str] = [
    "AzureAllocationStrategy",
    "AzureCapacityReservationGroupId",
    "AzureDiskEncryptionSetId",
    "AzureEvictionPolicy",
    "AzureLocationName",
    "AzureOSDiskType",
    "AzurePriority",
    "AzureProximityPlacementGroupId",
    "AzureProviderApi",
    "AzureResourceGroupName",
    "AzureSecurityType",
    "AzureTemplate",
    "AzureUpgradePolicyMode",
    "AzureVMSSOrchestrationMode",
]
