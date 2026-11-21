# Loop Runner apps: desktop, mobile and web from one Flutter codebase

Status: plan, 2026-11-21. Nothing built yet.

## What this covers

The **user portal** only: what a developer uses to start agent sessions, watch them, and review the fixes. The
admin portal (TaskQ's UI, `docker compose --profile queue`) stays an internal web page for the operator.

| Surface | Built with | Why |
|---|---|---|
| Desktop app (macOS first, then Windows, Linux) | Flutter | Can open a folder on the user's machine and run agents on it, which a website can't |
| Mobile app (iOS, Android) | Flutter, same code | Watch sessions, get notified when one ends, approve or reject a flagged fix |
| Website | Next.js (today's `frontend/`), unchanged | Public pages need fast loading and search indexing, which Flutter web is poor at |

Flutter over React Native: the owner has shipped several Flutter apps (Stamp'd, flashcards, the carpooling app with
Riverpod and go_router) and no React Native app; React Native's desktop support (Microsoft's macOS/Windows ports)
is also less mature than Flutter's.

## What the backend already gives us

- Auth: Supabase. REST calls send `Authorization: Bearer <access token>`; the live WebSocket
  (`/ws/sessions/{id}`) takes the token as its first message. `supabase_flutter` provides the token, so **no auth
  change is needed**.
- Endpoints the apps need exist: `GET/POST /sessions`, `GET /sessions/{id}` (+ `/events`, `/iterations`, `/diff`,
  `/map`), `POST /sessions/{id}/stop`, `DELETE /sessions/{id}`, `/models`, `/keys`, `/analytics/*`.
- FastAPI publishes `/openapi.json`, so a typed Dart client can be generated instead of hand-written.

Gaps:
1. Some routes return untyped dicts, so the generated client would have loose types. Add response models for the
   routes the apps use (sessions, events, iterations).
2. Hosted mode clones a repo URL; a local folder only works when the backend runs on the same machine. The desktop
   app's local-folder mode needs a backend on that machine (phase 3).
3. Push notifications need a device-token endpoint and a sender (phase 2).

## Layout

`app/` in this monorepo, beside `frontend/` and `backend/`. Riverpod for state, go_router for navigation (as in the
carpooling app), the generated API client in `app/lib/api/`, a WebSocket client that reconnects and replays missed
events from `GET /sessions/{id}/events` (the page already merges saved and live events by id).

## Phases

Each phase ends with something usable and a check that it works.

**Phase 0: desktop viewer (about 3 days)**
- Flutter project, macOS target, login with Supabase.
- Sessions list; one session live: steps, attempts, test output, cost, the cascade's steps.
- Done when: a session started on the website can be watched live in the macOS app, and survives a reconnect.

**Phase 1: desktop does the work (about 1 week)**
- New session (repo URL, model, cascade or a pipeline), Stop, Delete, the diff view, API keys.
- Windows and Linux builds in CI (GitHub Actions has macOS, Windows and Linux runners).
- Done when: a full session can be run from the app without the website, on all three desktops.

**Phase 2: mobile (about 1 week)**
- iOS and Android builds of the same app, with layouts for a phone: list, live view, diff.
- Push notification when a session ends: backend stores device tokens and sends on `session_complete`
  (Firebase Cloud Messaging covers both platforms; its free tier is enough to start).
- Approve or reject a flagged fix from the phone. This needs an "approve" step kind in the pipeline format
  (`backend/pipelines/`), which waits for a person; TaskQ's `wait_signal` is built for exactly that wait.
- Done when: a phone gets a notification for a finished session and can approve a fix the reviewer flagged.

**Phase 3: desktop local mode, and releases (1-2 weeks)**
- The desktop app runs agents on a local folder: it starts a local backend (Docker Compose, or a packaged binary)
  and talks to it instead of the hosted one.
- Signed releases: Apple Developer Program (USD 99 a year) for macOS and iOS, Google Play (USD 25 once), a code-signing
  certificate for Windows. These cost money, so each one waits for an explicit yes.

## Risks

- Two web frontends: Flutter can build for the web too, but this plan keeps Next.js as the website to avoid
  maintaining both. Revisit only if the Next.js app falls behind the Flutter one.
- Packaging the Python backend for desktop local mode is the hardest part; Docker Compose is the fallback.
- Mobile WebSockets drop when the app is backgrounded; the replay from `/events` covers the gap, and push covers the
  end of a session.

## Decisions needed before phase 0

1. Which backend URL the apps use by default: a hosted one (where?) or `localhost:8000` for now.
2. Whether desktop local mode (phase 3) is wanted, since it shapes how the desktop app picks a repo.
3. Whether to pay for the Apple Developer Program now or develop unsigned until phase 3.
