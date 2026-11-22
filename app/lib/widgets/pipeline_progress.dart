import '../models.dart';
import 'pipeline_map.dart';

/// A session's way through its pipeline, read from its "cascade" events (core/cascade.py sends one as each step
/// starts, plus "reviewed" with the review's verdict).
class PipelineProgress {
  PipelineProgress(this.states, this.taken, this.visited, this.verdicts);

  final Map<String, StepState> states;
  final Set<(String, String)> taken;

  /// The steps the session reached, in order.
  final List<String> visited;

  /// The review steps' verdicts: true to accept.
  final Map<String, bool> verdicts;

  factory PipelineProgress.of(Pipeline pipeline, List<SessionEvent> events, Session session) {
    final visited = <String>[];
    final verdicts = <String, bool>{};
    // A command step reports its own result; other steps' outcomes follow from where the session went next
    final commandPassed = <String, bool>{};
    String? lastReview;
    for (final e in events.where((e) => e.kind == 'cascade')) {
      final step = e.data['step'] as String?;
      if (step == 'reviewed') {
        if (lastReview != null) verdicts[lastReview] = e.data['accept'] == true;
      } else if (step == 'approved') {
        // A person's answer at an approve step names the step it answers
        if (e.data['of'] is String) verdicts[e.data['of'] as String] = e.data['accept'] == true;
      } else if (step != null && pipeline.step(step) != null) {
        visited.add(step);
        if (e.data['passed'] is bool) commandPassed[step] = e.data['passed'] as bool;
        if (pipeline.step(step)!.kind == 'review') lastReview = step;
      }
    }

    final states = <String, StepState>{};
    final taken = <(String, String)>{};
    final ended = !session.running;
    for (final (i, id) in visited.indexed) {
      final step = pipeline.step(id)!;
      final next = i + 1 < visited.length ? visited[i + 1] : null;
      String? outcome;
      if (commandPassed.containsKey(id)) {
        outcome = commandPassed[id]! ? 'on_pass' : 'on_fail';
      } else if (next != null) {
        // Which outcome led to the next step the session reached
        outcome = step.edges.entries.where((e) => e.value == next).map((e) => e.key).firstOrNull;
      } else if (ended) {
        outcome = switch (step.kind) {
          'review' || 'approve' => verdicts[id] == null ? null : (verdicts[id]! ? 'on_accept' : 'on_reject'),
          'fix' => session.status == 'passed' ? 'on_pass' : 'on_fail',
          _ => step.edges.keys.first,
        };
      }
      if (outcome != null) taken.add((id, outcome));
      states[id] = switch (outcome) {
        null => ended ? StepState.failed : StepState.active,
        'on_fail' || 'on_reject' => StepState.failed,
        _ => StepState.passed,
      };
    }
    for (final step in pipeline.steps) {
      states.putIfAbsent(step.id, () => ended ? StepState.skipped : StepState.idle);
    }
    states['done'] = !ended ? StepState.idle : (session.status == 'passed' ? StepState.passed : StepState.failed);
    return PipelineProgress(states, taken, visited, verdicts);
  }
}
