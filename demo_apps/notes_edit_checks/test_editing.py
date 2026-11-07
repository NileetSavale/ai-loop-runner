"""Note editing, the third task in the TeamNotes sequence. Hidden from the agents."""


def note(client, headers, title="Plan", body="v1"):
    return client.post("/notes", json={"title": title, "body": body}, headers=headers).json()["id"]


def test_owner_can_edit(client, login):
    alice = login("alice")
    n = note(client, alice)
    changed = client.put(f"/notes/{n}", json={"title": "Plan B", "body": "v2"}, headers=alice)
    assert changed.status_code == 200 and changed.json()["title"] == "Plan B"
    assert client.get(f"/notes/{n}", headers=alice).json()["body"] == "v2"


def test_editing_a_missing_note_is_404(client, login):
    alice = login("alice")
    assert client.put("/notes/999", json={"title": "x", "body": "y"}, headers=alice).status_code == 404


def test_shared_user_cannot_edit(client, login):
    alice, bob = login("alice"), login("bob")
    n = note(client, alice)
    client.post(f"/notes/{n}/share", json={"username": "bob"}, headers=alice)
    client.put(f"/notes/{n}", json={"title": "bob was here", "body": ""}, headers=bob)
    assert client.get(f"/notes/{n}", headers=alice).json()["title"] == "Plan"


def test_stranger_cannot_edit(client, login):
    alice, mallory = login("alice"), login("mallory")
    n = note(client, alice)
    assert client.put(f"/notes/{n}", json={"title": "pwned", "body": ""}, headers=mallory).status_code in (403, 404)
    assert client.get(f"/notes/{n}", headers=alice).json()["title"] == "Plan"
