from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")

# Shared polling constants used by orchestrators that block-and-poll until a
# request reaches a terminal state.  Both spellings of "complete/completed" and
# "cancel/cancelled" are included because the HostFactory scheduler returns
# "completed" / "canceled" (past-tense) whereas the internal RequestStatus enum
# uses "complete" / "cancelled".  The defensive set keeps polling correct across
# both sources without adding a spelling-normalisation step to every caller.
TERMINAL_STATUSES: frozenset[str] = frozenset(
    {
        "complete",
        "completed",
        "failed",
        "error",
        "cancelled",
        "canceled",
        "partial",
        "timeout",
    }
)
MAX_CONSECUTIVE_POLL_ERRORS: int = 3


class OrchestratorBase(ABC, Generic[InputT, OutputT]):
    """Base class for all interface-facing orchestrators.

    Orchestrators are the single source of truth for each operation.
    They dispatch CQRS commands/queries and return typed DTOs.
    They do NOT call SchedulerPort — formatting is the adapter's concern.
    They do NOT call get_container() — all deps are constructor-injected.
    """

    @abstractmethod
    async def execute(self, input: InputT) -> OutputT:  # type: ignore[return]
        pass
