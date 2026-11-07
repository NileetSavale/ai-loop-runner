def test_register_and_login(client):
    assert client.post("/register", json={"username": "alice", "password": "pw1"}).status_code == 201
    assert client.post("/login", json={"username": "alice", "password": "pw1"}).status_code == 200


def test_username_is_unique(client):
    client.post("/register", json={"username": "alice", "password": "pw1"})
    assert client.post("/register", json={"username": "alice", "password": "pw2"}).status_code == 409


def test_wrong_password_is_refused(client):
    client.post("/register", json={"username": "alice", "password": "pw1"})
    assert client.post("/login", json={"username": "alice", "password": "nope"}).status_code == 401


def test_notes_need_login(client):
    assert client.get("/notes").status_code == 401


def test_create_and_list_notes(client, login):
    alice = login("alice")
    client.post("/notes", json={"title": "Groceries", "body": "milk"}, headers=alice)
    notes = client.get("/notes", headers=alice).json()
    assert [n["title"] for n in notes] == ["Groceries"]


def test_users_only_list_their_own_notes(client, login):
    alice, bob = login("alice"), login("bob")
    client.post("/notes", json={"title": "Alice's plan"}, headers=alice)
    assert client.get("/notes", headers=bob).json() == []


def test_search_by_title(client, login):
    alice = login("alice")
    client.post("/notes", json={"title": "Trip to Lisbon"}, headers=alice)
    client.post("/notes", json={"title": "Groceries"}, headers=alice)
    found = client.get("/notes/search", params={"q": "lisbon"}, headers=alice).json()
    assert [n["title"] for n in found] == ["Trip to Lisbon"]


def test_get_and_delete_a_note(client, login):
    alice = login("alice")
    note_id = client.post("/notes", json={"title": "Temp"}, headers=alice).json()["id"]
    assert client.get(f"/notes/{note_id}", headers=alice).json()["title"] == "Temp"
    assert client.delete(f"/notes/{note_id}", headers=alice).status_code == 204
    assert client.get(f"/notes/{note_id}", headers=alice).status_code == 404


def test_share_a_note(client, login):
    alice, bob = login("alice"), login("bob")
    note_id = client.post("/notes", json={"title": "Plan"}, headers=alice).json()["id"]
    assert client.post(f"/notes/{note_id}/share", json={"username": "bob"}, headers=alice).status_code == 200
    assert [n["title"] for n in client.get("/notes", headers=bob).json()] == ["Plan"]


def test_recipient_cannot_delete_a_shared_note(client, login):
    alice, bob = login("alice"), login("bob")
    note_id = client.post("/notes", json={"title": "Plan"}, headers=alice).json()["id"]
    client.post(f"/notes/{note_id}/share", json={"username": "bob"}, headers=alice)
    client.delete(f"/notes/{note_id}", headers=bob)
    assert client.get(f"/notes/{note_id}", headers=alice).status_code == 200
