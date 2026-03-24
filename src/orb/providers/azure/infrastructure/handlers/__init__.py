"""Azure infrastructure handlers."""

from orb.providers.azure.infrastructure.handlers.azure_handler import AzureHandler
from orb.providers.azure.infrastructure.handlers.single_vm_handler import SingleVMHandler
from orb.providers.azure.infrastructure.handlers.vmss_handler import VMSSHandler

__all__: list[str] = [
    "AzureHandler",
    "SingleVMHandler",
    "VMSSHandler",
]

