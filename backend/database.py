from sqlmodel import SQLModel, create_engine, Session as DBSession
from contextlib import contextmanager
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./loop_runner.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db():
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session():
    with DBSession(engine) as session:
        yield session
