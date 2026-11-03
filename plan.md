# Loop Runner — SaaS Build Plan

## Completed
- [x] Core Ralph Wiggum loop (agent → verifier → commit/retry)
- [x] Loop reliability: exception handling, cancellation, verifier output fed into retry prompt
- [x] Multi-LLM provider abstraction (Anthropic, OpenAI, Gemini, Mistral)
- [x] Supabase JWT auth (get_current_user / get_optional_user)
- [x] BYOK API key vault (Fernet AES-256, encrypted at rest)
- [x] Test generation agent with stack auto-detection
- [x] Chat interface (multi-turn, WebSocket streaming)
- [x] Analytics endpoints with Redis caching + invalidation
- [x] WebSocket fan-out via Redis pub/sub (multi-pod safe)
- [x] Docker Compose local dev stack
- [x] Kubernetes production manifests (backend, frontend, postgres, redis, ingress, RBAC, HPA)
- [x] GitHub Actions CI/CD (test → build+push GHCR → kubectl deploy)

## Pending

- [x] **Multi-tenancy enforcement on sessions API** — scoped `GET /sessions` to authenticated user, added `_own_session` ownership guard on all `{session_id}` endpoints; added `model` and `max_iterations` validators on `SessionCreate`.
- [x] Fix `task.title` detached-instance access in `core/loop.py` — copied to `task_title` local before DB session closes.
- [x] `WsMessage` frontend type is incomplete — missing `"agent_token"` and `"cancelled"` events emitted by the backend.
- [x] `UsageEvent` recording — written atomically with each `Iteration` in the loop; skipped for unauthenticated sessions; `byok` flag set when user supplies their own key. Added `GET /analytics/usage` endpoint (auth-gated, scoped to calling user, max 1000 rows).
- [x] Input validation — Pydantic models on `SessionCreate` don't validate `model` string against `SUPPORTED_MODELS`; invalid model silently fails at loop start.
- [x] Rate limiting — Redis fixed-window middleware in `ratelimit.py`, per verified user or client IP: 10/min on routes that start a loop or call an LLM, 120/min on everything else. Override with `RATE_LIMIT_EXPENSIVE_PER_MINUTE` / `RATE_LIMIT_PER_MINUTE`.
- [x] Login required by default on every route and WebSocket, with `ALLOW_ANONYMOUS=true` for local development. Chat and analytics scoped to their owner. Private beta allowlist via `ALLOWED_USER_IDS`.
- [x] Production routing: `/api` rewrite in the ingress, `NEXT_PUBLIC_*` passed at image build, server-rendered pages send the user's token over `INTERNAL_API_URL`.
- [ ] Sandbox loop execution. Loops run inside the backend process, because `core/k8s_loop.py` isn't called and `core/loop_worker` doesn't exist. Required before removing the allowlist.
- [ ] Postgres support: no driver in `requirements.txt`, and `check_same_thread` in `database.py` is SQLite-only.
