"""Shared helpers for Azure strategy tests."""

import asyncio


def run_operation(coro):
    """Run a coroutine in a fresh event loop for synchronous tests."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
