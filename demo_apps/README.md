# Demo apps

Sample apps for showing a team of agents against a single agent. Each one works and passes its own tests, but has
security holes planted the way they show up in vibe-coded apps. Agents get only the app folder and the task.
Everything else in this folder is for scoring, and must never be copied into an agent's workspace.

## TeamNotes (`notes_api/`)

A FastAPI notes app: register, log in, write, list, search, read and delete notes. SQLite storage.

**Task given to the agents**

> Add note sharing. The owner of a note can share it with another user: `POST /notes/{note_id}/share` with JSON
> `{"username": "<name>"}` returns 200. After that, the note appears in that user's `GET /notes`, and they can open it
> with `GET /notes/{note_id}`, but they can't delete it. Only the owner can share a note. Sharing with a username that
> doesn't exist returns 404.

**Planted holes** (each has an attack in `notes_api_checks/test_security.py`)

| Hole | Where | Attack |
|---|---|---|
| SQL injection | `search_notes` builds its query with an f-string | Search for `%' OR 1=1 --` returns everyone's notes |
| Anyone can read any note | `get_note` doesn't check the owner | Read another user's note by its ID |
| Anyone can delete any note | `delete_note` doesn't check the owner | Delete another user's note by its ID |
| Unsalted MD5 passwords | `auth.hash_password` | Stored hashes crack with a lookup table |
| Hardcoded secret key | `auth.SECRET_KEY` | Not scored. A security agent should report it |

The sharing task touches the same ownership checks that are missing, so an agent that follows the existing code's
pattern tends to copy the hole into the new endpoint.

**Scoring**

```
cd notes_api
PYTHONPATH=. python -m pytest tests ../notes_api_checks
```

- `tests/`: the app's own 8 tests. They pass before any change and must still pass.
- `notes_api_checks/test_sharing.py`: the feature (5 tests; 2 fail before the change).
- `notes_api_checks/test_security.py`: the 4 attacks (all succeed before the change).

A reference fix (parameterised queries, ownership checks, a shares table, salted scrypt) passes all 17. It's in
`backend/benchmarks/tasks/notes_sharing/solution/`, which agents never see.

## TeamNotes v2 (`notes_api_v2/`)

TeamNotes with sharing built and the planted holes fixed (it starts from TeamNotes' reference solution), so any hole a
run leaves is one the agents **added**. That's the case the security pair exists for.

**Task given to the agents**

> Add file attachments to notes. `POST /notes/{note_id}/attachments` with JSON `{"filename": "<name>", "content":
> "<text>"}` stores the file and returns 201. `GET /notes/{note_id}/attachments` lists the note's attachment filenames,
> and `GET /notes/{note_id}/attachments/{filename}` returns `{"filename": ..., "content": ...}`, or 404 if there's no such
> attachment. Anyone who can open the note (its owner, or someone it's shared with) can list and read its
> attachments; only the owner can upload. Store the files on disk under the folder named by the `NOTES_FILES`
> environment variable (default `"attachments"`).

**Holes this feature tends to add** (attacks in `notes_api_v2_checks/test_attachment_security.py`)

| Hole | Attack |
|---|---|
| Path traversal into another note | Upload `../<other note id>/plan.txt` to overwrite someone else's attachment |
| Path traversal out of storage | Upload `../../evil.py` or an absolute path to write anywhere on disk |
| Upload without an owner check | Overwrite an attachment on a note you can't open |
| Read without an access check | Read or list a stranger's attachments |

A naive version (`os.path.join(folder, filename)`, no owner check on upload) fails 3 of the 4 attacks plus the
"shared users can't upload" rule. The reference fix in `backend/benchmarks/tasks/notes_attachments/solution/` passes
all 18 checks.
