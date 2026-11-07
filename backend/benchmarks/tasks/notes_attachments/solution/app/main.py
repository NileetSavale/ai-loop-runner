import sqlite3
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.auth import check_password, hash_password, make_token, read_token
from app.db import connect, init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="TeamNotes", lifespan=lifespan)


class Credentials(BaseModel):
    username: str
    password: str


class NoteIn(BaseModel):
    title: str
    body: str = ""


def current_user(authorization: str = Header(default="")) -> int:
    user_id = read_token(authorization.removeprefix("Bearer "))
    if user_id is None:
        raise HTTPException(401, "Not logged in")
    return user_id


@app.post("/register", status_code=201)
def register(creds: Credentials):
    try:
        with connect() as conn:
            conn.execute(
                "INSERT INTO users (username, password_hash) VALUES (?, ?)",
                (creds.username, hash_password(creds.password)),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(409, "Username taken")
    return {"username": creds.username}


@app.post("/login")
def login(creds: Credentials):
    with connect() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (creds.username,)).fetchone()
    if not user or not check_password(creds.password, user["password_hash"]):
        raise HTTPException(401, "Wrong username or password")
    return {"token": make_token(user["id"])}


@app.post("/notes", status_code=201)
def create_note(note: NoteIn, user_id: int = Depends(current_user)):
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO notes (owner_id, title, body) VALUES (?, ?, ?)", (user_id, note.title, note.body)
        )
    return {"id": cur.lastrowid, "title": note.title, "body": note.body}


@app.get("/notes")
def list_notes(user_id: int = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE owner_id = ? OR id IN (SELECT note_id FROM shares WHERE user_id = ?) ORDER BY id",
            (user_id, user_id),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/notes/search")
def search_notes(q: str, user_id: int = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM notes WHERE owner_id = ? AND title LIKE ? ORDER BY id", (user_id, f"%{q}%")
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/notes/{note_id}")
def get_note(note_id: int, user_id: int = Depends(current_user)):
    with connect() as conn:
        note = conn.execute(
            "SELECT * FROM notes WHERE id = ? AND (owner_id = ? OR id IN (SELECT note_id FROM shares WHERE user_id = ?))",
            (note_id, user_id, user_id),
        ).fetchone()
    if not note:
        raise HTTPException(404, "Note not found")
    return dict(note)


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user_id: int = Depends(current_user)):
    with connect() as conn:
        conn.execute("DELETE FROM shares WHERE note_id IN (SELECT id FROM notes WHERE id = ? AND owner_id = ?)", (note_id, user_id))
        deleted = conn.execute("DELETE FROM notes WHERE id = ? AND owner_id = ?", (note_id, user_id)).rowcount
    if not deleted:
        raise HTTPException(404, "Note not found")


class ShareIn(BaseModel):
    username: str


@app.post("/notes/{note_id}/share")
def share_note(note_id: int, share: ShareIn, user_id: int = Depends(current_user)):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM notes WHERE id = ? AND owner_id = ?", (note_id, user_id)).fetchone():
            raise HTTPException(404, "Note not found")
        other = conn.execute("SELECT id FROM users WHERE username = ?", (share.username,)).fetchone()
        if not other:
            raise HTTPException(404, "User not found")
        conn.execute("INSERT OR IGNORE INTO shares (note_id, user_id) VALUES (?, ?)", (note_id, other["id"]))
    return {"shared_with": share.username}


import os


class AttachmentIn(BaseModel):
    filename: str
    content: str


def _note_folder(note_id: int) -> str:
    return os.path.join(os.path.realpath(os.environ.get("NOTES_FILES", "attachments")), str(note_id))


def _safe_name(filename: str) -> str:
    if not filename or filename != os.path.basename(filename) or filename.startswith("."):
        raise HTTPException(400, "Invalid filename")
    return filename


@app.post("/notes/{note_id}/attachments", status_code=201)
def upload_attachment(note_id: int, att: AttachmentIn, user_id: int = Depends(current_user)):
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM notes WHERE id = ? AND owner_id = ?", (note_id, user_id)).fetchone():
            raise HTTPException(404, "Note not found")
    folder = _note_folder(note_id)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, _safe_name(att.filename)), "w") as f:
        f.write(att.content)
    return {"filename": att.filename}


@app.get("/notes/{note_id}/attachments")
def list_attachments(note_id: int, user_id: int = Depends(current_user)):
    get_note(note_id, user_id)
    folder = _note_folder(note_id)
    return sorted(os.listdir(folder)) if os.path.isdir(folder) else []


@app.get("/notes/{note_id}/attachments/{filename}")
def read_attachment(note_id: int, filename: str, user_id: int = Depends(current_user)):
    get_note(note_id, user_id)
    path = os.path.join(_note_folder(note_id), _safe_name(filename))
    if not os.path.isfile(path):
        raise HTTPException(404, "Attachment not found")
    with open(path) as f:
        return {"filename": filename, "content": f.read()}
