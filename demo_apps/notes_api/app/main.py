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
        rows = conn.execute("SELECT * FROM notes WHERE owner_id = ? ORDER BY id", (user_id,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/notes/search")
def search_notes(q: str, user_id: int = Depends(current_user)):
    with connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM notes WHERE owner_id = {user_id} AND title LIKE '%{q}%' ORDER BY id"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/notes/{note_id}")
def get_note(note_id: int, user_id: int = Depends(current_user)):
    with connect() as conn:
        note = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
    if not note:
        raise HTTPException(404, "Note not found")
    return dict(note)


@app.delete("/notes/{note_id}", status_code=204)
def delete_note(note_id: int, user_id: int = Depends(current_user)):
    with connect() as conn:
        deleted = conn.execute("DELETE FROM notes WHERE id = ?", (note_id,)).rowcount
    if not deleted:
        raise HTTPException(404, "Note not found")
