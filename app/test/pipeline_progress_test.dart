import 'package:flutter_test/flutter_test.dart';
import 'package:loop_runner_app/models.dart';
import 'package:loop_runner_app/widgets/pipeline_map.dart';
import 'package:loop_runner_app/widgets/pipeline_progress.dart';

/// backend/pipelines/reviewed-cascade.yaml, as GET /pipelines/reviewed-cascade returns it.
final cascade = Pipeline.fromJson({
  'name': 'reviewed-cascade',
  'start': 'scout',
  'steps': [
    {
      'id': 'scout',
      'kind': 'scout',
      'model': 'cheap',
      'edges': {'next': 'cheap'},
      'options': {'budget_usd': 0.05},
    },
    {
      'id': 'cheap',
      'kind': 'fix',
      'model': 'cheap',
      'edges': {'on_pass': 'review', 'on_fail': 'escalated'},
    },
    {
      'id': 'review',
      'kind': 'review',
      'model': 'claude-sonnet-5-5',
      'edges': {'on_accept': 'done', 'on_reject': 'escalated'},
    },
    {
      'id': 'escalated',
      'kind': 'fix',
      'model': 'main',
      'edges': {'on_pass': 'done', 'on_fail': 'done'},
      'options': {'undo': true},
    },
  ],
});

Session session(String status) => Session.fromJson({'id': 's', 'status': status});

SessionEvent step(String id, [Map<String, dynamic> extra = const {}]) =>
    SessionEvent('cascade', {'step': id, 'model': 'claude-haiku-5-5', ...extra});

void main() {
  test('while the cheap model works, scout is done, cheap runs, the rest wait', () {
    final p = PipelineProgress.of(cascade, [step('scout'), step('cheap')], session('running'));
    expect(p.states['scout'], StepState.passed);
    expect(p.states['cheap'], StepState.active);
    expect(p.states['review'], StepState.idle);
    expect(p.states['done'], StepState.idle);
    expect(p.taken, {('scout', 'next')});
  });

  test('a reviewed pass ends at done; the escalation is skipped', () {
    final p = PipelineProgress.of(cascade, [
      step('scout'),
      step('cheap'),
      step('review'),
      step('reviewed', {'accept': true}),
    ], session('passed'));
    expect(p.states['cheap'], StepState.passed);
    expect(p.states['review'], StepState.passed);
    expect(p.states['escalated'], StepState.skipped);
    expect(p.states['done'], StepState.passed);
    expect(p.taken, {('scout', 'next'), ('cheap', 'on_pass'), ('review', 'on_accept')});
  });

  test('a rejected pass goes to the escalation, which decides the end', () {
    final p = PipelineProgress.of(cascade, [
      step('scout'),
      step('cheap'),
      step('review'),
      step('reviewed', {'accept': false}),
      step('escalated'),
    ], session('failed'));
    expect(p.states['review'], StepState.failed);
    expect(p.verdicts['review'], isFalse);
    expect(p.states['escalated'], StepState.failed);
    expect(p.taken, containsAll({('review', 'on_reject'), ('escalated', 'on_fail')}));
    expect(p.states['done'], StepState.failed);
  });

  test('a cheap failure skips the review', () {
    final p = PipelineProgress.of(cascade, [step('scout'), step('cheap'), step('escalated')], session('running'));
    expect(p.states['cheap'], StepState.failed);
    expect(p.states['review'], StepState.idle);
    expect(p.states['escalated'], StepState.active);
    expect(p.taken, {('scout', 'next'), ('cheap', 'on_fail')});
  });

  test('a command step shows its own result, and the arrow it took', () {
    final withLint = Pipeline.fromJson({
      'name': 'lint-after-fix',
      'start': 'fix',
      'steps': [
        {
          'id': 'fix',
          'kind': 'fix',
          'model': 'main',
          'edges': {'on_pass': 'lint', 'on_fail': 'done'},
        },
        {
          'id': 'lint',
          'kind': 'command',
          'model': '',
          'edges': {'on_pass': 'done', 'on_fail': 'done'},
          'options': {'run': 'ruff check .'},
        },
      ],
    });
    final p = PipelineProgress.of(withLint, [
      SessionEvent('cascade', {'step': 'fix', 'model': 'claude-sonnet-5-5'}),
      SessionEvent('cascade', {'step': 'lint', 'step_kind': 'command', 'command': 'ruff check .', 'passed': false}),
    ], session('passed'));
    expect(p.states['fix'], StepState.passed);
    expect(p.states['lint'], StepState.failed);
    expect(p.taken, {('fix', 'on_pass'), ('lint', 'on_fail')});
  });
}
