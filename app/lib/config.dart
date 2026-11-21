/// Settings read at build time from app/.env (`flutter run --dart-define-from-file=.env`), so the backend can move
/// without a code change. Copy .env.example to .env to set them.
class Config {
  /// The Loop Runner backend.
  static const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://localhost:8000');

  /// Supabase login. Left empty, the app runs anonymously, which matches a local backend with ALLOW_ANONYMOUS=true.
  static const supabaseUrl = String.fromEnvironment('SUPABASE_URL');
  static const supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

  static bool get loginEnabled => supabaseUrl.isNotEmpty && supabaseAnonKey.isNotEmpty;

  /// The WebSocket base for the same backend (http -> ws, https -> wss).
  static String get wsUrl => apiUrl.replaceFirst(RegExp(r'^http'), 'ws');
}
