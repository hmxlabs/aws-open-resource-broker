"""Azure provider configuration."""

from providers.azure.configuration.config import AzureProviderConfig
from providers.azure.configuration.template_extension import AzureTemplateExtensionConfig
from providers.azure.configuration.validator import validate_azure_config, validate_azure_template

__all__: list[str] = [
    "AzureProviderConfig",
    "AzureTemplateExtensionConfig",
    "validate_azure_config",
    "validate_azure_template",
]

