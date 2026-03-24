"""Azure infrastructure adapters."""

from orb.providers.azure.infrastructure.adapters.machine_adapter import AzureMachineAdapter
from orb.providers.azure.infrastructure.adapters.template_adapter import AzureTemplateAdapter

__all__: list[str] = [
    "AzureMachineAdapter",
    "AzureTemplateAdapter",
]

