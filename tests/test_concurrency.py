"""gather_bounded: asyncio.gather semantics with a cap on in-flight awaitables."""

import asyncio

import pytest

from minitest_cli.utils.concurrency import DEFAULT_FANOUT_LIMIT, gather_bounded


class _Probe:
    def __init__(self) -> None:
        self.in_flight = 0
        self.peak = 0
        self.started: list[int] = []
        self.finished: list[int] = []

    async def work(self, index: int, delay: float, *, fail: bool = False) -> int:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        self.started.append(index)
        try:
            await asyncio.sleep(delay)
            if fail:
                raise ValueError(f"boom {index}")
            return index * 10
        finally:
            self.in_flight -= 1
            self.finished.append(index)


class TestGatherBounded:
    def test_gather_bounded_preserves_input_order(self) -> None:
        probe = _Probe()
        # Later items finish first, so completion order is the reverse of input order.
        delays = [0.002 * (20 - i) for i in range(20)]

        results = asyncio.run(
            gather_bounded((probe.work(i, d) for i, d in enumerate(delays)), limit=20)
        )

        assert results == [i * 10 for i in range(20)]
        assert probe.finished != sorted(probe.finished)

    @pytest.mark.parametrize("limit", [1, 3, DEFAULT_FANOUT_LIMIT])
    def test_gather_bounded_caps_in_flight(self, limit: int) -> None:
        probe = _Probe()

        results = asyncio.run(
            gather_bounded((probe.work(i, 0.001 * (i % 4)) for i in range(25)), limit=limit)
        )

        assert results == [i * 10 for i in range(25)]
        assert probe.peak == limit

    def test_gather_bounded_default_limit_is_six(self) -> None:
        probe = _Probe()

        asyncio.run(gather_bounded(probe.work(i, 0.001) for i in range(25)))

        assert DEFAULT_FANOUT_LIMIT == 6
        assert probe.peak == 6

    def test_gather_bounded_propagates_first_exception_like_gather(self) -> None:
        probe = _Probe()

        async def run() -> None:
            await gather_bounded(
                (probe.work(i, 0.001, fail=i in {4, 9}) for i in range(12)), limit=3
            )

        with pytest.raises(ValueError, match="boom 4"):
            asyncio.run(run())

    def test_gather_bounded_leaves_siblings_running_like_gather(self) -> None:
        probe = _Probe()

        async def run() -> None:
            with pytest.raises(ValueError, match="boom 0"):
                await gather_bounded(
                    (probe.work(i, 0.0 if i == 0 else 0.002, fail=i == 0) for i in range(5)),
                    limit=2,
                )
            await asyncio.sleep(0.05)

        asyncio.run(run())
        assert sorted(probe.finished) == list(range(5))

    def test_gather_bounded_empty_input(self) -> None:
        assert asyncio.run(gather_bounded([])) == []

    def test_gather_bounded_rejects_non_positive_limit(self) -> None:
        with pytest.raises(ValueError, match="at least 1"):
            asyncio.run(gather_bounded([], limit=0))
