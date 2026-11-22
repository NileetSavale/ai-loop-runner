import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../main.dart';
import '../models.dart';
import 'sessions_screen.dart';

/// One session, live: what it was asked, then every step as it happens. The saved events are loaded first and the
/// WebSocket adds the rest; after a dropped connection the saved events are reloaded, so nothing is missed.
class SessionScreen extends ConsumerStatefulWidget {
  const SessionScreen({super.key, required this.id});
  final String id;

  @override
  ConsumerState<SessionScreen> createState() => _SessionScreenState();
}

class _SessionScreenState extends ConsumerState<SessionScreen> {
  Session? _session;
  final List<SessionEvent> _events = [];
  final Set<int> _seen = {};
  StreamSubscription<SessionEvent>? _live;
  Timer? _retry;
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
    final session = await ref.read(apiProvider).session(widget.id);
    if (mounted) setState(() => _session = session);
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
        title: Text(session?.name ?? 'Session'),
        actions: [
          if (session?.running == true) ...[
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              child: Chip(label: Text(_connected ? 'live' : 'connecting')),
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
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    _Header(session),
                    const SizedBox(height: 16),
                    for (final event in _events) _EventTile(event),
                  ],
                ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header(this.session);
  final Session session;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            StatusDot(session.status),
            const SizedBox(width: 8),
            Text(session.status, style: text.titleMedium),
            const Spacer(),
            Text('\$${session.totalCostUsd.toStringAsFixed(3)}', style: text.titleMedium),
          ]),
          const SizedBox(height: 8),
          Text('${session.model} · attempt ${session.totalIterations} of ${session.maxIterations}'),
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

/// One event in words. Unknown kinds still show, by name, so a new backend event is never silently dropped.
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
      'cascade' => (Icons.alt_route, 'Cascade: ${d['step']} (${d['model'] ?? ''})', d['reason'] ?? d['why']),
      'iteration_start' => (Icons.play_arrow, 'Attempt ${d['iteration']}', null),
      'tool' => (Icons.handyman, 'Tool: ${d['tool']}', d['target']?.toString()),
      'file_changed' => (Icons.edit_document, 'Changed ${d['path']}', null),
      'usage' => (Icons.payments_outlined, 'Model call', '\$${(d['cost_usd'] as num?)?.toStringAsFixed(4) ?? '?'}'),
      'verify_output' => (
          d['passed'] == true ? Icons.check_circle : Icons.cancel,
          d['passed'] == true ? 'Tests passed' : 'Tests failed',
          _tail(d['output']?.toString()),
        ),
      'iteration_complete' => (Icons.flag_outlined, 'Attempt ${d['iteration_number'] ?? ''} finished', null),
      'session_complete' => (Icons.flag, 'Session ${d['status']}', d['error']?.toString()),
      _ => (Icons.info_outline, event.kind, null),
    };
    return ListTile(
      dense: true,
      leading: Icon(icon),
      title: Text(title),
      subtitle: body == null ? null : Text(body, maxLines: 6, overflow: TextOverflow.ellipsis),
    );
  }

  static String? _tail(String? output) {
    if (output == null || output.isEmpty) return null;
    final lines = output.trimRight().split('\n');
    return lines.length <= 6 ? lines.join('\n') : lines.sublist(lines.length - 6).join('\n');
  }
}
