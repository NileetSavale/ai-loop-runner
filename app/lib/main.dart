import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'api.dart';
import 'config.dart';
import 'notifications.dart';
import 'screens/diff_screen.dart';
import 'screens/keys_screen.dart';
import 'screens/login_screen.dart';
import 'screens/new_session_screen.dart';
import 'screens/pipeline_editor_screen.dart';
import 'screens/pipelines_screen.dart';
import 'screens/sessions_screen.dart';
import 'shell.dart';

final apiProvider = Provider<Api>((ref) => Api());

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (Config.loginEnabled) {
    await Supabase.initialize(url: Config.supabaseUrl, publishableKey: Config.supabaseAnonKey);
  }
  // The app's own notifications: a session that ends or waits for approval, tapped to open it
  await Notifications.init((id) => _router.go('/sessions/$id'));
  final container = ProviderContainer();
  final watcher = SessionWatcher(container.read(apiProvider));
  if (watchSessions(_signedIn)) watcher.start();
  if (Config.loginEnabled) {
    Supabase.instance.client.auth.onAuthStateChange.listen((_) => _signedIn ? watcher.start() : watcher.stop());
  }
  runApp(UncontrolledProviderScope(container: container, child: const LoopRunnerApp()));
}

/// Signed in, or anonymous when login is off: either way the sessions screens can call the backend.
bool get _signedIn => !Config.loginEnabled || Supabase.instance.client.auth.currentSession != null;

final _router = GoRouter(
  initialLocation: '/sessions',
  // Login or logout re-runs the redirect below
  refreshListenable: Config.loginEnabled ? _AuthChanges() : null,
  redirect: (context, state) {
    final atLogin = state.matchedLocation == '/login';
    if (!_signedIn) return atLogin ? null : '/login';
    return atLogin ? '/sessions' : null;
  },
  routes: [
    GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
    ShellRoute(
      builder: (_, state, child) => AppShell(location: state.matchedLocation, child: child),
      routes: [
        GoRoute(
          path: '/sessions',
          builder: (_, _) => const SessionsPage(),
          routes: [
            // Before :id, so "new" is not read as a session id
            GoRoute(path: 'new', builder: (_, _) => const NewSessionScreen()),
            GoRoute(
              path: ':id',
              builder: (_, state) => SessionsPage(selectedId: state.pathParameters['id']),
              routes: [
                GoRoute(
                  path: 'diff',
                  builder: (_, state) => DiffScreen(id: state.pathParameters['id']!),
                ),
              ],
            ),
          ],
        ),
        GoRoute(
          path: '/pipelines',
          builder: (_, state) =>
              PipelinesScreen(key: ValueKey(state.uri.query), initial: state.uri.queryParameters['name']),
          routes: [
            GoRoute(
              path: 'new',
              builder: (_, state) => PipelineEditorScreen(from: state.uri.queryParameters['from']),
            ),
            GoRoute(
              path: ':name/edit',
              builder: (_, state) => PipelineEditorScreen(from: state.pathParameters['name'], editing: true),
            ),
          ],
        ),
        GoRoute(path: '/keys', builder: (_, _) => const KeysScreen()),
      ],
    ),
  ],
);

class _AuthChanges extends ChangeNotifier {
  _AuthChanges() {
    Supabase.instance.client.auth.onAuthStateChange.listen((_) => notifyListeners());
  }
}

class LoopRunnerApp extends StatelessWidget {
  const LoopRunnerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Loop Runner',
      theme: ThemeData(colorSchemeSeed: Colors.indigo, useMaterial3: true),
      darkTheme: ThemeData(colorSchemeSeed: Colors.indigo, brightness: Brightness.dark, useMaterial3: true),
      routerConfig: _router,
    );
  }
}
