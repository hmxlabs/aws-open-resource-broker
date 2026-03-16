"""Azure Handler Factory.

Creates and caches Azure handlers based on ``provider_api`` values
"""

from typing import Optional

from domain.base.dependency_injection import injectable
from domain.base.ports import LoggingPort
from domain.template.template_aggregate import Template
from providers.azure.domain.template.value_objects import AzureProviderApi
from providers.azure.exceptions.azure_exceptions import AzureValidationError
from providers.azure.infrastructure.azure_client import AzureClient
from providers.azure.infrastructure.handlers.azure_handler import AzureHandler


@injectable
class AzureHandlerFactory:
    """Factory for creating Azure handlers keyed by ``AzureProviderApi``."""

    def __init__(
        self,
        azure_client: AzureClient,
        logger: LoggingPort,
        machine_adapter: Optional[object] = None,
    ) -> None:
        self._azure_client = azure_client
        self._logger = logger
        self._machine_adapter = machine_adapter
        self._handlers: dict[str, AzureHandler] = {}
        self._handler_classes: dict[str, type[AzureHandler]] = {}
        self._register_handler_classes()

    @property
    def azure_client(self) -> AzureClient:
        return self._azure_client

    def create_handler(self, handler_type: str) -> AzureHandler:
        """Create (or return cached) handler for *handler_type*.

        Raises:
            AzureValidationError: If *handler_type* is unknown.
        """
        if handler_type in self._handlers:
            return self._handlers[handler_type]

        # Validate
        try:
            AzureProviderApi(handler_type)
        except ValueError:
            raise AzureValidationError(f"Invalid Azure handler type: {handler_type}")

        if handler_type not in self._handler_classes:
            raise AzureValidationError(
                f"No handler class registered for type: {handler_type}"
            )

        handler_class = self._handler_classes[handler_type]
        handler = handler_class(
            azure_client=self._azure_client,
            logger=self._logger,
            machine_adapter=self._machine_adapter,
        )
        self._handlers[handler_type] = handler
        self._logger.debug("Created Azure handler for type: %s", handler_type)
        return handler

    def create_handler_for_template(self, template: Template) -> AzureHandler:
        """Create handler appropriate for *template.provider_api*."""
        handler_type = template.provider_api or AzureProviderApi.VMSS.value
        return self.create_handler(handler_type)

    def _register_handler_classes(self) -> None:
        from providers.azure.infrastructure.handlers.cyclecloud_handler import (
            CycleCloudHandler,
        )
        from providers.azure.infrastructure.handlers.single_vm_handler import (
            SingleVMHandler,
        )
        from providers.azure.infrastructure.handlers.vmss_handler import VMSSHandler

        self._handler_classes = {
            AzureProviderApi.VMSS.value: VMSSHandler,
            AzureProviderApi.VMSS_UNIFORM.value: VMSSHandler,
            AzureProviderApi.SINGLE_VM.value: SingleVMHandler,
            AzureProviderApi.CYCLECLOUD.value: CycleCloudHandler,
        }
        self._logger.debug(
            "Registered Azure handler classes: %s",
            list(self._handler_classes.keys()),
        )

    def generate_example_templates(self) -> list[dict]:
        """Collect example templates from all registered handlers."""
        examples: list[dict] = []
        for handler_type, handler_class in self._handler_classes.items():
            if hasattr(handler_class, "get_example_templates"):
                try:
                    examples.extend(handler_class.get_example_templates())
                except Exception as exc:
                    self._logger.warning(
                        "Failed to get example templates from %s: %s",
                        handler_type,
                        exc,
                    )
        return examples

