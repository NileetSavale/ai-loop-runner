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

  Uri _url(String path) => Uri.parse('${Config.apiUrl}$path');

  Future<dynamic> _get(String path) async => _decode(await _http.get(_url(path), headers: _headers));

  Future<dynamic> _post(String path, [Object? body]) async =>
      _decode(await _http.post(_url(path), headers: _headers, body: body == null ? null : jsonEncode(body)));

  Future<dynamic> _delete(String path) async => _decode(await _http.delete(_url(path), headers: _headers));

  dynamic _decode(http.Response response) {
    if (response.statusCode >= 400) throw ApiError(response.statusCode, _detail(response.body));
    return jsonDecode(response.body);
  }

  /// FastAPI's error: a sentence, or for a request the backend refused field by field, each field and its reason.
  static String _detail(String body) {
    try {
      final detail = (jsonDecode(body) as Map<String, dynamic>)['detail'];
      if (detail is List) {
        return [
          for (final item in detail.cast<Map<String, dynamic>>())
            '${(item['loc'] as List?)?.skip(1).join('.') ?? ''}: ${item['msg']}',
        ].join('\n');
      }
      return detail?.toString() ?? body;
    } catch (_) {
      return body;
    }
  }

  Future<List<Session>> sessions() async =>
      [for (final row in await _get('/sessions') as List) Session.fromJson(row as Map<String, dynamic>)];

  Future<Session> session(String id) async => Session.fromJson(await _get('/sessions/$id') as Map<String, dynamic>);

  Future<List<SessionEvent>> events(String id) async =>
      [for (final row in await _get('/sessions/$id/events') as List) SessionEvent.saved(row as Map<String, dynamic>)];

  Future<void> stop(String id) => _post('/sessions/$id/stop');

  Future<void> delete(String id) => _delete('/sessions/$id');

  /// Starts the session at once; returns its id.
  Future<String> createSession(NewSession session) async =>
      (await _post('/sessions', session.toJson()) as Map<String, dynamic>)['id'] as String;

  /// The session's changes as a patch (git apply can take it).
  Future<String> diff(String id) async {
    final response = await _http.get(_url('/sessions/$id/diff'), headers: _headers);
    if (response.statusCode >= 400) throw ApiError(response.statusCode, _detail(response.body));
    return response.body;
  }

  /// Every model the backend supports, by provider.
  Future<List<ModelChoice>> models() async => [
        for (final entry in (await _get('/keys/models') as Map<String, dynamic>).entries)
          for (final model in (entry.value as List).cast<Map<String, dynamic>>())
            ModelChoice(model['id'] as String, model['name'] as String, entry.key),
      ];

  Future<List<Pipeline>> pipelines() async =>
      [for (final row in await _get('/pipelines') as List) Pipeline.fromJson(row as Map<String, dynamic>)];

  Future<Pipeline> pipeline(String name) async =>
      Pipeline.fromJson(await _get('/pipelines/$name') as Map<String, dynamic>);

  /// Checks and saves `backend/pipelines/<name>.yaml`; an ApiError carries the reason it can't run.
  Future<Pipeline> savePipeline(String name, Map<String, dynamic> document) async {
    final response = await _http.put(_url('/pipelines/$name'), headers: _headers, body: jsonEncode(document));
    return Pipeline.fromJson(_decode(response) as Map<String, dynamic>);
  }

  Future<void> deletePipeline(String name) => _delete('/pipelines/$name');

  /// The user's saved provider keys (never the keys themselves). Needs login.
  Future<List<SavedKey>> keys() async =>
      [for (final row in await _get('/keys') as List) SavedKey.fromJson(row as Map<String, dynamic>)];

  Future<void> addKey(String provider, String apiKey) => _post('/keys', {'provider': provider, 'api_key': apiKey});

  Future<void> deleteKey(String id) => _delete('/keys/$id');

  /// The session's live events. The stream ends when the socket closes; the caller reconnects and reloads the saved
  /// events to fill the gap.
  Stream<SessionEvent> live(String id) {
    final channel = WebSocketChannel.connect(Uri.parse('${Config.wsUrl}/ws/sessions/$id'));
    channel.sink.add(_token);
    return channel.stream.map((raw) => SessionEvent.live(jsonDecode(raw as String) as Map<String, dynamic>));
  }
}
