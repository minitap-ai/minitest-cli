"""Bounded fan-out for requests sent through one ApiClient."""

import asyncio
from collections.abc import Awaitable, Iterable

# Enough to overlap round trips, small enough not to queue a burst on the API.
DEFAULT_FANOUT_LIMIT = 6


async def gather_bounded[T](
    aws: Iterable[Awaitable[T]], *, limit: int = DEFAULT_FANOUT_LIMIT
) -> list[T]:
    """``asyncio.gather`` with at most ``limit`` awaitables running at once.

    Results come back in input order. The first exception propagates to the
    caller and the other awaitables are left running, exactly like
    ``asyncio.gather`` without ``return_exceptions``. Pass coroutines, not
    tasks: a coroutine only starts once it holds a slot.
    """
    if limit < 1:
        msg = f"limit must be at least 1, got {limit}"
        raise ValueError(msg)
    semaphore = asyncio.Semaphore(limit)

    async def _run(aw: Awaitable[T]) -> T:
        async with semaphore:
            return await aw

    return list(await asyncio.gather(*(_run(aw) for aw in aws)))
