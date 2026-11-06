import asyncio


async def run_bounded(factories, limit):
    semaphore = asyncio.Semaphore(limit)

    async def guarded(coroutine):
        async with semaphore:
            return await coroutine

    return await asyncio.gather(*(guarded(factory()) for factory in factories))
