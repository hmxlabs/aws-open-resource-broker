"""Azure create-instance orchestration helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, cast

from orb.providers.azure.domain.template.azure_template_aggregate import AzureTemplate
from orb.providers.azure.domain.template.value_objects import AzureProviderApi
from orb.providers.azure.infrastructure.handlers.azure_handler import AzureHandler
from orb.providers.base.strategy import ProviderOperation, ProviderResult


AzureProviderApiRef = AzureProviderApi | str


@dataclass
class CreateOperationContext:
    """Context object encapsulating all necessary information for handling a create operation."""
    template_config: dict[str, Any]
    count: int
    provider_api: AzureProviderApiRef
    provider_api_key: str
    handler: AzureHandler
    azure_template: AzureTemplate


class AzureProvisioningService:
    """Own Azure create-operation preparation and handler result shaping."""

    @staticmethod
    def get_create_template_config(operation: ProviderOperation) -> dict[str, Any]:
        """Extract the template configuration from the provider operation.

        Args:
            operation (ProviderOperation): The provider operation containing parameters.
        Returns:
            dict[str, Any]: The template configuration dictionary (may be empty).
        """
        return dict(operation.parameters.get("template_config") or {})

    @staticmethod
    def get_create_count(operation: ProviderOperation) -> int:
        """Extract the instance count from the provider operation.

        Args:
            operation (ProviderOperation): The provider operation containing parameters.
        Returns:
            int: The number of instances to create (default 1).
        """
        return operation.parameters.get("count", 1)

    @staticmethod
    def validate_create_template_config(
        template_config: dict[str, Any],
    ) -> Optional[ProviderResult]:
        """Validate that the template configuration is present.

        Args:
            template_config (dict[str, Any]): The template configuration to validate.
        Returns:
            Optional[ProviderResult]: None if valid, or an error result if missing.
        """
        if template_config:
            return None
        return ProviderResult.error_result(
            "Template configuration is required for instance creation",
            "MISSING_TEMPLATE_CONFIG",
        )

    @staticmethod
    def provider_api_key(provider_api: AzureProviderApiRef) -> str:
        """Get the string key for the provider API value.

        Args:
            provider_api (AzureProviderApiRef): The provider API enum or string.
        Returns:
            str: The string key for the provider API.
        """
        if isinstance(provider_api, AzureProviderApi):
            return provider_api.value
        return provider_api

    @staticmethod
    def resolve_create_provider_api(
        template_config: dict[str, Any],
        normalize_provider_api: Callable[[Any], Any],
    ) -> AzureProviderApiRef:
        """Resolve the provider API from the template config, normalizing as needed.

        Args:
            template_config (dict[str, Any]): The template configuration.
            normalize_provider_api (Callable): Function to normalize the API value.
        Returns:
            AzureProviderApiRef: The resolved provider API value.
        """
        provider_api = template_config.get("provider_api", AzureProviderApi.VMSS)
        return cast(AzureProviderApiRef, normalize_provider_api(provider_api))

    def build_create_operation_context(
        self,
        *,
        operation: ProviderOperation,
        normalize_provider_api: Callable[[Any], Any],
        resolve_handler: Callable[[AzureProviderApiRef], Optional[AzureHandler]],
        build_template: Callable[[dict[str, Any]], AzureTemplate],
    ) -> CreateOperationContext | ProviderResult:
        """Build and validate the context required for a create operation.

        Args:
            operation (ProviderOperation): The provider operation.
            normalize_provider_api (Callable): Function to normalize the API value.
            resolve_handler (Callable): Function to resolve the handler for the API.
            build_template (Callable): Function to build the AzureTemplate.
        Returns:
            CreateOperationContext | ProviderResult: The context or an error result.
        """
        template_config = self.get_create_template_config(operation)
        count = self.get_create_count(operation)
        validation_error = self.validate_create_template_config(template_config)
        if validation_error:
            return validation_error

        provider_api = self.resolve_create_provider_api(template_config, normalize_provider_api)
        provider_api_key = self.provider_api_key(provider_api)
        handler = resolve_handler(provider_api)
        if handler is None:
            return ProviderResult.error_result(
                f"No handler available for provider_api: {provider_api_key}",
                "HANDLER_NOT_FOUND",
            )

        return CreateOperationContext(
            template_config=template_config,
            count=count,
            provider_api=provider_api,
            provider_api_key=provider_api_key,
            handler=handler,
            azure_template=build_template(template_config),
        )

    def build_create_request(
        self,
        *,
        operation: ProviderOperation,
        azure_template: AzureTemplate,
        count: int,
        provider_api: AzureProviderApiRef,
        provider_instance_name: str,
    ) -> Any:
        """Build a request object for the create operation handler.

        Args:
            operation (ProviderOperation): The provider operation.
            azure_template (AzureTemplate): The Azure template object.
            count (int): Number of instances to create.
            provider_api (AzureProviderApiRef): The provider API value.
            provider_instance_name (str): The provider instance name.
        Returns:
            Any: The constructed request object.
        """
        from orb.domain.request.aggregate import Request
        from orb.domain.request.value_objects import RequestType

        request_metadata = dict(operation.parameters.get("request_metadata", {}) or {})
        request_id = operation.parameters.get("request_id") or (
            operation.context.get("request_id") if operation.context else None
        )
        request = Request.create_new_request(
            request_type=RequestType.ACQUIRE,
            template_id=azure_template.template_id,
            machine_count=count,
            provider_type="azure",
            provider_name=provider_instance_name,
            metadata=request_metadata,
            request_id=request_id,
        )
        request.provider_api = self.provider_api_key(provider_api)
        return request

    def normalize_handler_create_result(
        self,
        handler_result: Any,
        *,
        template_config: dict[str, Any],
        provider_api: AzureProviderApiRef,
        count: int,
        template_id: str,
    ) -> ProviderResult:
        """Normalize the result from the handler into a ProviderResult.

        Args:
            handler_result (Any): The result from the handler.
            template_config (dict[str, Any]): The template configuration.
            provider_api (AzureProviderApiRef): The provider API value.
            count (int): Number of instances requested.
            template_id (str): The template ID.
        Returns:
            ProviderResult: The normalized result object.
        """
        if isinstance(handler_result, dict):
            resource_ids = handler_result.get("resource_ids", [])
            instances = handler_result.get("instances", [])
            success = handler_result.get("success", False)
            error_message = handler_result.get("error_message")
            provider_data = handler_result.get("provider_data") or {}

            if not success:
                return ProviderResult.error_result(
                    f"Provisioning failed: {error_message}",
                    "PROVISIONING_ADAPTER_ERROR",
                    {
                        "operation": "create_instances",
                        "template_config": template_config,
                        "handler_used": self.provider_api_key(provider_api),
                        "method": "handler",
                        "provider_data": provider_data,
                    },
                )
        else:
            resource_ids = [handler_result] if handler_result else []
            instances = []
            provider_data = {}

        return ProviderResult.success_result(
            {
                "resource_ids": resource_ids,
                "instances": instances,
                "provider_api": self.provider_api_key(provider_api),
                "count": count,
                "template_id": template_id,
            },
            {
                "operation": "create_instances",
                "template_config": template_config,
                "handler_used": self.provider_api_key(provider_api),
                "method": "handler",
                "provider_data": provider_data,
            },
        )

    @staticmethod
    def create_instances_dry_run_result(
        create_context: CreateOperationContext,
    ) -> ProviderResult:
        """Return a dry-run result for create instances operation.

        Args:
            create_context (CreateOperationContext): The context for the create operation.
        Returns:
            ProviderResult: The dry-run result object.
        """
        return ProviderResult.success_result(
            {
                "resource_ids": ["dry-run-resource-id"],
                "instances": [],
                "provider_api": create_context.provider_api_key,
                "count": create_context.count,
                "template_id": create_context.azure_template.template_id,
            },
            {
                "operation": "create_instances",
                "template_config": create_context.template_config,
                "handler_used": create_context.provider_api_key,
                "method": "dry_run",
                "provider_data": {"dry_run": True},
            },
        )

    def execute_create_handler(
        self,
        *,
        create_context: CreateOperationContext,
        request: Any,
    ) -> ProviderResult:
        """Execute the handler's acquire_hosts method and normalize the result.

        Args:
            create_context (CreateOperationContext): The context for the create operation.
            request (Any): The request object for the handler.
        Returns:
            ProviderResult: The normalized result object.
        """
        handler_result = create_context.handler.acquire_hosts(
            request, create_context.azure_template
        )
        return self.normalize_handler_create_result(
            handler_result,
            template_config=create_context.template_config,
            provider_api=create_context.provider_api,
            count=create_context.count,
            template_id=create_context.azure_template.template_id,
        )
