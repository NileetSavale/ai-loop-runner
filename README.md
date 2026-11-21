# Loop Runner

**An autonomous AI coding agent that writes code, runs your tests, learns from failures, and commits when it passes — all in a real-time web UI.**

> **Research:** *When Tests Lie: Cascades, Reviewers and Failure Attribution in Coding Agents* uses Loop Runner on
> 436 SWE-bench Verified bugs. Browse every bug, run, review and label in the
> [interactive explorer](https://nileetsavale.github.io/ai-loop-runner/).

Loop Runner is a full-stack SaaS platform built around a deceptively simple idea: what if you could point an LLM at a failing test suite and have it keep rewriting code until the tests go green? No human in the loop. No copy-pasting from a chat window. Just a tight agent → verify → retry cycle, streaming live to your browser.

---

## The Concept

Most AI coding tools are glorified autocomplete — you still have to read the suggestion, judge it, apply it, run your tests, paste the errors back, and repeat. That loop is manual, slow, and interruptible.

Loop Runner automates the entire cycle:

```
┌─────────────────────────────────────────────────────────────┐
│                     THE AGENT LOOP                          │
│                                                             │
│   You give it:                                              │
│   • A repo path on disk                                     │
│   • A task description ("implement a rate limiter")         │
│   • A verify command ("pytest tests/ -v")                   │
│   • Which LLM to use (Claude, GPT-4o, Gemini, Mistral)     │
│                                                             │
│   Then it runs:                                             │
│                                                             │
│   ┌──────────┐    code     ┌──────────┐   exit 0   ┌─────┐ │
│   │  Agent   │ ──────────► │ Verifier │ ──────────► │ Git │ │
│   │  (LLM)   │             │  (your   │             │commit│ │
│   └──────────┘             │  tests)  │             └─────┘ │
│        ▲                   └──────────┘                     │
│        │                        │ exit 1                    │
│        └────────────────────────┘                           │
│              error output injected into next prompt         │
│                                                             │
│   Repeats up to N iterations. Commits on first green run.   │
└─────────────────────────────────────────────────────────────┘
```

The key insight is **error injection**: when the verifier fails, the full stdout/stderr — the actual test failure output — is fed verbatim into the next iteration's prompt as context. The model sees exactly what broke and why, which is far more useful than a generic "fix the code" instruction. This mimics what a developer actually does when tests fail: read the error, understand it, fix it.

Every token the LLM produces streams live to your browser over WebSocket. You watch the agent think in real time.

---

## Features

### Core Loop Engine
- **Iterative agent-verifier cycle** — LLM writes code, tests verify it, failure output feeds the next attempt
- **Error injection** — raw test output (including stack traces and assertion diffs) is embedded in the retry prompt, not summarized
- **Configurable iteration cap** — set 1–50 max attempts per session
- **Auto-commit on pass** — successful runs are committed to the target repo via GitPython with a structured commit message
- **Graceful cancellation** — stop a running session at any time; the in-flight asyncio task is cancelled cleanly and status is persisted

### Multi-LLM Provider Support
- **4 providers out of the box**: Anthropic (Claude), OpenAI (GPT-4o), Google (Gemini), Mistral
- **Unified provider interface** — all providers implement the same abstract `LLMProvider` base class; swapping models requires no loop logic changes
- **Token-level streaming** — every provider streams tokens as they arrive, forwarded live to the browser
- **Per-model cost tracking** — exact USD cost calculated per iteration using real provider pricing tables

### Bring Your Own Key (BYOK)
- Users can register their own API keys for any provider in the Settings page
- Keys are **encrypted at rest with AES-256 (Fernet)** before hitting the database — never stored in plaintext
- If no user key is present, the platform's own provider keys are used as fallback
- Usage events are flagged `byok: true/false` for accurate billing attribution

### Test Generation Agent
- **Describe a feature in plain English** → the agent generates a complete, runnable test suite
- Auto-detects your tech stack (Python/pytest, TypeScript/Vitest, Go testing, Rust, Ruby/RSpec, Java/JUnit) by scanning the repo for marker files
- Reads existing tests in your repo and matches their style
- Outputs both test files ready to write to disk and an `implementation_spec` — a precise natural-language spec for the coding agent
- The generated tests start failing (they define a feature that doesn't exist yet) and are designed to pass only when the implementation is fully correct
- Feeds directly into a Loop Runner session: generate tests → run loop → watch it implement the feature

### Real-Time WebSocket Streaming
- Every event (iteration start, agent token, verify output, completion) is pushed over WebSocket the moment it happens
- Redis pub/sub fan-out makes this **horizontally scalable** — a WebSocket connection on pod A receives events from a loop running on pod B
- Chat interface for multi-turn conversation with the agent inside a session

### Multi-Tenancy & Auth
- **Supabase JWT authentication** — stateless, no DB roundtrip per request; tokens verified locally with `HS256`
- Sessions are scoped to their owner — authenticated users can only see and modify their own sessions (returns 404, not 403, to avoid information leakage)
- Login required by default, plus a private beta allowlist (`ALLOWED_USER_IDS`). Set `ALLOW_ANONYMOUS=true` for local development only
- All `{session_id}` endpoints enforce ownership before any operation

### Analytics Dashboard
- **Summary metrics**: total sessions, pass rate, average iterations to pass, total cost, "correction tax" (avg extra iterations beyond 1)
- **Cost over time**: daily spend aggregated across all sessions
- **Iteration distribution**: histogram of how many attempts sessions typically need
- **Success/fail/stopped breakdown** and top-10 most expensive sessions
- **Per-user usage ledger**: full audit trail of every LLM call, token counts, cost, provider, and BYOK flag
- All analytics endpoints are **Redis-cached** with 60-second TTL and invalidated automatically when a session completes

### Infrastructure
- **Docker Compose** for zero-config local development (backend + frontend + Redis)
- **Full Kubernetes production manifests** — Deployments, Jobs, HPA, PVC, ConfigMap, Secrets, RBAC, Namespace, Ingress
- **Kubernetes Job-per-session isolation** — in production, each loop run spawns a dedicated pod with defined resource limits (512Mi–2Gi RAM, 0.5–2 CPU), preventing one heavy session from starving others
- **GitHub Actions CI/CD** — parallel test/typecheck → Docker Buildx build → push to GHCR with SHA-pinned tags → `kubectl set image` deploy with rollout wait

---

## Tech Stack

### Backend
| | |
|---|---|
| **Language** | Python 3.12 |
| **Web framework** | FastAPI (REST API + native WebSocket) |
| **ORM** | SQLModel (Pydantic + SQLAlchemy unified) |
| **Database** | SQLite (dev) / PostgreSQL (prod) |
| **Cache / Pub-Sub** | Redis (`redis-py` async) |
| **Encryption** | `cryptography` — Fernet / AES-256-CBC + HMAC |
| **Auth** | PyJWT — Supabase JWT validation (HS256) |
| **Git integration** | GitPython — auto-commit on verified pass |
| **LLM SDKs** | `anthropic`, `openai`, `google-genai`, `mistralai` |
| **HTTP client** | `httpx` (async) |
| **Server** | Uvicorn with standard extras |
| **K8s client** | `kubernetes` (Python SDK) |

### Frontend
| | |
|---|---|
| **Framework** | Next.js 14 (App Router) |
| **Language** | TypeScript 5 |
| **Styling** | Tailwind CSS |
| **Charts** | Recharts |
| **Server state** | TanStack React Query v5 |
| **Client state** | Zustand v4 |
| **Auth** | `@supabase/supabase-js` + `@supabase/ssr` |

### Infrastructure
| | |
|---|---|
| **Containerization** | Docker + Docker Compose |
| **Orchestration** | Kubernetes (k8s manifests included) |
| **Container registry** | GitHub Container Registry (GHCR) |
| **Ingress** | nginx-ingress (WebSocket proxy, 1-hour timeout) |
| **TLS** | cert-manager + Let's Encrypt |
| **CI/CD** | GitHub Actions |

---

## Architecture

```
┌────────────────────────────────────────────────────────────────┐
│                        Browser                                 │
│  Next.js 14 · TypeScript · Tailwind · React Query · Zustand   │
│         WebSocket (token stream)    REST (sessions/analytics)  │
└───────────────────────┬────────────────────────┬──────────────┘
                        │                        │
                        ▼                        ▼
┌───────────────────────────────────────────────────────────────┐
│                    FastAPI Backend                            │
│                                                               │
│  /sessions ──► core/loop.py ──► core/agent.py                │
│                    │                  │                       │
│                    │           providers/router.py            │
│                    │          /anthropic /openai              │
│                    │          /gemini   /mistral              │
│                    │                                          │
│                    ├──► core/verifier.py (subprocess)         │
│                    ├──► core/git_ops.py  (GitPython)          │
│                    └──► routes/ws.py ──► Redis pub/sub        │
│                                                               │
│  /analytics  ──► Redis cache ──► SQLite / PostgreSQL          │
│  /keys       ──► vault.py (Fernet AES-256)                   │
│  /test-gen   ──► agents/test_gen.py                           │
│  /chat       ──► multi-turn WebSocket chat sessions           │
└───────────────────────┬────────────────────────┬──────────────┘
                        │                        │
               ┌────────▼──────┐      ┌──────────▼────────┐
               │     Redis     │      │  SQLite/PostgreSQL │
               │  pub/sub +    │      │  Sessions, Tasks,  │
               │  analytics    │      │  Iterations,       │
               │  cache        │      │  UsageEvents,      │
               └───────────────┘      │  ApiKeys           │
                                      └───────────────────┘

Production:
┌──────────────────────────────────────────────────────┐
│                   Kubernetes                         │
│                                                      │
│  nginx-ingress (TLS termination, WS proxy)           │
│       │                                              │
│  ┌────┴────┐    ┌──────────┐    ┌─────────────────┐ │
│  │Frontend │    │ Backend  │    │  Loop Job (pod)  │ │
│  │Deployment│   │Deployment│    │  per session     │ │
│  │  HPA    │    │   HPA    │    │  isolated, 2Gi   │ │
│  └─────────┘    └──────────┘    └─────────────────┘ │
│                                                      │
│  PostgreSQL StatefulSet · Redis StatefulSet · PVC    │
└──────────────────────────────────────────────────────┘
```

### How the Agent Loop Works (Code Level)

1. `POST /sessions` — creates a `Session` + `Task` record, calls `start_loop()`
2. `core/loop.py` spawns an `asyncio.Task`; in production, `core/k8s_loop.py` spawns a Kubernetes Job instead
3. Each iteration:
   - Reads target files from disk and builds a context block
   - Constructs the prompt: task spec + file contents + (if retry) the raw verifier error output from the last attempt
   - Calls `core/agent.py` → `providers/router.py` → the correct SDK → streams tokens back through a callback
   - Parses `<file path="...">...</file>` blocks from the LLM response and writes them to disk
   - Runs the verify command as a subprocess via `core/verifier.py` with a configurable timeout
   - If exit code 0: calls `core/git_ops.py` to commit, broadcasts `session_complete`, writes `UsageEvent`
   - If exit code ≠ 0: stores `verify_output` as `last_verify_output`, increments iteration, loops
4. All events are published to Redis (`ws:{session_id}` channel); the WebSocket handler on any pod subscribes and forwards to the browser

---

## Project Structure

```
loop_runner/
├── backend/
│   ├── main.py               # FastAPI app, router registration
│   ├── models.py             # SQLModel table definitions
│   ├── database.py           # Session factory
│   ├── auth.py               # Supabase JWT validation
│   ├── cache.py              # Shared async Redis client
│   ├── vault.py              # Fernet AES-256 encrypt/decrypt
│   ├── core/
│   │   ├── loop.py           # The agent loop engine
│   │   ├── agent.py          # LLM call + file block parser
│   │   ├── verifier.py       # Subprocess runner + timeout
│   │   ├── git_ops.py        # GitPython auto-commit
│   │   └── k8s_loop.py       # Kubernetes Job submission (prod)
│   ├── providers/
│   │   ├── base.py           # Abstract LLMProvider + pricing
│   │   ├── router.py         # Model → provider routing + BYOK
│   │   ├── anthropic.py
│   │   ├── openai.py
│   │   ├── gemini.py
│   │   └── mistral.py
│   ├── agents/
│   │   └── test_gen.py       # Test generation agent
│   ├── routes/
│   │   ├── sessions.py       # CRUD + loop control
│   │   ├── ws.py             # WebSocket + Redis pub/sub
│   │   ├── analytics.py      # Cached analytics endpoints
│   │   ├── chat.py           # Multi-turn chat sessions
│   │   ├── keys.py           # BYOK key management
│   │   └── test_gen.py       # Test gen HTTP route
│   └── tests/                # pytest test suite
├── frontend/
│   ├── app/                  # Next.js App Router pages
│   │   ├── page.tsx          # Dashboard / session list
│   │   ├── new/              # Create session form
│   │   ├── sessions/[id]/    # Live session viewer
│   │   ├── analytics/        # Analytics dashboard
│   │   ├── chat/             # Chat interface
│   │   ├── generate/         # Test generation UI
│   │   └── settings/keys/    # BYOK key management
│   ├── components/           # Recharts charts, LiveLoop stream, etc.
│   └── lib/                  # API client, React Query hooks, Zustand store
├── k8s/                      # Kubernetes manifests
│   ├── backend/              # Deployment, Service, HPA, RBAC
│   ├── frontend/             # Deployment, Service
│   ├── postgres/             # StatefulSet, PVC, Service
│   ├── redis/                # StatefulSet, Service
│   ├── loop-job/             # Job template for prod loop execution
│   ├── ingress.yaml          # nginx-ingress with WebSocket headers
│   ├── configmap.yaml
│   └── secret.example.yaml
├── .github/workflows/
│   └── test.yml              # CI: test → build → push GHCR → deploy
└── docker-compose.yml        # Local dev stack
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- Node.js 20+
- Docker + Docker Compose
- A Supabase project (for auth)
- At least one LLM provider API key

### Local Development

**1. Clone and configure**

```bash
git clone https://github.com/NileetSavale/ai-loop-runner.git
cd ai-loop-runner
```

**2. Backend environment**

Copy `backend/.env.example` → `backend/.env` and fill in:

```env
DATABASE_URL=sqlite:///./loop_runner.db
REDIS_URL=redis://localhost:6379

# Supabase
SUPABASE_JWT_SECRET=your_supabase_jwt_secret

# Local development only: skip login and the allowlist. Never set this on a reachable server.
ALLOW_ANONYMOUS=true

# LLM keys (at least one required)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=...
MISTRAL_API_KEY=...

# BYOK vault key — generate with:
# python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
VAULT_KEY=...

# Verify timeout
MAX_VERIFY_TIMEOUT_SECONDS=120
```

**3. Frontend environment**

```env
# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
```

**4. Start everything with Docker Compose**

```bash
docker compose up
```

- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:8000`
- API docs: `http://localhost:8000/docs`

To run sessions on a separate worker instead of inside the API process, so a restart doesn't lose them, use the
[TaskQ](https://github.com/AZX-PBC-OSS/TaskQ) queue (`backend/jobs.py`):

```bash
LOOP_RUNNER_QUEUE=taskq docker compose --profile queue up
```

This adds Postgres for TaskQ's jobs, runs its migrations, and starts a worker plus TaskQ's admin UI at
`http://localhost:8080`, which shows every session's job, its attempts and progress, and the workers. Stop cancels the session's job. If a
worker dies mid-run, the session is marked failed with the reason rather than run again, since the run has already
changed the repo.

**5. Or run services individually**

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn main:app --reload

# Frontend
cd frontend
npm install
npm run dev
```

### Run it on your own repo

Everything runs on your machine and your own API keys; there is no shared server.

1. Start Redis (`docker run -d --rm -p 127.0.0.1:6379:6379 redis:7-alpine`), then the backend on the host with
   `ALLOW_ANONYMOUS=true` and your `ANTHROPIC_API_KEY` in `backend/.env`. Run the backend outside Docker Compose
   for GitHub sessions: their tests run in sandbox containers, which need the host's Docker.
2. Open **New Session** and pick either:
   - **GitHub repo**: a URL, an optional branch, and a token if it's private. The repo is cloned per session, its
     dependencies are installed into a container, and every test run happens in a container with no network.
     Supported now: npm projects with a `package-lock.json`, and Python projects (`pyproject.toml`, `setup.py` or
     `requirements*.txt`).
   - **Folder on this machine**: its checks run directly on your machine (the API's `sandbox: true` puts them in a
     container instead).
3. Tick **Try a cheap model first** to have Haiku try first, Sonnet review a passing fix, and your main model redo
   the task only if the fix fails or the review rejects it. It needs a Claude main model.
4. When the session ends, **Download changes (.diff)** gives you a `.diff` to apply with `git apply`.

**Cost limit (USD)** caps what a session spends. To let other people use your instance, set
`LOOP_RUNNER_HOSTED=1` and real auth (no `ALLOW_ANONYMOUS`): sessions then must come from GitHub, and each one
runs on its user's own key from Settings, never yours.

### Running Tests

```bash
cd backend
pip install -r requirements.txt pytest
pytest tests/ -v
```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/sessions` | Create a new session and start the loop |
| `GET` | `/sessions` | List sessions (scoped to current user) |
| `GET` | `/sessions/{id}` | Get session detail + all iterations |
| `POST` | `/sessions/{id}/stop` | Cancel a running loop |
| `DELETE` | `/sessions/{id}` | Delete session and all iterations |
| `GET` | `/sessions/{id}/iterations` | List iterations for a session |
| `WS` | `/ws/sessions/{id}` | Real-time event stream for a session |
| `WS` | `/ws/chat/{id}` | Real-time stream for a chat session |
| `GET` | `/analytics/summary` | Aggregate stats (cached) |
| `GET` | `/analytics/cost-over-time` | Daily cost breakdown (cached) |
| `GET` | `/analytics/iteration-distribution` | Histogram of iterations (cached) |
| `GET` | `/analytics/success-rate` | Pass/fail/stopped counts (cached) |
| `GET` | `/analytics/top-tasks` | Top 10 most expensive sessions (cached) |
| `GET` | `/analytics/usage` | Per-user usage ledger (auth required) |
| `POST` | `/keys` | Store an encrypted BYOK API key |
| `GET` | `/keys` | List stored keys (metadata only) |
| `DELETE` | `/keys/{id}` | Remove a stored key |
| `POST` | `/test-gen` | Generate a test suite from a description |
| `GET` | `/health` | Health check |

### WebSocket Events

The WebSocket stream for a session emits the following event types:

| Event | Payload | Description |
|---|---|---|
| `iteration_start` | `{ iteration: number }` | A new iteration has begun |
| `agent_token` | `{ token: string }` | A single streamed token from the LLM |
| `verify_output` | `{ output: string, passed: bool }` | Verifier finished, here's the output |
| `iteration_complete` | `{ id, iteration_number, status, cost_usd, ... }` | Iteration done (failed, retrying) |
| `session_complete` | `{ status, commit?, error? }` | Loop finished (passed/failed/cancelled) |
| `cancelled` | — | Session was stopped by the user |

---

## Kubernetes Deployment

All manifests are in `k8s/`. The stack in production:

- **Backend** — Deployment with HPA (autoscales on CPU), RBAC ServiceAccount for Job submission
- **Frontend** — Deployment with HPA
- **PostgreSQL** — StatefulSet with persistent storage
- **Redis** — StatefulSet
- **Loop Jobs** — each session spawns a dedicated Kubernetes Job (isolated pod, 512Mi–2Gi RAM, 0.5–2 CPU, auto-deleted after 10 minutes)
- **Ingress** — nginx with WebSocket upgrade headers and 1-hour proxy timeout for long-running loops
- **TLS** — cert-manager with Let's Encrypt

```bash
# Apply everything
kubectl apply -f k8s/ --recursive -n loop-runner

# Copy and fill in secrets
cp k8s/secret.example.yaml k8s/secret.yaml
# edit k8s/secret.yaml
kubectl apply -f k8s/secret.yaml -n loop-runner
```

Before deploying, set `ALLOWED_USER_IDS` in `k8s/configmap.yaml`; the API rejects everyone while it's empty. Also set the GitHub Actions variables `NEXT_PUBLIC_WS_URL` (`wss://your-host`), `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`, because they're compiled into the frontend image.

### CI/CD Pipeline

On every push to `main`:

1. **Test** — `pytest backend/tests/ -v` + `tsc --noEmit` (run in parallel)
2. **Build** — Docker Buildx multi-stage builds for backend and frontend, pushed to GHCR tagged with both `latest` and the commit SHA
3. **Deploy** — `kubectl set image` with the exact commit SHA tag (deterministic, rollback-safe), then `kubectl rollout status` waits for the rollout to complete

---

## Supported Models

| Provider | Model |
|---|---|
| Anthropic | Claude Sonnet 4.6, Claude Opus 4.8, Claude Haiku 4.5 |
| OpenAI | GPT-4o, GPT-4o Mini |
| Google | Gemini 1.5 Pro, Gemini 1.5 Flash |
| Mistral | Mistral Large, Mistral Small |

Models are validated at session creation time — an unsupported model string is rejected with a clear error before the loop starts.

---

## Design Decisions

**Why inject raw verifier output instead of summarizing it?**
The full stack trace, assertion diff, and line numbers are exactly what a developer reads when a test fails. Summarizing it loses precision. Feeding the raw output gives the model the same signal a human would act on.

**Why Redis pub/sub for WebSocket fan-out?**
With multiple backend pods, a WebSocket connection lands on whichever pod accepts it, but the loop might be running on a different pod. Redis pub/sub decouples them — any pod can publish events, any pod can forward them to its connected clients. This makes horizontal scaling transparent.

**Why Kubernetes Jobs instead of asyncio tasks in production?**
asyncio tasks share the process. One session with a runaway loop or a memory-hungry LLM response affects all others on that pod. A Kubernetes Job gets its own isolated pod with enforced resource limits. It also survives pod restarts and can be monitored independently.

**Why Fernet for BYOK key encryption?**
Fernet is AES-256-CBC + HMAC-SHA256 with built-in key rotation support. It's the standard symmetric encryption primitive in the Python `cryptography` library — audited, well-understood, and requires zero custom crypto code.

---

## License

MIT, see [LICENSE](LICENSE). The paper in `paper/` is not covered by it.
