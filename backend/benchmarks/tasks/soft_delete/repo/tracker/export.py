def export_lines(store):
    rows = sorted(store.projects.values(), key=lambda p: p.id)
    return [f"{p.id},{p.name},{p.owner}" for p in rows]
