import pytest
from tracker.activity import recent
from tracker.errors import NameTaken, NotFound
from tracker.export import export_lines
from tracker.projects import (
    create_project, delete_project, deleted_projects, get_project, list_projects, rename_project, restore_project,
)
from tracker.quotas import can_create
from tracker.search import search
from tracker.stats import counts_by_owner, project_count
from tracker.store import Store
from tracker.tags import add_tag, projects_with_tag, tag_counts


@pytest.fixture
def world():
    store = Store()
    keep = create_project(store, "Keep", "ann")
    gone = create_project(store, "Gone", "ann")
    add_tag(store, keep.id, "red")
    add_tag(store, gone.id, "red")
    add_tag(store, gone.id, "blue")
    delete_project(store, gone.id)
    return store, keep, gone


def names(projects):
    return [p.name for p in projects]


def test_listings(world):
    store, *_ = world
    assert names(list_projects(store)) == ["Keep"]
    assert names(list_projects(store, owner="ann")) == ["Keep"]


def test_search(world):
    assert names(search(world[0], "gon")) == []


def test_stats(world):
    store, *_ = world
    assert project_count(store) == 1
    assert counts_by_owner(store) == {"ann": 1}


def test_stats_drop_owners_with_only_deleted_projects():
    store = Store()
    only = create_project(store, "Only", "bob")
    delete_project(store, only.id)
    assert counts_by_owner(store) == {}


def test_tags(world):
    store, *_ = world
    assert names(projects_with_tag(store, "red")) == ["Keep"]
    assert projects_with_tag(store, "blue") == []
    assert tag_counts(store) == {"red": 1}


def test_export(world):
    store, keep, _ = world
    assert export_lines(store) == [f"{keep.id},Keep,ann"]


def test_recent(world):
    assert names(recent(world[0])) == ["Keep"]


def test_quota_ignores_deleted_projects():
    store = Store()
    made = [create_project(store, f"P{i}", "ann") for i in range(3)]
    assert can_create(store, "ann") is False
    delete_project(store, made[0].id)
    assert can_create(store, "ann") is True


@pytest.mark.parametrize("action", [
    lambda s, i: get_project(s, i),
    lambda s, i: rename_project(s, i, "New"),
    lambda s, i: delete_project(s, i),
    lambda s, i: add_tag(s, i, "green"),
])
def test_actions_treat_deleted_as_missing(world, action):
    store, _, gone = world
    with pytest.raises(NotFound):
        action(store, gone.id)


def test_name_can_be_reused_by_create_and_rename(world):
    store, keep, _ = world
    assert create_project(store, "Gone", "bob").name == "Gone"
    delete_project(store, keep.id)
    other = create_project(store, "Other", "bob")
    assert rename_project(store, other.id, "Keep").name == "Keep"


def test_restore_brings_it_back_unchanged(world):
    store, _, gone = world
    restored = restore_project(store, gone.id)
    assert (restored.name, restored.owner, restored.tags) == ("Gone", "ann", {"red", "blue"})
    assert get_project(store, gone.id) is not None
    assert sorted(names(list_projects(store))) == ["Gone", "Keep"]
    assert deleted_projects(store) == []
    assert tag_counts(store) == {"red": 2, "blue": 1}


def test_restore_refuses_a_reused_name(world):
    store, _, gone = world
    create_project(store, "Gone", "bob")
    with pytest.raises(NameTaken):
        restore_project(store, gone.id)
    assert names(deleted_projects(store)) == ["Gone"]


@pytest.mark.parametrize("project", ["live", "missing"])
def test_restore_needs_a_deleted_project(world, project):
    store, keep, _ = world
    with pytest.raises(NotFound):
        restore_project(store, keep.id if project == "live" else 999)


def test_ids_are_never_reused(world):
    store, _, gone = world
    assert create_project(store, "New", "ann").id > gone.id
