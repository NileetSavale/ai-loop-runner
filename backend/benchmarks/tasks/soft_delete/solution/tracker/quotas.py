def can_create(store, owner, limit=3):
    return sum(1 for p in store.live() if p.owner == owner) < limit
