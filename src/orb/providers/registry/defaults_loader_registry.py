"""Registry mapping provider types to ProviderDefaultsLoaderPort instances."""

from __future__ import annotations

from orb.domain.base.ports.provider_defaults_loader_port import ProviderDefaultsLoaderPort
from orb.infrastructure.registry.simple_registry import SimpleRegistry


class DefaultsLoaderRegistry(SimpleRegistry[ProviderDefaultsLoaderPort]):
    """Registry mapping provider type strings to ProviderDefaultsLoaderPort implementations.

    Use ``get_or_none`` when the absence of a defaults loader is acceptable
    (e.g. checking before registration to avoid duplicate registration).  Use
    ``get`` when the loader must exist.

    Follows the same lightweight pattern as :class:`CLISpecRegistry` and
    :class:`FieldMappingRegistry`.

    Usage::

        # During provider bootstrap:
        DefaultsLoaderRegistry.register("aws", AWSDefaultsLoader())

        # At call site:
        for provider_type, loader in DefaultsLoaderRegistry.all().items():
            defaults = loader.load_defaults()
    """

    _registry_name = "DefaultsLoaderRegistry"
    _store: dict[str, ProviderDefaultsLoaderPort] = {}

    @classmethod
    def registered_providers(cls) -> list[str]:
        """Return all registered provider type strings."""
        return cls.registered_keys()
