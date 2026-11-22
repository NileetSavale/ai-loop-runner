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

  // Not pumpAndSettle: the list refreshes every few seconds while any session runs, so the screen never goes still
  Future<void> settle(WidgetTester tester) async {
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 100));
    }
  }

  testWidgets('a session started from the app runs, and its changes open', (tester) async {
    expect(repo, isNotEmpty, reason: 'pass --dart-define=REPO=<a git repo on this machine>');
    await tester.pumpWidget(const ProviderScope(child: LoopRunnerApp()));
    await settle(tester);
    expect(find.text('Sessions'), findsWidgets); // the sidebar and the list's title

    expect(find.text('Pick a session, or start one'), findsOneWidget, reason: 'the split view, nothing selected');
    await tester.tap(find.byTooltip('New session'));
    await settle(tester);
    await tester.enterText(find.widgetWithText(TextFormField, 'Repo folder'), repo);
    await tester.enterText(find.widgetWithText(TextFormField, 'Test command'), 'false');
    await tester.enterText(find.widgetWithText(TextFormField, 'Task'), 'Integration test task');
    await tester.enterText(
        find.widgetWithText(TextFormField, 'What should change, and how to tell it worked'), 'Make x equal 2.');
    // The form is a ListView, which builds only what is on screen
    final start = find.text('Start session');
    await tester.scrollUntilVisible(start, 300, scrollable: find.byType(Scrollable).first);
    await settle(tester);
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
    expect(find.text('The run stopped'), findsWidgets, reason: 'the 401 shown as why the run stopped');
    // Still beside the list, which now shows this session
    expect(find.text('Sessions'), findsWidgets); // the sidebar and the list's title
    expect(find.text('Integration test task'), findsWidgets);

    await tester.tap(find.byTooltip('Changes'));
    await settle(tester);
    expect(find.text('Changes'), findsOneWidget);
  });

  testWidgets('the Pipelines section maps the reviewed cascade and explains a step', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: LoopRunnerApp()));
    await settle(tester);
    await tester.tap(find.text('Pipelines').first);
    for (var i = 0; i < 40 && find.text('reviewed-cascade').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 250));
    }
    expect(find.text('reviewed-cascade'), findsWidgets);
    for (final id in ['scout', 'cheap', 'review', 'escalated', 'done']) {
      expect(find.text(id), findsWidgets, reason: 'the map draws $id');
    }
    // The map scrolls sideways when it is wider than its pane
    await tester.ensureVisible(find.text('review').first);
    await settle(tester);
    await tester.tap(find.text('review').first);
    await settle(tester);
    expect(find.textContaining('accepts or rejects it'), findsOneWidget);
    expect(find.text('reject → escalated'), findsOneWidget);
  });
}
