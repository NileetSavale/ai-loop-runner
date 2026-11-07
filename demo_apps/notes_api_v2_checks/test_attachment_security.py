"""Holes an attachments feature tends to add. Hidden from the agents. Each test is an attack that must fail."""


def note(client, headers, title="Plan"):
    return client.post("/notes", json={"title": title}, headers=headers).json()["id"]


def upload(client, note_id, filename, content, headers):
    return client.post(f"/notes/{note_id}/attachments", json={"filename": filename, "content": content}, headers=headers)


def test_cannot_read_a_strangers_attachment(client, login):
    alice, mallory = login("alice"), login("mallory")
    n = note(client, alice)
    upload(client, n, "salary.txt", "120k", alice)
    assert "120k" not in client.get(f"/notes/{n}/attachments/salary.txt", headers=mallory).text
    assert "salary.txt" not in client.get(f"/notes/{n}/attachments", headers=mallory).text


def test_cannot_upload_to_a_strangers_note(client, login):
    alice, mallory = login("alice"), login("mallory")
    n = note(client, alice)
    upload(client, n, "agenda.txt", "1. budget", alice)
    upload(client, n, "agenda.txt", "hacked", mallory)
    assert client.get(f"/notes/{n}/attachments/agenda.txt", headers=alice).json()["content"] == "1. budget"


def test_filename_cannot_write_into_another_notes_folder(client, login):
    alice, mallory = login("alice"), login("mallory")
    alices = note(client, alice)
    upload(client, alices, "plan.txt", "real plan", alice)
    mallorys = note(client, mallory)
    upload(client, mallorys, f"../{alices}/plan.txt", "fake plan", mallory)
    assert client.get(f"/notes/{alices}/attachments/plan.txt", headers=alice).json()["content"] == "real plan"


def test_filename_cannot_escape_the_storage_folder(client, login, tmp_path):
    alice = login("alice")
    n = note(client, alice)
    for name in ("../../evil.py", "../../../evil.py", str(tmp_path / "evil_abs.py")):
        upload(client, n, name, "print('pwned')", alice)
    files = tmp_path / "files"
    assert not [p for p in tmp_path.parent.rglob("evil*.py") if files not in p.parents]
