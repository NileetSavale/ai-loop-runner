"""The feature the team is asked to build. Hidden from the agents."""


def note(client, headers, title="Plan"):
    return client.post("/notes", json={"title": title}, headers=headers).json()["id"]


def upload(client, note_id, filename, content, headers):
    return client.post(f"/notes/{note_id}/attachments", json={"filename": filename, "content": content}, headers=headers)


def test_upload_read_and_list(client, login):
    alice = login("alice")
    n = note(client, alice)
    assert upload(client, n, "agenda.txt", "1. budget", alice).status_code == 201
    got = client.get(f"/notes/{n}/attachments/agenda.txt", headers=alice).json()
    assert got["content"] == "1. budget" and got["filename"] == "agenda.txt"
    assert "agenda.txt" in client.get(f"/notes/{n}/attachments", headers=alice).text


def test_missing_attachment_is_404(client, login):
    alice = login("alice")
    n = note(client, alice)
    assert client.get(f"/notes/{n}/attachments/nope.txt", headers=alice).status_code == 404


def test_shared_user_can_read_but_not_upload(client, login):
    alice, bob = login("alice"), login("bob")
    n = note(client, alice)
    upload(client, n, "agenda.txt", "1. budget", alice)
    client.post(f"/notes/{n}/share", json={"username": "bob"}, headers=alice)
    assert client.get(f"/notes/{n}/attachments/agenda.txt", headers=bob).json()["content"] == "1. budget"
    assert upload(client, n, "mine.txt", "x", bob).status_code in (403, 404)


def test_files_are_stored_under_notes_files(client, login, tmp_path):
    alice = login("alice")
    upload(client, note(client, alice), "agenda.txt", "1. budget", alice)
    assert any(p.name == "agenda.txt" for p in (tmp_path / "files").rglob("*"))
