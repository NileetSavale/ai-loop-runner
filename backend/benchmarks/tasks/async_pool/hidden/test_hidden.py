import asyncio

import pytest
from pool import run_bounded


def test_limit_is_respected_and_factories_are_called_lazily():
    called, running, peak = [], 0, 0

    def factory(index):
        async def job():
            nonlocal running, peak
            running += 1
            peak = max(peak, running)
            assert len(called) - sum(finished) <= 2  # a factory only runs once a slot is free
            await asyncio.sleep(0.01)
            running -= 1
            finished.append(1)
            return index
        called.append(index)
        return job()

    finished = []
    results = asyncio.run(run_bounded([lambda i=i: factory(i) for i in range(6)], 2))
    assert results == list(range(6)) and peak == 2 and called == list(range(6))


def test_results_stay_in_input_order_when_jobs_finish_out_of_order():
    async def job(value, delay):
        await asyncio.sleep(delay)
        return value
    factories = [lambda: job("slow", 0.03), lambda: job("fast", 0.0)]
    assert asyncio.run(run_bounded(factories, 2)) == ["slow", "fast"]


def test_errors_take_their_place_by_default():
    async def ok():
        return 1

    async def bad():
        raise KeyError("x")
    results = asyncio.run(run_bounded([ok, bad, ok], 1))
    assert results[0] == 1 and isinstance(results[1], KeyError) and results[2] == 1


def test_stop_on_error_cancels_awaits_cleanup_and_starts_nothing_new():
    started, cleaned = [], []

    async def slow():
        started.append("slow")
        try:
            await asyncio.sleep(10)
        finally:
            await asyncio.sleep(0.01)  # cleanup takes time, and must finish
            cleaned.append("slow")

    async def bad():
        await asyncio.sleep(0.01)
        raise KeyError("boom")

    async def never():
        started.append("never")

    async def main():
        with pytest.raises(KeyError):
            await asyncio.wait_for(run_bounded([slow, bad, never], 2, stop_on_error=True), 1)

    asyncio.run(main())
    assert started == ["slow"] and cleaned == ["slow"]


def test_first_error_wins_over_errors_during_cancellation():
    async def fails_in_cleanup():
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise ValueError("late")

    async def bad():
        await asyncio.sleep(0.01)
        raise KeyError("first")

    async def main():
        with pytest.raises(KeyError):
            await asyncio.wait_for(run_bounded([fails_in_cleanup, bad], 2, stop_on_error=True), 1)

    asyncio.run(main())


def test_outer_cancellation_cleans_up_and_propagates():
    cleaned, started = [], []

    async def slow():
        started.append("slow")
        try:
            await asyncio.sleep(10)
        finally:
            await asyncio.sleep(0.01)
            cleaned.append("slow")

    async def waiting():
        started.append("waiting")

    async def main():
        outer = asyncio.create_task(run_bounded([slow, waiting], 1))
        await asyncio.sleep(0.01)
        outer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await outer

    asyncio.run(main())
    assert cleaned == ["slow"] and started == ["slow"]


@pytest.mark.parametrize("limit", [0, -1])
def test_bad_limit(limit):
    with pytest.raises(ValueError):
        asyncio.run(run_bounded([], limit))


def test_empty_list():
    assert asyncio.run(run_bounded([], 3)) == []
