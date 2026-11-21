import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'api.dart';
import 'config.dart';
import 'screens/login_screen.dart';
import 'screens/session_screen.dart';
import 'screens/sessions_screen.dart';

final apiProvider = Provider<Api>((ref) => Api());

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  if (Config.loginEnabled) {
    await Supabase.initialize(url: Config.supabaseUrl, publishableKey: Config.supabaseAnonKey);
  }
  runApp(const ProviderScope(child: LoopRunnerApp()));
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
    GoRoute(
      path: '/sessions',
      builder: (_, _) => const SessionsScreen(),
      routes: [
        GoRoute(path: ':id', builder: (_, state) => SessionScreen(id: state.pathParameters['id']!)),
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
