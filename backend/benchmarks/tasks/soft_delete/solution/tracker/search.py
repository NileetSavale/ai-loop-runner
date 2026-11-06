def search(store, query):
    query = query.lower()
    return [p for p in store.live() if query in p.name.lower()]
