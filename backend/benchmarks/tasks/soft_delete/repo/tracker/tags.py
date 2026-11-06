from collections import Counter

from tracker.errors import NotFound


def add_tag(store, project_id, tag):
    if project_id not in store.projects:
        raise NotFound(project_id)
    store.projects[project_id].tags.add(tag)
    store.projects[project_id].updated = store.tick()


def projects_with_tag(store, tag):
    return [p for p in store.projects.values() if tag in p.tags]


def tag_counts(store):
    return dict(Counter(tag for p in store.projects.values() for tag in p.tags))
