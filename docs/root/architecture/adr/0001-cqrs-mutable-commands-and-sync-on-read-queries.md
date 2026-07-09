# ADR-0001: CQRS with Mutable Commands and Sync-on-Read Queries

**Status:** Accepted  
**Date:** 2026-07-09  
**Context:** Application layer CQRS design

---

## Context

The codebase follows CQRS (Command Query Responsibility Segregation): commands change state,
queries read state. Two intentional deviations from strict CQRS purity exist, both load-bearing
and documented here so future contributors understand what they are, why they exist, and what
the naming convention is going forward.

---

## Decision 1: Mutable Result-Carrying Commands

### What

`BaseCommand` (`src/orb/application/dto/base.py`) uses `model_config = ConfigDict(frozen=False)`.
Command DTOs are **mutable** — handlers are allowed to write result data back into the command
object after execution.

```python
class BaseCommand(BaseDTO, Command):
    """Base class for command DTOs.

    CQRS: Commands can store results in mutable fields for callers to access.
    This allows commands to return void while still providing result data.
    """
    model_config = ConfigDict(frozen=False)  # Allow mutation for result storage
```

### Why

The `CommandBus.execute()` method returns `None` (CQRS purity: commands are fire-and-forget).
Some callers need to retrieve data produced by the command (e.g. the created resource's ID)
without turning the command into a query. Storing the result in a mutable field on the command
object itself lets callers access it after `await command_bus.execute(cmd)` completes, without
introducing an out-of-band side channel or a return value.

This is a deliberate **CQRS-by-mutation** pattern: the command bus returns void; the caller
reads the result from the command object.

### Trade-offs

| Pro | Con |
|-----|-----|
| Command bus signature stays `execute() -> None` | DTO is mutable; callers must know to read the field |
| Works without protocol changes | Field is set as a side effect, not via return value |
| Familiar to callers that already hold the command reference | Can confuse readers who expect DTOs to be immutable |

### Naming convention

Command classes keep their existing `XxxCommand` names. No suffix is required because
**all commands can mutate** — it is the base-class default. Document result-carrying fields
in the docstring of the specific command class.

---

## Decision 2: Sync-on-Read Query Handlers

### What

Several query handlers perform **provider synchronisation** (refresh + persist) as a side
effect of answering a read request. This means that running these queries writes to the
database. The affected handlers are:

| Query DTO | Handler | What it writes |
|-----------|---------|----------------|
| `SyncAndGetRequestQuery` | `SyncAndGetRequestHandler` | `uow.machines.save()` for each changed machine; `uow.requests.save()` to stamp `first_status_check` / `last_status_check` |
| `SyncAndListActiveRequestsQuery` | `SyncAndListActiveRequestsHandler` | Same per active (non-terminal) request on the returned page |
| `SyncAndListReturnRequestsQuery` | `SyncAndListReturnRequestsHandler` | Same per non-terminal return request |

The writes are performed inside `MachineSyncService.sync_machines_with_provider()` and
`RequestStatusService.update_request_status()`, which are invoked from the handler.

### Why

The database is treated as a **cache of provider state** (EC2, Kubernetes, etc.). A "get
request status" call must reflect reality, not a stale snapshot from the last background
poll cycle. Without a background polling service running independently, the only opportunity
to refresh the read model is when a client asks for the current state — i.e. during the
query itself.

This is a **sync-on-read** (read-through cache refresh) pattern, not a domain command.
No domain invariants are enforced and no domain events are raised during the sync. The sync
is purely an infrastructure concern: update the cached provider state before returning it.

Consequences of removing this sync without adding background polling:

- Clients polling "get request status" would see a request stuck in `IN_PROGRESS` until
  the next background poll cycle (if one existed).
- Return requests that completed at the provider would show as `IN_PROGRESS` indefinitely,
  potentially triggering double-decrement retries (ASG capacity off-by-one).
- The `successful_count` reconciliation would never fire for provisioning requests.

**The alternative is a background sync service.** If one is implemented, these handlers
should be refactored to pure reads. Until then, the sync-on-read pattern is intentional
and must not be removed in the name of "CQRS purity".

The `GetRequestHandler` already documents this inline:

```python
# Read-through sync: refresh the read model (DB) from live AWS state before
# returning. This is intentional — the DB is a cache of provider state, and
# status queries must reflect reality. Do NOT remove this in the name of
# "CQRS purity". A query refreshing its own read model is not a domain command;
# no domain invariants are enforced here, no domain events are raised.
# The alternative (background polling) requires infrastructure that doesn't
# exist yet. If you want to remove this, implement a background sync first.
```

### Trade-offs

| Pro | Con |
|-----|-----|
| Client always sees live provider state | Query has a write side effect — surprises strict CQRS readers |
| No separate background worker needed | Higher latency per query (one provider round-trip) |
| Correct behaviour for return-request double-decrement prevention | Sync failures can affect read availability (mitigated by fallback to stored state) |
| `MachineSyncService` encapsulates the write so handlers stay thin | Pagination + sync combined bounds cost to one page, not the whole dataset |

### Naming convention (enforced from this ADR)

Sync-writing query handlers **must carry a `SyncAnd` prefix** so their name reveals the
write side effect:

- `SyncAndGetXQuery` / `SyncAndGetXHandler` — single-entity sync-on-read
- `SyncAndListXQuery` / `SyncAndListXHandler` — collection sync-on-read

Pure read-only queries (no provider call, no write) keep the `GetX` / `ListX` naming.

Borderline case — opt-in sync flag:

`ListMachinesQuery` has a `sync: bool = False` flag. When `sync=False` (the default used
by all production callers) it is a pure read; when `sync=True` it triggers per-machine
provider fetches and writes. Because the default is read-only and no production caller
passes `sync=True`, this class keeps the `ListMachines` name. If a caller is introduced
that relies on `sync=True`, that call site should be wrapped in an explicit service method
named to reveal the write.

---

## Consequences

1. The three sync-writing query classes (`SyncAndGetRequestQuery`,
   `SyncAndListActiveRequestsQuery`, `SyncAndListReturnRequestsQuery`) have been renamed
   from their original `Get` / `List` names. All call sites (orchestration services, CLI
   factories, API routers, tests) have been updated to use the new names.

2. When reviewing a PR that adds a new query handler: if the handler calls
   `MachineSyncService`, `RequestStatusService.update_request_status`, or any `uow.*.save`
   / `uow.commit`, it must be named `SyncAndXxx` not `GetXxx` / `ListXxx`.

3. When background polling is eventually implemented, these handlers should be refactored
   to pure reads (drop the `MachineSyncService` dependency) and renamed back to `Get` /
   `List` without the `SyncAnd` prefix.
