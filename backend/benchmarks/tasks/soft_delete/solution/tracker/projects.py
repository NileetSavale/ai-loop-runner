from tracker.errors import NameTaken, NotFound
from tracker.store import Project


def create_project(store, name, owner):
    if any(p.name == name for p in store.live()):
        raise NameTaken(name)
    project = Project(store.next_id, name, owner, updated=store.tick())
    store.projects[project.id] = project
    store.next_id += 1
    return project


def get_project(store, project_id):
    project = store.projects.get(project_id)
    if project is None or project.deleted:
        raise NotFound(project_id)
    return project


def list_projects(store, owner=None):
    return [p for p in store.live() if owner is None or p.owner == owner]


def rename_project(store, project_id, name):
    project = get_project(store, project_id)
    if any(p.name == name and p.id != project_id for p in store.live()):
        raise NameTaken(name)
    project.name = name
    project.updated = store.tick()
    return project


def delete_project(store, project_id):
    get_project(store, project_id).deleted = True


def restore_project(store, project_id):
    project = store.projects.get(project_id)
    if project is None or not project.deleted:
        raise NotFound(project_id)
    if any(p.name == project.name for p in store.live()):
        raise NameTaken(project.name)
    project.deleted = False
    return project


def deleted_projects(store):
    return [p for p in store.projects.values() if p.deleted]
