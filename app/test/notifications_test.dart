import 'package:flutter_test/flutter_test.dart';
import 'package:loop_runner_app/models.dart';
import 'package:loop_runner_app/notifications.dart';

Session s(String id, String status, {String? waiting, String name = 'Fix login'}) =>
    Session.fromJson({'id': id, 'name': name, 'status': status, 'waiting_for': waiting});

void main() {
  test('the first look sets the baseline and raises nothing', () {
    expect(alertsBetween(null, [s('a', 'passed'), s('b', 'running', waiting: 'ok')]), isEmpty);
  });

  test('a running session that ends raises one alert with its outcome', () {
    final before = {'a': s('a', 'running')};
    final alerts = alertsBetween(before, [s('a', 'failed')]);
    expect(alerts, [(sessionId: 'a', title: 'Session failed', body: 'Fix login')]);
  });

  test('a session that starts waiting for approval raises an alert once', () {
    final before = {'a': s('a', 'running')};
    final waiting = [s('a', 'running', waiting: 'ok')];
    expect(alertsBetween(before, waiting).single.title, 'Waiting for your approval');
    expect(alertsBetween({'a': waiting.single}, waiting), isEmpty, reason: 'still waiting is not news');
  });

  test('an ended session that stays ended raises nothing', () {
    expect(alertsBetween({'a': s('a', 'passed')}, [s('a', 'passed')]), isEmpty);
  });
}
