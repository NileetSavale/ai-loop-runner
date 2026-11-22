# Loop Runner app

The desktop and mobile app for Loop Runner, in Flutter: start a session (a folder on this machine or a GitHub repo),
watch it live, stop or delete it, read its changes, and manage API keys. The plan is in `../flutter-apps-plan.md`.

```bash
cp .env.example .env          # API_URL, and Supabase settings to log in (empty = anonymous local backend)
flutter run -d macos --dart-define-from-file=.env
flutter test

# The whole flow in the real app, against a running backend in local mode:
flutter test integration_test -d macos --dart-define-from-file=.env --dart-define=REPO=/path/to/a/git/repo
```

CI (`.github/workflows/app.yml`) analyzes, tests and builds the macOS, Windows and Linux apps on every change here.

`API_URL` defaults to `http://localhost:8000`. Change it in `.env` and run again; nothing in the code needs to change.
