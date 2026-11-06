import pytest
from tracker.errors import NotFound
from tracker.projects import create_project, delete_project, deleted_projects, get_project, list_projects
from tracker.store import Store


def test_deleted_project_is_hidden_but_kept():
    store = Store()
    project = create_project(store, "Alpha", "ann")
    delete_project(store, project.id)
    assert list_projects(store) == []
    assert [p.name for p in deleted_projects(store)] == ["Alpha"]
    with pytest.raises(NotFound):
        get_project(store, project.id)
