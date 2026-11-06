from tracker.errors import NameTaken, NotFound
from tracker.store import Project


def create_project(store, name, owner):
    if any(p.name == name for p in store.projects.values()):
        raise NameTaken(name)
    project = Project(store.next_id, name, owner, updated=store.tick())
    store.projects[project.id] = project
    store.next_id += 1
    return project


def get_project(store, project_id):
    if project_id not in store.projects:
        raise NotFound(project_id)
    return store.projects[project_id]


def list_projects(store, owner=None):
    return [p for p in store.projects.values() if owner is None or p.owner == owner]


def rename_project(store, project_id, name):
    project = get_project(store, project_id)
    if any(p.name == name and p.id != project_id for p in store.projects.values()):
        raise NameTaken(name)
    project.name = name
    project.updated = store.tick()
    return project


def delete_project(store, project_id):
    get_project(store, project_id)
    del store.projects[project_id]
