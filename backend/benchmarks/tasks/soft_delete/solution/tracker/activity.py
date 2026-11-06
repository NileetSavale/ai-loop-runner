import heapq


def recent(store, count=5):
    return heapq.nlargest(count, store.live(), key=lambda p: p.updated)
