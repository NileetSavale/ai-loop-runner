# Loop Runner apps: desktop, mobile and web from one Flutter codebase

Status, 2026-11-22: phases 0-2 built (branch `feat/flutter-app`); phase 3 and the next items below are planned.

## What this covers

The **user portal** only: what a developer uses to start agent sessions, watch them, and review the fixes. The
admin portal (TaskQ's UI, `docker compose --profile queue`) stays an internal web page for the operator.

| Surface | Built with | Why |
|---|---|---|
| Desktop app (macOS, Windows, Linux) | Flutter | Can open a folder on the user's machine and run agents on it, which a website can't |
| Mobile app (iOS; Android when an Android SDK is set up) | Flutter, same code | Watch sessions, get notified, approve or reject a fix |
| Website | Next.js (`frontend/`) | Public pages need fast loading and search indexing, which Flutter web is poor at |

Flutter over React Native: the owner has shipped several Flutter apps and no React Native app, and React Native's
desktop support is less mature.

## Decisions taken

- Local first: a fresh clone runs with only a model key. Supabase login is optional (bring your own project), and so
  is Redis (live events stay in the process without it).
- The apps read `API_URL` and the Supabase settings from `app/.env` (`--dart-define-from-file=.env`).
- Closed-app push is built but off until the paid Apple Developer Program; in-app notifications work now.

## Built

**Phase 0: desktop viewer.** Login, the sessions list, one session live with reconnect and replay.

**Phase 1: desktop does the work.** New session (a folder or a GitHub repo, model, pipeline), Stop, Delete, the diff,
API keys; macOS, Windows and Linux builds in CI.

**Desktop polish.** Sidebar and split view, native menus and shortcuts, list search and filters, attempts grouped by
step; pipelines as a live map; a pipeline editor (scout, fix, review, command and approve steps) with the map redrawn
as you edit.

**Phase 2: mobile.** Phone layouts; approve or reject a fix from the phone (the approve step); in-app notifications
when a session ends or waits for you; push registration ready for the paid account. Checked on the iPhone simulator
and on a real iPhone logged in through Supabase against the backend on a Mac over Wi-Fi.

## Next

1. **Repos on the backend's machine, for the phone.** A phone can't browse the Mac's folders. Add `GET /repos`: git
   repos under a folder the owner allows (`REPOS_DIR`) plus repos used in past sessions; logged-in users only, off on
   a hosted server. The phone picks from that list instead of typing a path.
2. **Unknown model names.** `providers/router.py` sends any model it doesn't recognise to Anthropic. Refuse an
   unknown model instead.
3. **Open-source and custom models.** Any OpenAI-compatible endpoint: Ollama (models found automatically when it
   runs on the backend's machine), LM Studio, llama.cpp, vLLM, and hosted ones (OpenRouter, Together, Groq).
   Endpoints are added like API keys (a name, a base URL, an optional key); local models cost $0. They run on the
   loop's whole-file path first, which works with any model; tool calling per model after. Measure how far a free
   coder model (Qwen2.5-Coder 14-32B) gets with the SWE-bench harness.
4. **Releases.** A Flutter fix or workaround for `flutter run --release` on iOS looking in `build/ios/iphoneos` while
   Xcode writes `build/ios/Release-iphoneos` (today: `xcrun devicectl device install app`).
5. **Database upgrades.** The backend creates missing tables but never adds columns, so an old `loop_runner.db` breaks
   on new fields (it happened with `session.user_id`). Add migrations, or at least a clear startup error.

**Phase 3: desktop local mode, and signed releases.** The desktop app starts a local backend (Docker Compose, or a
packaged binary) and runs agents on a local folder. Signed releases: Apple Developer Program (USD 99 a year) for
macOS and iOS push and distribution, Google Play (USD 25 once), a Windows code-signing certificate. Each waits for an
explicit yes.

## Risks

- Two web frontends: Flutter can build for the web too; this plan keeps Next.js as the website.
- Packaging the Python backend for desktop local mode is the hardest part; Docker Compose is the fallback.
- Mobile WebSockets drop in the background; the replay from `/events` and the 15-second request limit cover it, and
  push covers the end of a session once switched on.
- Small open models are much weaker at multi-step fixes than Claude or GPT; quote measured numbers, not hopes.
