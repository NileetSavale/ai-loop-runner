def can_create(store, owner, limit=3):
    return sum(1 for p in store.projects.values() if p.owner == owner) < limit
