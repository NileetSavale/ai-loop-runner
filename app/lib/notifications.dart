import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'api.dart';
import 'config.dart';
import 'models.dart';

/// A notification the app should raise: the session it is about, a title and a line of text.
typedef Alert = ({String sessionId, String title, String body});

/// What changed between two looks at the sessions list that deserves a notification: a running session that ended,
/// or one that started waiting for an approval. The first look only sets the baseline, so opening the app doesn't
/// replay old endings.
List<Alert> alertsBetween(Map<String, Session>? before, List<Session> now) {
  if (before == null) return const [];
  final alerts = <Alert>[];
  for (final s in now) {
    final was = before[s.id];
    final name = s.name.isEmpty ? 'A session' : s.name;
    if (was != null && was.running && !s.running) {
      alerts.add((sessionId: s.id, title: 'Session ${s.status}', body: name));
    }
    if (s.waitingFor != null && was?.waitingFor != s.waitingFor) {
      alerts.add((sessionId: s.id, title: 'Waiting for your approval', body: '$name: approve or reject the fix'));
    }
  }
  return alerts;
}

/// The app's own notifications: raised while it runs (open, or briefly in the background), with no cloud service.
/// Closed-app push is separate (push.dart) and waits for the paid Apple Developer Program.
class Notifications {
  static final _plugin = FlutterLocalNotificationsPlugin();
  static bool _ready = false;
  static int _next = 0;

  /// [onOpen] gets the session id when a notification is tapped.
  static Future<void> init(void Function(String sessionId) onOpen) async {
    if (kIsWeb) return;
    try {
      await _plugin.initialize(
        settings: const InitializationSettings(
          macOS: DarwinInitializationSettings(),
          iOS: DarwinInitializationSettings(),
          android: AndroidInitializationSettings('@mipmap/ic_launcher'),
          linux: LinuxInitializationSettings(defaultActionName: 'Open session'),
          windows: WindowsInitializationSettings(
            appName: 'Loop Runner',
            appUserModelId: 'com.looprunner.LoopRunner',
            guid: '6f0f5d37-9a7e-4c1e-8f61-3b2a9a4f1c52',
          ),
        ),
        onDidReceiveNotificationResponse: (response) {
          if (response.payload case final id? when id.isNotEmpty) onOpen(id);
        },
      );
      _ready = true;
    } catch (e) {
      debugPrint('Notifications are off: $e');
    }
  }

  static Future<void> show(Alert alert) async {
    if (!_ready) return;
    await _plugin.show(id: _next++, title: alert.title, body: alert.body, payload: alert.sessionId);
  }
}

/// Looks at the sessions every few seconds while the app runs and raises a notification for each [alertsBetween].
class SessionWatcher {
  SessionWatcher(this._api, {this.every = const Duration(seconds: 8), this.onAlert = Notifications.show});

  final Api _api;
  final Duration every;
  final Future<void> Function(Alert) onAlert;
  Map<String, Session>? _last;
  Timer? _timer;

  void start() {
    _timer ??= Timer.periodic(every, (_) => check());
    check();
  }

  void stop() {
    _timer?.cancel();
    _timer = null;
  }

  Future<void> check() async {
    try {
      final now = await _api.sessions();
      for (final alert in alertsBetween(_last, now)) {
        await onAlert(alert);
      }
      _last = {for (final s in now) s.id: s};
    } catch (_) {
      // Signed out or the backend is down: try again next time
    }
  }
}

/// Whether the app should watch at all: with login on, only once signed in.
bool watchSessions(bool signedIn) => !Config.loginEnabled || signedIn;
