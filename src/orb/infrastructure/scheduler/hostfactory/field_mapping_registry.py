"""Registry mapping provider types to FieldMappingPort instances."""

from orb.infrastructure.registry.simple_registry import SimpleRegistry
from orb.infrastructure.scheduler.hostfactory.field_mapping_port import FieldMappingPort


class FieldMappingRegistry(SimpleRegistry[FieldMappingPort]):
    """Registry mapping provider type strings to FieldMappingPort implementations.

    Use ``get_or_none`` when the absence of a field-mapping adapter is
    acceptable (the host-factory code has explicit None-guard fallbacks for
    providers that do not supply cpu/ram derivation yet).  Use ``get`` when
    the adapter must exist.

    Follows the same lightweight pattern as :class:`CLISpecRegistry`.

    Usage::

        # During provider bootstrap:
        FieldMappingRegistry.register("aws", AWSFieldMapping())

        # At call site (intentionally optional — adapter may not exist):
        adapter = FieldMappingRegistry.get_or_none("aws")
        if adapter is not None:
            mapped = adapter.apply_defaults(mapped)
    """

    _registry_name = "FieldMappingRegistry"
    _store: dict[str, FieldMappingPort] = {}

    @classmethod
    def registered_providers(cls) -> list[str]:
        """Return all registered provider type strings."""
        return cls.registered_keys()
