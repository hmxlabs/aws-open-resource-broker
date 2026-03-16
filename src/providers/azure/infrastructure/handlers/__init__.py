"""Azure infrastructure handlers."""

from providers.azure.infrastructure.handlers.azure_handler import AzureHandler
from providers.azure.infrastructure.handlers.single_vm_handler import SingleVMHandler
from providers.azure.infrastructure.handlers.vmss_handler import VMSSHandler

__all__: list[str] = [
    "AzureHandler",
    "SingleVMHandler",
    "VMSSHandler",
]

