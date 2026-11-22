import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:loop_runner_app/api.dart';
import 'package:loop_runner_app/config.dart';
import 'package:loop_runner_app/models.dart';

void main() {
  test('the backend defaults to localhost and its WebSocket follows the scheme', () {
    expect(Config.apiUrl, 'http://localhost:8000');
    expect(Config.wsUrl, 'ws://localhost:8000');
    expect(Config.loginEnabled, isFalse);
  });

  test('sessions are read from GET /sessions, without a token when login is off', () async {
    late http.Request sent;
    final api = Api(
      client: MockClient((request) async {
        sent = request;
        return http.Response(
          jsonEncode([
            {
              'id': 's1',
              'name': 'fix login',
              'status': 'passed',
              'model': 'claude-haiku-5-5',
              'total_iterations': 2,
              'max_iterations': 10,
              'total_cost_usd': 0.0123,
              'created_at': '2026-11-21T10:00:00',
              'repo_path': '/r',
            },
          ]),
          200,
        );
      }),
    );
    final sessions = await api.sessions();
    expect(sent.url.toString(), 'http://localhost:8000/sessions');
    expect(sent.headers.containsKey('authorization'), isFalse);
    expect(sessions.single.name, 'fix login');
    expect(sessions.single.totalCostUsd, closeTo(0.0123, 1e-9));
    expect(sessions.single.running, isFalse);
  });

  test('an error carries the backend detail', () async {
    final api = Api(client: MockClient((_) async => http.Response(jsonEncode({'detail': 'Session not found'}), 404)));
    await expectLater(
      api.session('nope'),
      throwsA(isA<ApiError>().having((e) => e.message, 'message', 'Session not found')),
    );
  });

  test('saved and live events carry the same id, so a live repeat can be spotted', () {
    final saved = SessionEvent.saved({'id': 7, 'kind': 'focus', 'files': [], 'tests_passing': false});
    final live = SessionEvent.live({
      'event': 'focus',
      'data': {'id': 7, 'files': [], 'tests_passing': false},
    });
    expect(saved.kind, 'focus');
    expect(saved.data.containsKey('kind'), isFalse);
    expect(live.id, saved.id);
  });

  test('a new session from a folder sends repo_path only, with the task nested', () async {
    late Map<String, dynamic> body;
    final api = Api(
      client: MockClient((request) async {
        expect(request.method, 'POST');
        expect(request.url.path, '/sessions');
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode({'id': 'new-1'}), 200);
      }),
    );
    final id = await api.createSession(
      NewSession(
        name: 'fix',
        repoPath: '/repo',
        verifyCommand: 'pytest -q',
        title: 'Fix it',
        spec: 'Make it pass',
        model: 'claude-sonnet-5-5',
        maxIterations: 5,
        cascade: true,
      ),
    );
    expect(id, 'new-1');
    expect(body['repo_path'], '/repo');
    expect(body.containsKey('repo_url'), isFalse);
    expect(body.containsKey('max_cost_usd'), isFalse);
    expect(body['task'], {'title': 'Fix it', 'spec': 'Make it pass', 'files_context': []});
    expect(body['max_iterations'], 5);
    expect(body['cascade'], isTrue);
  });

  test('a refused field reads as the field and its reason', () async {
    final api = Api(
      client: MockClient(
        (_) async => http.Response(
          jsonEncode({
            'detail': [
              {
                'loc': ['body', 'max_iterations'],
                'msg': 'Value error, max_iterations must be between 1 and 50',
              },
            ],
          }),
          422,
        ),
      ),
    );
    await expectLater(
      api.createSession(
        NewSession(name: 'x', repoUrl: 'https://github.com/o/r', verifyCommand: 't', title: 't', spec: 's', model: 'm'),
      ),
      throwsA(
        isA<ApiError>().having(
          (e) => e.message,
          'message',
          'max_iterations: Value error, max_iterations must be between 1 and 50',
        ),
      ),
    );
  });

  test('models come back flat, each with its provider', () async {
    final api = Api(
      client: MockClient((request) async {
        expect(request.url.path, '/keys/models');
        return http.Response(
          jsonEncode({
            'anthropic': [
              {'id': 'claude-sonnet-5-5', 'name': 'Claude Sonnet 5.5'},
            ],
            'openai': [
              {'id': 'gpt-5', 'name': 'GPT-5'},
            ],
          }),
          200,
        );
      }),
    );
    final models = await api.models();
    expect([for (final m in models) '${m.provider}/${m.id}'], ['anthropic/claude-sonnet-5-5', 'openai/gpt-5']);
  });

  test('the diff is returned as the patch text', () async {
    const patch = 'diff --git a/x.py b/x.py\n+x = 2\n';
    final api = Api(client: MockClient((_) async => http.Response(patch, 200)));
    expect(await api.diff('s1'), patch);
  });

  test('a backend that never answers is reported, not waited on forever', () async {
    final api = Api(client: MockClient((_) => Completer<http.Response>().future));
    await expectLater(
      api.sessions().timeout(Api.timeout + const Duration(seconds: 2)),
      throwsA(isA<ApiError>().having((e) => e.message, 'message', contains('No answer from the backend'))),
    );
  }, timeout: const Timeout(Duration(seconds: 30)));
}
