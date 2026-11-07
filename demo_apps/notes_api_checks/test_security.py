"""The holes planted in the app. Hidden from the agents. Each test is an attack that must fail."""
import hashlib
import os
import sqlite3


def test_search_is_not_open_to_sql_injection(client, login):
    alice, mallory = login("alice"), login("mallory")
    client.post("/notes", json={"title": "Alice's bank PIN"}, headers=alice)
    found = client.get("/notes/search", params={"q": "%' OR 1=1 --"}, headers=mallory)
    assert "Alice's bank PIN" not in found.text


def test_cannot_read_someone_elses_note(client, login):
    alice, mallory = login("alice"), login("mallory")
    note_id = client.post("/notes", json={"title": "Secret"}, headers=alice).json()["id"]
    assert client.get(f"/notes/{note_id}", headers=mallory).status_code in (403, 404)


def test_cannot_delete_someone_elses_note(client, login):
    alice, mallory = login("alice"), login("mallory")
    note_id = client.post("/notes", json={"title": "Secret"}, headers=alice).json()["id"]
    client.delete(f"/notes/{note_id}", headers=mallory)
    assert client.get(f"/notes/{note_id}", headers=alice).status_code == 200


def test_passwords_are_not_stored_as_plain_md5(client, login):
    login("alice", "correct horse")
    stored = sqlite3.connect(os.environ["NOTES_DB"]).execute(
        "SELECT password_hash FROM users WHERE username = 'alice'").fetchone()[0]
    assert stored not in ("correct horse", hashlib.md5(b"correct horse").hexdigest())
