from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field
import json


class Session(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: Optional[str] = None          # Supabase user UUID (None = unauthenticated/local)
    name: str
    repo_path: str
    status: str = "running"  # running | passed | failed | stopped
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    total_iterations: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    max_iterations: int = 10
    model: str = "claude-sonnet-4-6"
    verify_command: str


class Task(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id")
    title: str
    spec: str
    files_context: str = "[]"  # JSON array stored as string
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def get_files_context(self) -> list[str]:
        return json.loads(self.files_context)

    def set_files_context(self, files: list[str]):
        self.files_context = json.dumps(files)


class Iteration(SQLModel, table=True):
    id: str = Field(primary_key=True)
    session_id: str = Field(foreign_key="session.id")
    iteration_number: int
    status: str = "running"  # running | passed | failed
    agent_output: str = ""
    files_changed: str = "[]"  # JSON array
    verify_output: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    duration_seconds: float = 0.0
    git_commit_hash: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None

    def get_files_changed(self) -> list[str]:
        return json.loads(self.files_changed)


class ApiKey(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: str                           # Supabase user UUID
    provider: str                          # anthropic | openai | google | mistral
    encrypted_key: str
    label: str = ""                        # user-friendly nickname
    created_at: datetime = Field(default_factory=datetime.utcnow)


class UsageEvent(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: str
    session_id: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    byok: bool = False                     # True = user's own key (no billing)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SessionEvent(SQLModel, table=True):
    """What the agent did, kept so the visual view survives a page reload."""
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    kind: str                              # focus | tool | file_changed
    data: str = "{}"                       # JSON
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatSession(SQLModel, table=True):
    id: str = Field(primary_key=True)
    user_id: Optional[str] = None
    name: str
    repo_path: str
    verify_command: str
    model: str = "claude-sonnet-4-6"
    max_iterations: int = 10
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatMessage(SQLModel, table=True):
    id: str = Field(primary_key=True)
    chat_session_id: str = Field(foreign_key="chatsession.id")
    prompt: str
    status: str = "running"  # running | passed | failed
    loop_session_id: Optional[str] = None  # FK → Session (the underlying loop run)
    total_iterations: int = 0
    total_cost_usd: float = 0.0
    git_commit_hash: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class DeviceToken(SQLModel, table=True):
    """A phone or desktop that wants push notifications (core/notify.py). The token is the platform's (APNs or FCM)."""
    id: str = Field(primary_key=True)
    user_id: Optional[str] = None          # None = the local user (ALLOW_ANONYMOUS)
    platform: str                          # ios | android | macos
    token: str = Field(index=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
