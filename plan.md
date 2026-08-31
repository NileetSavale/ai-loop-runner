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
- [ ] `WsMessage` frontend type is incomplete — missing `"agent_token"` and `"cancelled"` events emitted by the backend.
- [x] `UsageEvent` recording — written atomically with each `Iteration` in the loop; skipped for unauthenticated sessions; `byok` flag set when user supplies their own key. Added `GET /analytics/usage` endpoint (auth-gated, scoped to calling user, max 1000 rows).
- [ ] Input validation — Pydantic models on `SessionCreate` don't validate `model` string against `SUPPORTED_MODELS`; invalid model silently fails at loop start.
- [ ] Rate limiting — no per-user request rate limiting on any endpoint.
