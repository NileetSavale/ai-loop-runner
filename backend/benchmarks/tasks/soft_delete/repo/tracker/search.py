def search(store, query):
    query = query.lower()
    return [p for p in store.projects.values() if query in p.name.lower()]
