"""SimpleRegistry — a lightweight, fail-fast key→value registry.

Used by the satellite provider registries (CLISpecRegistry,
FieldMappingRegistry, DefaultsLoaderRegistry, TemplateExtensionRegistry,
TemplateExampleGeneratorRegistry, ProviderSettingsRegistry) so that a missing
entry fails loudly with a clear message instead of silently returning None.

For callers that intentionally need an absent-is-OK lookup, use
``get_or_none``.  For callers that expect the value to be present (the
majority), use ``get``; it raises ``RegistryLookupError`` naming the key and
listing every registered key so the gap is immediately obvious.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from orb.domain.base.exceptions import ConfigurationError

T = TypeVar("T")


class RegistryLookupError(ConfigurationError):
    """Raised when a key is not found in a SimpleRegistry.

    Carries the requested key and the list of registered keys so the caller
    gets a complete diagnosis without having to inspect the registry manually.
    """

    def __init__(self, registry_name: str, key: str, registered_keys: list[str]) -> None:
        available = ", ".join(sorted(registered_keys)) if registered_keys else "<none>"
        message = (
            f"{registry_name}: no entry registered for key {key!r}. Registered keys: [{available}]"
        )
        super().__init__(message)
        self.registry_name = registry_name
        self.key = key
        self.registered_keys = list(registered_keys)


class SimpleRegistry(Generic[T]):
    """Lightweight class-variable–style registry with fail-fast ``get``.

    Designed to be used as a mixin base (via composition or direct use) for the
    satellite provider registries.  Subclasses hold a ``_registry_name`` class
    attribute that appears in error messages::

        class CLISpecRegistry(SimpleRegistry[ProviderCLISpecPort]):
            _registry_name = "CLISpecRegistry"
            _store: dict[str, ProviderCLISpecPort] = {}

    Usage::

        # Fail-fast (raises RegistryLookupError on miss):
        spec = CLISpecRegistry.get("aws")

        # Explicit optional (returns None on miss):
        spec = CLISpecRegistry.get_or_none("aws")

        # Register:
        CLISpecRegistry.register("aws", AWSCLISpec())
    """

    #: Override in each concrete registry for error-message clarity.
    _registry_name: str = "SimpleRegistry"
    #: Each concrete subclass declares its own ``_store`` class variable.
    _store: dict[str, T] = {}  # type: ignore[assignment]

    @classmethod
    def register(cls, key: str, value: T) -> None:
        """Register *value* under *key*.  Overwrites any existing entry."""
        cls._store[key] = value

    @classmethod
    def get(cls, key: str) -> T:
        """Return the value for *key*.

        Raises:
            RegistryLookupError: when *key* is not registered.
        """
        try:
            return cls._store[key]
        except KeyError:
            raise RegistryLookupError(cls._registry_name, key, list(cls._store))

    @classmethod
    def get_or_none(cls, key: str) -> T | None:
        """Return the value for *key*, or ``None`` if not registered.

        Use this only when the absence of a registration is a legitimate
        "not applicable" case rather than a bug.
        """
        return cls._store.get(key)

    @classmethod
    def all(cls) -> dict[str, T]:
        """Return a snapshot copy of all registered entries."""
        return dict(cls._store)

    @classmethod
    def registered_keys(cls) -> list[str]:
        """Return all registered keys."""
        return list(cls._store)

    @classmethod
    def clear(cls) -> None:
        """Remove all entries (for use in tests)."""
        cls._store.clear()
