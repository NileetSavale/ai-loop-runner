import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../main.dart';
import '../models.dart';
import '../widgets/pipeline_map.dart';
import '../widgets/pipeline_progress.dart';
import 'pipelines_screen.dart';
import 'sessions_screen.dart';

/// One session, live: what it was asked, then every step as it happens. The saved events are loaded first and the
/// WebSocket adds the rest; after a dropped connection the saved events are reloaded, so nothing is missed.
class SessionScreen extends ConsumerStatefulWidget {
  const SessionScreen({super.key, required this.id, this.showBack = false});
  final String id;

  /// A back arrow to the list, when the session fills a narrow window instead of sitting beside the list.
  final bool showBack;

  @override
  ConsumerState<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends ConsumerState<SessionScreen> {
  Session? _session;
  final List<SessionEvent> _events = [];
  final Set<int> _seen = {};
  StreamSubscription<SessionEvent>? _live;
  Timer? _retry;
  Timer? _check;
  int _failures = 0;
  bool _connected = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _live?.cancel();
    _retry?.cancel();
    _check?.cancel();
    super.dispose();
  }

  Future<void> _load() async {
    final api = ref.read(apiProvider);
    try {
      final session = await api.session(widget.id);
      final saved = await api.events(widget.id);
      if (!mounted) return;
      setState(() {
        _session = session;
        _error = null;
        saved.forEach(_add);
      });
      if (session.running) _connect();
    } catch (e) {
      if (mounted) setState(() => _error = '$e');
    }
  }

  void _add(SessionEvent event) {
    if (event.id != null && !_seen.add(event.id!)) return;
    _events.add(event);
  }

  void _connect() {
    // A session can end between loading it and the socket opening, and the end is only sent live, never saved:
    // ask again once the socket is open, and every few seconds while it runs, so a missed end still shows.
    _check?.cancel();
    _check = Timer.periodic(const Duration(seconds: 5), (_) => _refreshSession());
    Future.delayed(const Duration(milliseconds: 500), _refreshSession);
    _live?.cancel();
    _live = ref.read(apiProvider).live(widget.id).listen(
      (event) {
        setState(() {
          _connected = true;
          _failures = 0;
          _add(event);
        });
        if (event.kind == 'session_complete') _refreshSession();
      },
      onError: (_) => _dropped(),
      onDone: _dropped,
    );
  }

  /// The socket closed: reconnect with a growing wait while the session runs, reloading what was missed.
  void _dropped() {
    if (!mounted) return;
    setState(() => _connected = false);
    if (_session?.running != true) return;
    _failures++;
    _retry = Timer(Duration(seconds: (1 << _failures.clamp(0, 5))), _load);
  }

  Future<void> _refreshSession() async {
    if (!mounted) return;
    final api = ref.read(apiProvider);
    try {
      final session = await api.session(widget.id);
      final ended = !session.running;
      final saved = ended ? await api.events(widget.id) : const <SessionEvent>[];
      if (!mounted) return;
      setState(() {
        _session = session;
        saved.forEach(_add);
      });
      if (ended) {
        _check?.cancel();
        _live?.cancel();
        _connected = false;
      }
    } catch (_) {
      // The next check, or the socket, tries again
    }
  }

  Future<void> _delete() async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this session?'),
        content: const Text('Its history goes, and a repo the backend cloned for it is removed. '
            'A folder on your machine is left as it is.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (sure != true) return;
    try {
      await ref.read(apiProvider).delete(widget.id);
      ref.invalidate(sessionsProvider);
      if (mounted) context.go('/sessions');
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Couldn\'t delete: $e')));
    }
  }

  Future<void> _stop() async {
    try {
      await ref.read(apiProvider).stop(widget.id);
      await _refreshSession();
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Couldn\'t stop: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final session = _session;
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        leading: widget.showBack
            ? IconButton(icon: const Icon(Icons.arrow_back), onPressed: () => context.go('/sessions'))
            : null,
        title: Text(session?.name ?? 'Session'),
        actions: [
          if (session?.running == true) ...[
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Chip(
                avatar: Icon(Icons.circle, size: 10, color: _connected ? Colors.green : Colors.orange),
                label: Text(_connected ? 'live' : 'connecting'),
              ),
            ),
            TextButton.icon(onPressed: _stop, icon: const Icon(Icons.stop), label: const Text('Stop')),
          ],
          if (session != null) ...[
            IconButton(
              tooltip: 'Changes',
              icon: const Icon(Icons.difference_outlined),
              onPressed: () => context.go('/sessions/${widget.id}/diff'),
            ),
            IconButton(tooltip: 'Delete', icon: const Icon(Icons.delete_outline), onPressed: _delete),
          ],
        ],
      ),
      body: _error != null
          ? Center(child: Text(_error!))
          : session == null
              ? const Center(child: CircularProgressIndicator())
              : _Timeline(session: session, events: _events),
    );
  }
}

/// One attempt of one model's loop. A cascade runs a loop per model and each counts its attempts from 1, so a
/// stage starts a new set of attempts.
class _Attempt {
  _Attempt(this.stage, this.number, this.model);
  final String stage;
  final int number;
  final String model;
  final List<SessionEvent> events = [];

  bool? get passed {
    final verdicts = events.where((e) => e.kind == 'verify_output').toList();
    return verdicts.isEmpty ? null : verdicts.last.data['passed'] == true;
  }

  double get cost => events
      .where((e) => e.kind == 'usage')
      .fold(0.0, (sum, e) => sum + ((e.data['cost_usd'] as num?)?.toDouble() ?? 0));

  int get filesChanged => events.where((e) => e.kind == 'file_changed').map((e) => e.data['path']).toSet().length;
}

class _Timeline extends StatelessWidget {
  const _Timeline({required this.session, required this.events});
  final Session session;
  final List<SessionEvent> events;

  @override
  Widget build(BuildContext context) {
    // Which pipeline the session ran (core/cascade.py saves it); older cascade sessions ran the default
    final pipelineName =
        events.where((e) => e.kind == 'pipeline').map((e) => e.data['name'] as String?).firstOrNull;
    final before = <SessionEvent>[];
    final attempts = <_Attempt>[];
    final cascade = <SessionEvent>[];
    final commands = <SessionEvent>[];
    SessionEvent? end;
    // A fix step's loop: the session itself, or a cascade step (cheap, escalated) once one starts
    var stage = '';
    var model = session.model;
    for (final e in events) {
      if (e.kind == 'session_complete') {
        end = e;
      } else if (e.kind == 'cascade') {
        cascade.add(e);
        if (e.data['kind'] == 'command') commands.add(e);
        if (e.data['model'] is String && !const {'scout', 'review', 'reviewed'}.contains(e.data['step']) &&
            e.data['kind'] != 'command') {
          stage = e.data['step'] as String;
          model = e.data['model'] as String;
        }
      } else if (e.data['iteration'] is int) {
        final n = e.data['iteration'] as int;
        if (attempts.isEmpty || attempts.last.stage != stage || attempts.last.number != n) {
          attempts.add(_Attempt(stage, n, model));
        }
        attempts.last.events.add(e);
      } else if (e.kind != 'iteration_complete' && e.kind != 'pipeline') {
        before.add(e);
      }
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        _Summary(session: session, attempts: attempts.length),
        // How it ended, and why, is what an ended session is opened for
        if (end != null || !session.running) ...[
          const SizedBox(height: 12),
          _End(end ?? SessionEvent('session_complete', {'status': session.status})),
        ],
        if (cascade.isNotEmpty || pipelineName != null) ...[
          const SizedBox(height: 12),
          _SessionMap(
              session: session, events: events, attempts: attempts, pipelineName: pipelineName ?? 'reviewed-cascade'),
        ],
        const SizedBox(height: 12),
        for (final e in before) _EventTile(e),
        for (final (i, a) in attempts.indexed)
          Card(
            margin: const EdgeInsets.only(top: 8),
            clipBehavior: Clip.antiAlias,
            child: ExpansionTile(
              // The newest attempt is the one being watched
              initiallyExpanded: i == attempts.length - 1,
              leading: Icon(switch (a.passed) {
                true => Icons.check_circle,
                false => Icons.cancel,
                null => Icons.more_horiz,
              }, color: switch (a.passed) { true => Colors.green, false => Colors.red, null => null }),
              title: Text('Attempt ${a.number}${a.stage.isEmpty ? '' : '  ·  ${a.stage} (${a.model})'}'),
              subtitle: Text([
                switch (a.passed) {
                  true => 'tests passed',
                  false => 'tests failed',
                  null => session.running && i == attempts.length - 1 ? 'running' : 'ended without a test result',
                },
                if (a.filesChanged > 0) '${a.filesChanged} file(s) changed',
                if (a.cost > 0) '\$${a.cost.toStringAsFixed(4)}',
              ].join('  ·  ')),
              children: [for (final e in a.events) _EventTile(e)],
            ),
          ),
        // A pipeline's command steps (a linter, more tests): their result shows without opening the map
        if (commands.isNotEmpty)
          Card(
            margin: const EdgeInsets.only(top: 8),
            child: Column(children: [for (final e in commands) _EventTile(e)]),
          ),
      ],
    );
  }
}

class _Summary extends StatelessWidget {
  const _Summary({required this.session, required this.attempts});
  final Session session;
  final int attempts;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    Widget figure(String label, String value) => Expanded(
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: text.labelSmall),
            Text(value, style: text.titleMedium),
          ]),
        );
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            figure('Status', session.status),
            figure('Attempts', '$attempts of ${session.maxIterations}'),
            figure('Cost', '\$${session.totalCostUsd.toStringAsFixed(3)}'),
            figure('Model', session.model),
          ]),
          const SizedBox(height: 8),
          Text(session.repoPath, style: text.bodySmall),
          if (session.spec != null) ...[
            const Divider(height: 24),
            SelectableText(session.spec!),
          ],
        ]),
      ),
    );
  }
}

/// The session's pipeline as a live map: the step running now pulses, finished steps show how they ended, and the
/// arrows the session took are bold. A click opens what happened at that step.
class _SessionMap extends ConsumerWidget {
  const _SessionMap({required this.session, required this.events, required this.attempts, required this.pipelineName});
  final Session session;
  final List<SessionEvent> events;
  final List<_Attempt> attempts;
  final String pipelineName;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final text = Theme.of(context).textTheme;
    return ref.watch(pipelineProvider(pipelineName)).when(
          loading: () => const LinearProgressIndicator(),
          error: (e, _) => Text('Couldn\'t load the pipeline map: $e'),
          data: (pipeline) {
            final progress = PipelineProgress.of(pipeline, events, session);
            final cascade = events.where((e) => e.kind == 'cascade');
            String? modelOf(String step) =>
                cascade.where((e) => e.data['step'] == step).map((e) => e.data['model'] as String?).firstOrNull;
            final models = {
              'cheap': modelOf('scout') ?? modelOf('cheap') ?? 'cheap',
              'main': modelOf('escalated') ?? session.model,
            };
            return Card(
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
                  child: Text('Pipeline: ${pipeline.name}', style: text.titleSmall),
                ),
                PipelineMap(
                  pipeline: pipeline,
                  states: progress.states,
                  taken: progress.taken,
                  models: models,
                  onSelect: (id) => _showStep(context, pipeline.step(id)!, models, progress),
                ),
              ]),
            );
          },
        );
  }

  void _showStep(BuildContext context, PipelineStep step, Map<String, String> models, PipelineProgress progress) {
    final mine = events
        .where((e) => e.kind == 'cascade' && (e.data['step'] == step.id || (step.kind == 'review' && e.data['step'] == 'reviewed')))
        .toList();
    final stepAttempts = attempts.where((a) => a.stage == step.id).toList();
    final reached = progress.visited.contains(step.id);
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('${step.id}  ·  ${step.kind}'),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, mainAxisSize: MainAxisSize.min, children: [
              Text(explainKind(step.kind)),
              const SizedBox(height: 8),
              Text('Model: ${models[step.model] ?? step.model}'),
              if (!reached) const Padding(padding: EdgeInsets.only(top: 8), child: Text('The session didn\'t reach this step.')),
              for (final e in mine) ...[
                if (e.data['notes'] != null) ...[const Divider(), const Text('Notes for the next model:'), SelectableText('${e.data['notes']}')],
                if (e.data['accept'] != null) ...[
                  const Divider(),
                  Text(e.data['accept'] == true ? 'Accepted' : 'Rejected'),
                  if (e.data['why'] != null) SelectableText('${e.data['why']}'),
                ],
                if (e.data['reason'] != null) ...[const Divider(), Text('Why it ran: ${e.data['reason']}')],
                if (e.data['command'] != null) ...[
                  const Divider(),
                  Text('Ran `${e.data['command']}`: ${e.data['passed'] == true ? 'passed' : 'failed (exit ${e.data['exit_code']})'}'),
                  if ((e.data['output'] as String?)?.isNotEmpty ?? false)
                    SelectableText('${e.data['output']}',
                        style: const TextStyle(fontFamily: 'Menlo', fontFamilyFallback: ['Courier New', 'monospace'], fontSize: 12)),
                ],
                if (e.data['cost_usd'] is num) Text('Cost: \$${(e.data['cost_usd'] as num).toStringAsFixed(4)}'),
              ],
              if (stepAttempts.isNotEmpty) ...[
                const Divider(),
                for (final a in stepAttempts)
                  Text('Attempt ${a.number}: ${switch (a.passed) { true => 'tests passed', false => 'tests failed', null => 'no test result' }}'
                      '${a.cost > 0 ? '  ·  \$${a.cost.toStringAsFixed(4)}' : ''}'),
              ],
            ]),
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ),
    );
  }
}

class _End extends StatelessWidget {
  const _End(this.event);
  final SessionEvent event;

  @override
  Widget build(BuildContext context) {
    final status = event.data['status'];
    final scheme = Theme.of(context).colorScheme;
    return Card(
      color: status == 'passed' ? Colors.green.withValues(alpha: 0.15) : scheme.errorContainer.withValues(alpha: 0.5),
      child: ListTile(
        leading: Icon(status == 'passed' ? Icons.flag : Icons.outlined_flag),
        title: Text('Session $status'),
        subtitle: event.data['error'] == null ? null : SelectableText(event.data['error'].toString()),
      ),
    );
  }
}

/// One event in words. Unknown kinds still show, by name, so a new backend event is never silently dropped. Test
/// output opens in full on a click.
class _EventTile extends StatelessWidget {
  const _EventTile(this.event);
  final SessionEvent event;

  @override
  Widget build(BuildContext context) {
    final d = event.data;
    final (IconData icon, String title, String? body) = switch (event.kind) {
      'workspace' => (Icons.folder_open, 'Workspace ready', d['base'] == null ? null : 'from commit ${d['base']}'),
      'setup' => (Icons.build, d['text']?.toString() ?? 'Setting up', null),
      'focus' => (
          Icons.center_focus_strong,
          'Looked at the code: ${(d['files'] as List?)?.length ?? 0} file(s)',
          d['tests_passing'] == true ? 'Tests already pass' : 'Tests fail before any change',
        ),
      'cascade' when d['kind'] == 'command' => (
          d['passed'] == true ? Icons.check_circle_outline : Icons.highlight_off,
          '${d['step']}: ran `${d['command']}`, ${d['passed'] == true ? 'passed' : 'failed'}',
          _tail(d['output']?.toString()),
        ),
      'cascade' => (Icons.alt_route, 'Step ${d['step']} (${d['model'] ?? ''})', d['reason'] ?? d['why']),
      'iteration_start' => (Icons.play_arrow, 'Attempt ${d['iteration']} started', null),
      'tool' => (Icons.handyman, 'Tool: ${d['tool']}', d['error']?.toString() ?? d['target']?.toString()),
      'file_changed' => (Icons.edit_document, 'Changed ${d['path']}', null),
      'usage' => (Icons.payments_outlined, 'Model call', '\$${(d['cost_usd'] as num?)?.toStringAsFixed(4) ?? '?'}'),
      // The backend sends why a run stopped as test output, so the page shows it without a change of its own
      'verify_output' when _isStopReason(d) => (Icons.report_outlined, 'The run stopped', d['output']?.toString()),
      'verify_output' => (
          d['passed'] == true ? Icons.check_circle : Icons.cancel,
          d['passed'] == true ? 'Tests passed' : 'Tests failed',
          _tail(d['output']?.toString()),
        ),
      _ => (Icons.info_outline, event.kind, null),
    };
    final output = event.kind == 'verify_output' || d['kind'] == 'command' ? d['output']?.toString() : null;
    return ListTile(
      dense: true,
      leading: Icon(icon),
      title: Text(title),
      subtitle: body == null ? null : Text(body, maxLines: 4, overflow: TextOverflow.ellipsis),
      trailing: output == null || output.isEmpty ? null : const Icon(Icons.open_in_full, size: 16),
      onTap: output == null || output.isEmpty ? null : () => _showOutput(context, title, output),
    );
  }

  static void _showOutput(BuildContext context, String title, String output) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 720,
          child: SingleChildScrollView(
            child: SelectableText(output,
                style: const TextStyle(fontFamily: 'Menlo', fontFamilyFallback: ['Courier New', 'monospace'], fontSize: 12)),
          ),
        ),
        actions: [TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close'))],
      ),
    );
  }

  /// Reasons core/loop.py and core/cascade.py stop a run with, sent as a failed test output with no attempt.
  static bool _isStopReason(Map<String, dynamic> d) {
    final output = d['output']?.toString() ?? '';
    return d['passed'] != true &&
        d['iteration'] == null &&
        (output.startsWith('The run crashed') ||
            output.startsWith('The worker running this session') ||
            output.startsWith('Commit or stash') ||
            output.startsWith('The cascade needs') ||
            output.startsWith('The tests already pass') ||
            output.startsWith("Couldn't set up the sandbox"));
  }

  static String? _tail(String? output) {
    if (output == null || output.isEmpty) return null;
    final lines = output.trimRight().split('\n');
    return lines.length <= 4 ? lines.join('\n') : lines.sublist(lines.length - 4).join('\n');
  }
}
