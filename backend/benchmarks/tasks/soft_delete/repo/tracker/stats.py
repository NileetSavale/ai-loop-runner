from collections import Counter


def project_count(store):
    return len(store.projects)


def counts_by_owner(store):
    return dict(Counter(p.owner for p in store.projects.values()))
