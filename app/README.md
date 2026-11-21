# Loop Runner app

The desktop and mobile app for Loop Runner, in Flutter: sessions list and one session live. The plan is in
`../flutter-apps-plan.md`.

```bash
cp .env.example .env          # API_URL, and Supabase settings to log in (empty = anonymous local backend)
flutter run -d macos --dart-define-from-file=.env
flutter test
```

`API_URL` defaults to `http://localhost:8000`. Change it in `.env` and run again; nothing in the code needs to change.
