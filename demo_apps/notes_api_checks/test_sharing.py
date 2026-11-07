"""The feature the team is asked to build. Hidden from the agents."""


def share(client, note_id, username, headers):
    return client.post(f"/notes/{note_id}/share", json={"username": username}, headers=headers)


def test_owner_can_share_and_recipient_sees_the_note(client, login):
    alice, bob = login("alice"), login("bob")
    note_id = client.post("/notes", json={"title": "Plan"}, headers=alice).json()["id"]
    assert share(client, note_id, "bob", alice).status_code == 200
    assert "Plan" in [n["title"] for n in client.get("/notes", headers=bob).json()]
    assert client.get(f"/notes/{note_id}", headers=bob).json()["title"] == "Plan"


def test_recipient_cannot_delete_a_shared_note(client, login):
    alice, bob = login("alice"), login("bob")
    note_id = client.post("/notes", json={"title": "Plan"}, headers=alice).json()["id"]
    share(client, note_id, "bob", alice)
    assert client.delete(f"/notes/{note_id}", headers=bob).status_code in (403, 404)
    assert client.get(f"/notes/{note_id}", headers=alice).status_code == 200


def test_only_the_owner_can_share(client, login):
    alice, bob, _ = login("alice"), login("bob"), login("carol")
    note_id = client.post("/notes", json={"title": "Plan"}, headers=alice).json()["id"]
    assert share(client, note_id, "carol", bob).status_code in (403, 404)


def test_sharing_with_an_unknown_user_is_404(client, login):
    alice = login("alice")
    note_id = client.post("/notes", json={"title": "Plan"}, headers=alice).json()["id"]
    assert share(client, note_id, "nobody", alice).status_code == 404


def test_unshared_notes_stay_private(client, login):
    alice, bob = login("alice"), login("bob")
    client.post("/notes", json={"title": "Private"}, headers=alice)
    assert client.get("/notes", headers=bob).json() == []
