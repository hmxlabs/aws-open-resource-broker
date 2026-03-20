"""Azure handler base class.

All Azure infrastructure handlers extend this ABC, providing a common constructor
contract and the three core operations
(acquire, status, release) that the provisioning adapter and strategy call.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional

from domain.base.dependency_injection import injectable
from domain.base.ports import LoggingPort
from domain.request.aggregate import Request
from providers.azure.domain.template.azure_template_aggregate import AzureTemplate
from providers.azure.infrastructure.azure_client import AzureClient


@injectable
class AzureHandler(ABC):
    """Abstract base handler for Azure provisioning operations.

    Concrete implementations (``VMSSHandler``, ``SingleVMHandler``)
    implement the three abstract methods for their specific Azure API surface.
    """

    def __init__(
        self,
        azure_client: AzureClient,
        logger: LoggingPort,
        machine_adapter: Optional[Any] = None,
    ) -> None:
        self.azure_client = azure_client
        self._logger = logger
        self._machine_adapter = machine_adapter

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    @abstractmethod
    def acquire_hosts(
        self, request: Request, template: AzureTemplate
    ) -> dict[str, Any]:
        """Provision resources.

        Returns:
            dict with keys:
                success (bool), resource_ids (list[str]),
                instances (list[dict]), error_message (str|None),
                provider_data (dict)
        """

    @abstractmethod
    def check_hosts_status(self, request: Request) -> list[dict[str, Any]]:
        """Return list of instance detail dicts for ``request.resource_ids``.

        Each dict must include at minimum:
            instance_id, status, private_ip, public_ip,
            launch_time, instance_type, subnet_id, vpc_id
        """

    @abstractmethod
    def release_hosts(
        self,
        machine_ids: list[str],
        resource_id: str,
        context: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Delete / deallocate cloud resources and optionally return provider metadata."""

    # ------------------------------------------------------------------
    # Optional helpers
    # ------------------------------------------------------------------

    @classmethod
    def get_example_templates(cls) -> list[dict[str, Any]]:
        """Return example template dicts for documentation / wizard use."""
        return []
