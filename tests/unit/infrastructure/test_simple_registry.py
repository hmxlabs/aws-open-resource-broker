"""Unit tests for SimpleRegistry[T] and RegistryLookupError.

Covers:
- register / get round-trip
- get() on miss raises RegistryLookupError naming the key and listing available keys
- get_or_none() returns None on miss
- register overwrites an existing entry
- all() / registered_keys() snapshots
- clear() wipes the store
"""

from __future__ import annotations

import pytest

from orb.infrastructure.registry.simple_registry import RegistryLookupError, SimpleRegistry

# ---------------------------------------------------------------------------
# Concrete registry fixture (isolated store per test via subclass + clear)
# ---------------------------------------------------------------------------


class _TestRegistry(SimpleRegistry[str]):
    """Concrete single-type registry used only in tests."""

    _registry_name = "TestRegistry"
    _store: dict[str, str] = {}


@pytest.fixture(autouse=True)
def _clear_registry():
    """Wipe the registry store before and after every test."""
    _TestRegistry.clear()
    yield
    _TestRegistry.clear()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSimpleRegistry:
    def test_register_and_get_round_trip(self):
        """register() followed by get() returns the stored value."""
        _TestRegistry.register("alpha", "value-alpha")

        result = _TestRegistry.get("alpha")

        assert result == "value-alpha"

    def test_get_on_miss_raises_registry_lookup_error(self):
        """get() with an unknown key raises RegistryLookupError."""
        _TestRegistry.register("existing", "v1")

        with pytest.raises(RegistryLookupError) as exc_info:
            _TestRegistry.get("missing")

        err = exc_info.value
        assert "missing" in str(err), "Error message must name the missing key"
        assert "existing" in str(err), "Error message must list available keys"

    def test_registry_lookup_error_attributes(self):
        """RegistryLookupError carries structured key + registered_keys."""
        _TestRegistry.register("k1", "v1")
        _TestRegistry.register("k2", "v2")

        with pytest.raises(RegistryLookupError) as exc_info:
            _TestRegistry.get("nope")

        err = exc_info.value
        assert err.key == "nope"
        assert err.registry_name == "TestRegistry"
        assert set(err.registered_keys) == {"k1", "k2"}

    def test_get_or_none_returns_none_on_miss(self):
        """get_or_none() returns None when the key is absent."""
        result = _TestRegistry.get_or_none("absent")

        assert result is None

    def test_get_or_none_returns_value_on_hit(self):
        """get_or_none() returns the stored value when the key exists."""
        _TestRegistry.register("present", "found")

        result = _TestRegistry.get_or_none("present")

        assert result == "found"

    def test_register_overwrites_existing_entry(self):
        """register() silently replaces a previous entry for the same key."""
        _TestRegistry.register("key", "original")
        _TestRegistry.register("key", "updated")

        assert _TestRegistry.get("key") == "updated"

    def test_all_returns_snapshot_copy(self):
        """all() returns a dict snapshot; mutating it does not affect the registry."""
        _TestRegistry.register("a", "1")
        _TestRegistry.register("b", "2")

        snapshot = _TestRegistry.all()

        assert snapshot == {"a": "1", "b": "2"}
        # Mutating the snapshot must not affect the registry
        snapshot["c"] = "3"
        assert _TestRegistry.get_or_none("c") is None

    def test_registered_keys_lists_all_keys(self):
        """registered_keys() enumerates every registered key."""
        _TestRegistry.register("x", "xv")
        _TestRegistry.register("y", "yv")

        keys = _TestRegistry.registered_keys()

        assert set(keys) == {"x", "y"}

    def test_clear_empties_the_store(self):
        """clear() removes all entries so a subsequent get() raises."""
        _TestRegistry.register("will-be-gone", "v")
        _TestRegistry.clear()

        with pytest.raises(RegistryLookupError):
            _TestRegistry.get("will-be-gone")

        assert _TestRegistry.registered_keys() == []

    def test_get_on_empty_registry_names_no_keys(self):
        """Error message for a completely empty registry says '<none>'."""
        with pytest.raises(RegistryLookupError) as exc_info:
            _TestRegistry.get("anything")

        assert "<none>" in str(exc_info.value)

    def test_registry_lookup_error_is_configuration_error(self):
        """RegistryLookupError is a ConfigurationError (correct hierarchy)."""
        from orb.domain.base.exceptions import ConfigurationError

        err = RegistryLookupError("R", "k", ["a", "b"])
        assert isinstance(err, ConfigurationError)
