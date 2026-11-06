import asyncio


async def run_bounded(factories, limit, stop_on_error=False):
    if limit < 1:
        raise ValueError("limit must be at least 1")
    results = [None] * len(factories)
    running = {}
    next_index = 0
    first_error = None

    async def call(factory):
        return await factory()

    async def cancel_running():
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)

    try:
        while next_index < len(factories) or running:
            while first_error is None and next_index < len(factories) and len(running) < limit:
                running[asyncio.ensure_future(call(factories[next_index]))] = next_index
                next_index += 1
            if not running:
                break
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            for task in sorted(done, key=running.get):
                index = running.pop(task)
                error = task.exception()
                if error is None:
                    results[index] = task.result()
                elif stop_on_error:
                    first_error = first_error or error
                else:
                    results[index] = error
            if first_error is not None:
                await cancel_running()
                raise first_error
    except asyncio.CancelledError:
        await cancel_running()
        raise
    return results
