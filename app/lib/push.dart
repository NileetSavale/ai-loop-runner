import 'api.dart';

/// Closed-app push notifications: the backend side is built (backend/core/notify.py, POST /devices) and sends nothing
/// until Apple push credentials are set, which needs the paid Apple Developer Program.
///
/// To switch it on:
/// 1. Join the program, enable Push Notifications for com.looprunner.loopRunnerApp, and create an APNs key.
/// 2. Set the backend's PUSH_APNS_KEY_ID, PUSH_APNS_TEAM_ID, PUSH_APNS_KEY_PATH and PUSH_APNS_TOPIC.
/// 3. Add a package that asks iOS for the device's push token (e.g. firebase_messaging, or flutter_apns_only),
///    and give its token to [register] at startup.
/// 4. Run the app with PUSH_ENABLED=true in app/.env.
///
/// Until then the app's own notifications (notifications.dart) cover a session it is watching.
class RemotePush {
  static const enabled = bool.fromEnvironment('PUSH_ENABLED');

  /// Sends this device's push token to the backend, so a session's end reaches it even when the app is closed.
  static Future<void> register(Api api, {required String platform, required String? token}) async {
    if (!enabled || token == null || token.isEmpty) return;
    await api.registerDevice(platform, token);
  }
}
