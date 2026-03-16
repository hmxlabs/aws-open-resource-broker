"""Azure infrastructure adapters."""

from providers.azure.infrastructure.adapters.machine_adapter import AzureMachineAdapter
from providers.azure.infrastructure.adapters.template_adapter import AzureTemplateAdapter

__all__: list[str] = [
    "AzureMachineAdapter",
    "AzureTemplateAdapter",
]

