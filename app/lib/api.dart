import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:supabase_flutter/supabase_flutter.dart' show Supabase;
import 'package:web_socket_channel/web_socket_channel.dart';

import 'config.dart';
import 'models.dart';

class ApiError implements Exception {
  ApiError(this.status, this.message);
  final int status;
  final String message;

  @override
  String toString() => 'HTTP $status: $message';
}

/// The Loop Runner backend: REST with the Supabase token as a Bearer header, and the session WebSocket, which takes
/// the token as its first message (the backend's rule, so the token never lands in a URL or a log).
class Api {
  Api({http.Client? client}) : _http = client ?? http.Client();

  final http.Client _http;

  String get _token =>
      Config.loginEnabled ? Supabase.instance.client.auth.currentSession?.accessToken ?? '' : '';

  Map<String, String> get _headers =>
      {'content-type': 'application/json', if (_token.isNotEmpty) 'authorization': 'Bearer $_token'};

  Future<dynamic> _get(String path) async {
    final response = await _http.get(Uri.parse('${Config.apiUrl}$path'), headers: _headers);
    return _decode(response);
  }

  dynamic _decode(http.Response response) {
    if (response.statusCode >= 400) {
      String message = response.body;
      try {
        message = (jsonDecode(response.body) as Map<String, dynamic>)['detail']?.toString() ?? message;
      } catch (_) {}
      throw ApiError(response.statusCode, message);
    }
    return jsonDecode(response.body);
  }

  Future<List<Session>> sessions() async =>
      [for (final row in await _get('/sessions') as List) Session.fromJson(row as Map<String, dynamic>)];

  Future<Session> session(String id) async => Session.fromJson(await _get('/sessions/$id') as Map<String, dynamic>);

  Future<List<SessionEvent>> events(String id) async =>
      [for (final row in await _get('/sessions/$id/events') as List) SessionEvent.saved(row as Map<String, dynamic>)];

  Future<void> stop(String id) async {
    _decode(await _http.post(Uri.parse('${Config.apiUrl}/sessions/$id/stop'), headers: _headers));
  }

  /// The session's live events. The stream ends when the socket closes; the caller reconnects and reloads the saved
  /// events to fill the gap.
  Stream<SessionEvent> live(String id) {
    final channel = WebSocketChannel.connect(Uri.parse('${Config.wsUrl}/ws/sessions/$id'));
    channel.sink.add(_token);
    return channel.stream.map((raw) => SessionEvent.live(jsonDecode(raw as String) as Map<String, dynamic>));
  }
}
