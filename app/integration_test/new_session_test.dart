// Drives the real app against a running backend (API_URL, default http://localhost:8000, in local mode):
//   REPO=/path/to/a/git/repo flutter test integration_test -d macos
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:integration_test/integration_test.dart';
import 'package:loop_runner_app/config.dart';
import 'package:loop_runner_app/main.dart';

const repo = String.fromEnvironment('REPO');

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  // The same tests run on a desktop window (sidebar, split view) and on a phone (bottom bar, one pane at a time)
  bool isWide(WidgetTester tester) => tester.view.physicalSize.width / tester.view.devicePixelRatio >= 900;

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

    if (isWide(tester)) {
      expect(find.text('Pick a session, or start one'), findsOneWidget, reason: 'the split view, nothing selected');
    }
    await tester.tap(find.byTooltip('New session'));
    await settle(tester);
    await tester.enterText(find.widgetWithText(TextFormField, 'Repo folder'), repo);
    await tester.enterText(find.widgetWithText(TextFormField, 'Test command'), 'false');
    await tester.enterText(find.widgetWithText(TextFormField, 'Task'), 'Integration test task');
    await tester.enterText(
      find.widgetWithText(TextFormField, 'What should change, and how to tell it worked'),
      'Make x equal 2.',
    );
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
    if (!isWide(tester)) {
      // A phone lists the pipelines first
      await tester.tap(find.text('reviewed-cascade').first);
      await settle(tester);
    }
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

  testWidgets('a pipeline built in the editor is saved, shown on its map, and deleted', (tester) async {
    await tester.pumpWidget(const ProviderScope(child: LoopRunnerApp()));
    await settle(tester);
    await tester.tap(find.text('Pipelines').first);
    await settle(tester);
    await tester.tap(find.text('New pipeline'));
    for (var i = 0; i < 20 && find.text('Add step').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 250));
    }
    await tester.enterText(find.widgetWithText(TextField, 'Name'), 'itest-lint');
    // The new pipeline starts with one fix step; add a command step after it
    await tester.tap(find.text('Add step'));
    await settle(tester);
    await tester.enterText(find.widgetWithText(TextFormField, 'Command'), 'true');
    await settle(tester);
    // A step nothing leads to can't be saved, so drop the starting fix step: the command step becomes the start
    await tester.ensureVisible(find.byTooltip('Remove step').first);
    await settle(tester);
    await tester.tap(find.byTooltip('Remove step').first);
    await settle(tester);
    expect(find.text('step2'), findsWidgets, reason: 'the map draws the new step');
    await tester.tap(find.text('Save'));
    for (var i = 0; i < 40 && find.text('itest-lint').evaluate().length < 2; i++) {
      await tester.pump(const Duration(milliseconds: 250));
    }
    expect(find.text('itest-lint'), findsWidgets, reason: 'saved and selected in the list');
    await tester.tap(find.byTooltip('Delete'));
    await settle(tester);
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    for (var i = 0; i < 40 && find.text('itest-lint').evaluate().isNotEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 250));
    }
    expect(find.text('itest-lint'), findsNothing);
  });

  testWidgets('a session waiting at an approve step is approved from the app and passes', (tester) async {
    // A pipeline with no model calls: a check, then a person's approval
    final api = Config.apiUrl;
    final headers = {'content-type': 'application/json'};
    await http.put(
      Uri.parse('$api/pipelines/itest-approve'),
      headers: headers,
      body: jsonEncode({
        'start': 'check',
        'steps': {
          'check': {'kind': 'command', 'run': 'true', 'on_pass': 'ok', 'on_fail': 'done'},
          'ok': {'kind': 'approve', 'on_accept': 'done', 'on_reject': 'done'},
        },
      }),
    );
    final created = await http.post(
      Uri.parse('$api/sessions'),
      headers: headers,
      body: jsonEncode({
        'name': 'Approval test',
        'repo_path': repo,
        'verify_command': 'true',
        'model': 'claude-sonnet-5-5',
        'pipeline': 'itest-approve',
        'task': {'title': 'Approval test', 'spec': 'Wait for a person.'},
      }),
    );
    final id = (jsonDecode(created.body) as Map<String, dynamic>)['id'] as String;

    await tester.pumpWidget(const ProviderScope(child: LoopRunnerApp()));
    await settle(tester);
    // The router outlives each test, so start from Sessions rather than where the last test ended
    await tester.tap(find.text('Sessions').first);
    await settle(tester);
    for (var i = 0; i < 40 && find.text('Approval test').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 250));
    }
    await tester.tap(find.text('Approval test').first);
    for (var i = 0; i < 60 && find.text('Waiting for your approval').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 500));
    }
    expect(find.text('Waiting for your approval'), findsOneWidget);
    await tester.tap(find.text('Approve'));
    for (var i = 0; i < 60 && find.text('Session passed').evaluate().isEmpty; i++) {
      await tester.pump(const Duration(milliseconds: 500));
    }
    expect(find.text('Session passed'), findsOneWidget);

    await http.delete(Uri.parse('$api/sessions/$id'));
    await http.delete(Uri.parse('$api/pipelines/itest-approve'));
  });
}
