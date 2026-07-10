"""
Unit tests for SQL-level optimistic concurrency control (OCC).

These tests verify the compare-and-swap predicate in SQLStorageStrategy.save()
and the version-predicate generation in SQLQueryBuilder.build_update().

All tests use SQLite :memory: — they are deterministic and have no I/O
dependencies beyond the in-process SQLite engine.
"""

import pytest

from orb.domain.base.exceptions import ConcurrencyError
from orb.infrastructure.storage.components.sql_query_builder import (
    SQLQueryBuilder,
)
from orb.infrastructure.storage.sql.strategy import SQLStorageStrategy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COLUMNS = {
    "id": "TEXT PRIMARY KEY",
    "name": "TEXT",
    "version": "INTEGER",
    "updated_at": "TEXT",
}


def _make_strategy() -> SQLStorageStrategy:
    """Construct an in-memory SQLite strategy with a versioned table."""
    return SQLStorageStrategy(
        config={"type": "sqlite", "name": ":memory:"},
        table_name="entities",
        columns=_COLUMNS,
    )


def _save_initial(strategy: SQLStorageStrategy, entity_id: str, version: int = 0) -> None:
    """Insert a brand-new entity (version starts at 0)."""
    strategy.save(entity_id, {"id": entity_id, "name": "initial", "version": version})


# ---------------------------------------------------------------------------
# Test group 1: SQLQueryBuilder.build_update CAS predicate
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBuildUpdateVersionPredicate:
    """build_update emits the correct SQL when expected_version is provided."""

    def setup_method(self):
        self.builder = SQLQueryBuilder(
            "t", {"id": "TEXT PRIMARY KEY", "name": "TEXT", "version": "INTEGER"}
        )

    def test_no_expected_version_omits_predicate(self):
        """Default (no expected_version) produces unconditional WHERE id = :entity_id."""
        sql, params = self.builder.build_update({"name": "x", "version": 1}, "id", "e1")
        assert "AND version" not in sql
        assert "expected_version" not in params
        assert "WHERE id = :entity_id" in sql

    def test_expected_version_adds_cas_predicate(self):
        """Providing expected_version adds AND version = :expected_version to WHERE."""
        sql, params = self.builder.build_update(
            {"name": "x", "version": 1}, "id", "e1", expected_version=0
        )
        assert "AND version = :expected_version" in sql
        assert params["expected_version"] == 0

    def test_expected_version_zero_is_valid(self):
        """expected_version=0 is a legitimate first-update guard (server_default row)."""
        sql, params = self.builder.build_update(
            {"name": "x", "version": 1}, "id", "e1", expected_version=0
        )
        assert params["expected_version"] == 0
        assert "AND version = :expected_version" in sql

    def test_version_column_included_in_set_clause(self):
        """The new version value appears in the SET clause."""
        sql, params = self.builder.build_update(
            {"name": "x", "version": 3}, "id", "e1", expected_version=2
        )
        assert "version = :version" in sql
        assert params["version"] == 3

    def test_none_expected_version_keeps_original_behaviour(self):
        """Explicitly passing None keeps original single-predicate WHERE."""
        sql, _ = self.builder.build_update(
            {"name": "x", "version": 1}, "id", "e1", expected_version=None
        )
        assert "AND version" not in sql


# ---------------------------------------------------------------------------
# Test group 2: INSERT path is unaffected
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInsertPathUnaffected:
    """New entities (INSERT) must not trigger ConcurrencyError."""

    def test_first_save_inserts_without_concurrency_check(self):
        """Saving a new entity with version=0 must succeed without any CAS logic."""
        strategy = _make_strategy()
        # No exception should be raised
        strategy.save("new-entity", {"id": "new-entity", "name": "initial", "version": 0})
        loaded = strategy.find_by_id("new-entity")
        assert loaded is not None

    def test_version_zero_insert_roundtrips(self):
        """Version is stored and retrieved correctly on the happy INSERT path."""
        strategy = _make_strategy()
        strategy.save("e1", {"id": "e1", "name": "alpha", "version": 0})
        data = strategy.find_by_id("e1")
        assert data is not None
        assert data.get("version") == 0


# ---------------------------------------------------------------------------
# Test group 3: Version increments on successful save
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestVersionIncrementsOnSave:
    """Each successful save bumps the version stored in the DB."""

    def test_version_increments_single_writer(self):
        """Sequential single-writer saves bump the version column each time."""
        strategy = _make_strategy()

        # First write: new entity with version 0
        strategy.save("e1", {"id": "e1", "name": "v0", "version": 0})

        # Second write: aggregate mutation increments to 1
        strategy.save("e1", {"id": "e1", "name": "v1", "version": 1})
        data = strategy.find_by_id("e1")
        assert data is not None
        assert data.get("version") == 1

    def test_multiple_sequential_saves_track_version(self):
        """Five sequential saves correctly advance the version to 4."""
        strategy = _make_strategy()
        strategy.save("e1", {"id": "e1", "name": "v0", "version": 0})
        for v in range(1, 5):
            strategy.save("e1", {"id": "e1", "name": f"v{v}", "version": v})
        data = strategy.find_by_id("e1")
        assert data is not None
        assert data.get("version") == 4


# ---------------------------------------------------------------------------
# Test group 4: Stale-version write raises ConcurrencyError
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestStaleVersionRaisesConcurrencyError:
    """Two saves with a stale version on the second must raise ConcurrencyError."""

    def test_second_stale_save_raises(self):
        """
        Scenario: two 'writers' load version=0 simultaneously.

        Writer A saves first (version 0 → 1 in DB).
        Writer B then tries to save with version=1 (expecting DB version=0),
        but the DB now has version=1 — rowcount is 0 → ConcurrencyError.
        """
        strategy = _make_strategy()

        # Both writers read the entity at version=0
        _save_initial(strategy, "e1", version=0)

        # Writer A succeeds: version 0 → 1
        strategy.save("e1", {"id": "e1", "name": "writer-a", "version": 1})

        # Writer B is stale: it also has version=0, increments to 1, but
        # DB already has version=1 → expected_version=0 mismatch.
        with pytest.raises(ConcurrencyError) as exc_info:
            strategy.save("e1", {"id": "e1", "name": "writer-b", "version": 1})

        assert "e1" in str(exc_info.value)
        # The winning write from A should still be in the DB unchanged.
        data = strategy.find_by_id("e1")
        assert data is not None
        assert data.get("name") == "writer-a"
        assert data.get("version") == 1

    def test_concurrency_error_includes_entity_id(self):
        """ConcurrencyError message contains the entity id for debugging."""
        strategy = _make_strategy()
        _save_initial(strategy, "some-entity", version=0)

        # Advance to version 1
        strategy.save("some-entity", {"id": "some-entity", "name": "a", "version": 1})

        # Stale save (still expects DB version=0)
        with pytest.raises(ConcurrencyError) as exc_info:
            strategy.save("some-entity", {"id": "some-entity", "name": "b", "version": 1})

        assert "some-entity" in str(exc_info.value)

    def test_concurrent_writes_only_one_wins(self):
        """
        Three 'writers' all read version=N.  Only the first to save wins;
        the other two must receive ConcurrencyError.
        """
        strategy = _make_strategy()
        _save_initial(strategy, "shared", version=0)

        # Writer 1 wins
        strategy.save("shared", {"id": "shared", "name": "winner", "version": 1})

        # Writers 2 and 3 are stale
        for loser_name in ("loser-2", "loser-3"):
            with pytest.raises(ConcurrencyError):
                strategy.save("shared", {"id": "shared", "name": loser_name, "version": 1})

        # DB reflects only the winner
        data = strategy.find_by_id("shared")
        assert data is not None
        assert data.get("name") == "winner"
        assert data.get("version") == 1

    def test_non_versioned_table_save_never_raises(self):
        """
        A table without a ``version`` column in its schema must never raise
        ConcurrencyError — the opt-in CAS logic must not fire.
        """
        strategy = SQLStorageStrategy(
            config={"type": "sqlite", "name": ":memory:"},
            table_name="unversioned",
            columns={"id": "TEXT PRIMARY KEY", "val": "TEXT"},
        )
        strategy.save("u1", {"id": "u1", "val": "first"})
        # Unconditional overwrite — no ConcurrencyError
        strategy.save("u1", {"id": "u1", "val": "second"})
        data = strategy.find_by_id("u1")
        assert data is not None
        assert data.get("val") == "second"

    def test_happy_path_sequential_saves_never_raise(self):
        """
        The single-writer happy path must not raise ConcurrencyError at any
        version — the CAS predicate must match on every sequential write.
        """
        strategy = _make_strategy()
        _save_initial(strategy, "seq", version=0)
        for v in range(1, 10):
            # Each save correctly carries the incremented version.
            strategy.save("seq", {"id": "seq", "name": f"step-{v}", "version": v})
        data = strategy.find_by_id("seq")
        assert data is not None
        assert data.get("version") == 9
