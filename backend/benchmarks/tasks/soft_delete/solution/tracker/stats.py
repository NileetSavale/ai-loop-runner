from collections import Counter


def project_count(store):
    return len(store.live())


def counts_by_owner(store):
    return dict(Counter(p.owner for p in store.live()))
