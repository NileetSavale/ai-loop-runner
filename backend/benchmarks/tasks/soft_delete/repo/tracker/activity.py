import heapq


def recent(store, count=5):
    return heapq.nlargest(count, store.projects.values(), key=lambda p: p.updated)
