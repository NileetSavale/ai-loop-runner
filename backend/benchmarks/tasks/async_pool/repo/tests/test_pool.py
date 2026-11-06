import asyncio

from pool import run_bounded


async def double(value):
    await asyncio.sleep(0)
    return value * 2


def test_results_keep_their_order():
    factories = [lambda v=v: double(v) for v in (1, 2, 3)]
    assert asyncio.run(run_bounded(factories, 2, stop_on_error=False)) == [2, 4, 6]
