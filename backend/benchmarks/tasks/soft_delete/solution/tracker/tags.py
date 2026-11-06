from collections import Counter

from tracker.projects import get_project


def add_tag(store, project_id, tag):
    project = get_project(store, project_id)
    project.tags.add(tag)
    project.updated = store.tick()


def projects_with_tag(store, tag):
    return [p for p in store.live() if tag in p.tags]


def tag_counts(store):
    return dict(Counter(tag for p in store.live() for tag in p.tags))
