// Drives the real app against a running backend (API_URL, default http://localhost:8000, in local mode):
//   REPO=/path/to/a/git/repo flutter test integration_test -d macos
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:loop_runner_app/main.dart';

const repo = String.fromEnvironment('REPO');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('a session started from the app runs, and its changes open', (tester) async {
    expect(repo, isNotEmpty, reason: 'pass --dart-define=REPO=<a git repo on this machine>');
    await tester.pumpWidget(const ProviderScope(child: LoopRunnerApp()));
    await tester.pumpAndSettle();
    expect(find.text('Sessions'), findsOneWidget);

    await tester.tap(find.text('New session'));
    await tester.pumpAndSettle();
    await tester.enterText(find.widgetWithText(TextFormField, 'Repo folder'), repo);
    await tester.enterText(find.widgetWithText(TextFormField, 'Test command'), 'false');
    await tester.enterText(find.widgetWithText(TextFormField, 'Task'), 'Integration test task');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'What should change, and how to tell it worked'), 'Make x equal 2.');
    // The form is a ListView, which builds only what is on screen
    final start = find.text('Start session');
    await tester.scrollUntilVisible(start, 300, scrollable: find.byType(Scrollable).first);
    await tester.pumpAndSettle();
    await tester.tap(start);

    // The session screen opens (only it has the Changes button), then the session's end arrives live: the test
    // command fails and the model call fails on the backend's key, so the session ends failed
    Future<void> waitFor(Finder finder, {int seconds = 60}) async {
      for (var i = 0; i < seconds * 2 && finder.evaluate().isEmpty; i++) {
        await tester.pump(const Duration(milliseconds: 500));
      }
      expect(finder, findsWidgets);
    }

    await waitFor(find.byTooltip('Changes'));
    expect(find.text('Make x equal 2.'), findsOneWidget, reason: 'the task, in the header');
    await waitFor(find.text('Session failed'), seconds: 90);
    expect(find.text('Tests failed'), findsWidgets);

    await tester.tap(find.byTooltip('Changes'));
    await tester.pumpAndSettle();
    expect(find.text('Changes'), findsOneWidget);
  });
}
