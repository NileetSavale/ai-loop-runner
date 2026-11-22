import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../config.dart';
import '../main.dart';
import '../models.dart';
import '../shell.dart';
import 'session_screen.dart';

final sessionsProvider = FutureProvider.autoDispose<List<Session>>((ref) => ref.watch(apiProvider).sessions());

/// The sessions list beside the selected session on a wide window; on a narrow one, the list or the session.
class SessionsPage extends StatelessWidget {
  const SessionsPage({super.key, this.selectedId});
  final String? selectedId;

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= wideLayout;
    final session = selectedId == null
        ? null
        : SessionScreen(key: ValueKey(selectedId), id: selectedId!, showBack: !wide);
    if (!wide) return session ?? SessionList(selectedId: selectedId);
    return Row(
      children: [
        SizedBox(width: 360, child: SessionList(selectedId: selectedId)),
        const VerticalDivider(width: 1),
        Expanded(child: session ?? const _NothingSelected()),
      ],
    );
  }
}

class _NothingSelected extends StatelessWidget {
  const _NothingSelected();

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.play_circle_outline, size: 48, color: Theme.of(context).colorScheme.outline),
          const SizedBox(height: 12),
          Text('Pick a session, or start one', style: text.titleMedium),
          const SizedBox(height: 4),
          Text('New session: ⌘N (Ctrl+N on Windows and Linux)', style: text.bodySmall),
        ],
      ),
    );
  }
}

enum _Filter { all, running, waiting, passed, failed }

/// Searchable by name, task or model, filtered by status, and refreshed every few seconds while a session runs.
class SessionList extends ConsumerStatefulWidget {
  const SessionList({super.key, this.selectedId});
  final String? selectedId;

  @override
  ConsumerState<SessionList> createState() => _SessionListState();
}

class _SessionListState extends ConsumerState<SessionList> {
  final _search = TextEditingController();
  _Filter _filter = _Filter.all;
  Timer? _poll;

  @override
  void dispose() {
    _poll?.cancel();
    _search.dispose();
    super.dispose();
  }

  /// Poll only while something runs, so an idle list costs nothing.
  void _keepFresh(List<Session> sessions) {
    final running = sessions.any((s) => s.running);
    if (running && _poll == null) {
      _poll = Timer.periodic(const Duration(seconds: 4), (_) => ref.invalidate(sessionsProvider));
    } else if (!running && _poll != null) {
      _poll!.cancel();
      _poll = null;
    }
  }

  bool _matches(Session s) {
    final status = switch (_filter) {
      _Filter.all => true,
      _Filter.running => s.running,
      _Filter.waiting => s.waitingFor != null,
      _Filter.passed => s.status == 'passed',
      _Filter.failed => s.status == 'failed' || s.status == 'stopped',
    };
    final query = _search.text.trim().toLowerCase();
    return status && (query.isEmpty || '${s.name} ${s.model} ${s.repoPath}'.toLowerCase().contains(query));
  }

  @override
  Widget build(BuildContext context) {
    final sessions = ref.watch(sessionsProvider);
    ref.listen(sessionsProvider, (_, next) => next.whenData(_keepFresh));
    return Scaffold(
      // A phone has no sidebar, so New session lives on the list
      floatingActionButton: MediaQuery.sizeOf(context).width < wideLayout
          ? FloatingActionButton(
              tooltip: 'New session',
              onPressed: () => context.go('/sessions/new'),
              child: const Icon(Icons.add),
            )
          : null,
      appBar: AppBar(
        // The list is a top-level page beside the session, so nothing to go back to
        automaticallyImplyLeading: false,
        title: const Text('Sessions'),
        actions: [
          IconButton(
            tooltip: 'Refresh (⌘R)',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(sessionsProvider),
          ),
        ],
      ),
      body: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: TextField(
              controller: _search,
              onChanged: (_) => setState(() {}),
              decoration: InputDecoration(
                isDense: true,
                prefixIcon: const Icon(Icons.search),
                hintText: 'Search sessions',
                border: const OutlineInputBorder(),
                suffixIcon: _search.text.isEmpty
                    ? null
                    : IconButton(icon: const Icon(Icons.clear), onPressed: () => setState(_search.clear)),
              ),
            ),
          ),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 12),
            child: Row(
              children: [
                for (final f in _Filter.values)
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ChoiceChip(
                      label: Text(switch (f) {
                        _Filter.all => 'All',
                        _Filter.running => 'Running',
                        _Filter.waiting => 'Needs you',
                        _Filter.passed => 'Passed',
                        _Filter.failed => 'Failed',
                      }),
                      selected: _filter == f,
                      onSelected: (_) => setState(() => _filter = f),
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          Expanded(
            child: sessions.when(
              skipLoadingOnRefresh: true,
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => _Problem(
                'Couldn\'t load sessions from ${Config.apiUrl}.\n$error',
                onRetry: () => ref.invalidate(sessionsProvider),
              ),
              data: (rows) {
                final shown = rows.where(_matches).toList();
                if (rows.isEmpty) return const Center(child: Text('No sessions yet. Start one with New session.'));
                if (shown.isEmpty) return const Center(child: Text('Nothing matches.'));
                return ListView.builder(
                  itemCount: shown.length,
                  itemBuilder: (context, i) => _SessionTile(shown[i], selected: shown[i].id == widget.selectedId),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _SessionTile extends StatelessWidget {
  const _SessionTile(this.session, {required this.selected});
  final Session session;
  final bool selected;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      selected: selected,
      selectedTileColor: Theme.of(context).colorScheme.secondaryContainer.withValues(alpha: 0.5),
      leading: session.waitingFor != null
          ? Tooltip(
              message: 'Waiting for your approval',
              child: Icon(Icons.how_to_reg, color: Colors.orange.shade700),
            )
          : StatusDot(session.status),
      title: Text(session.name.isEmpty ? session.id : session.name, maxLines: 1, overflow: TextOverflow.ellipsis),
      subtitle: Text(
        '${session.model} · ${session.totalIterations} attempt(s) · \$${session.totalCostUsd.toStringAsFixed(3)}',
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
      ),
      onTap: () => context.go('/sessions/${session.id}'),
    );
  }
}

class StatusDot extends StatelessWidget {
  const StatusDot(this.status, {super.key});
  final String status;

  @override
  Widget build(BuildContext context) {
    final color = switch (status) {
      'passed' => Colors.green,
      'failed' => Colors.red,
      'stopped' || 'cancelled' => Colors.grey,
      _ => Colors.blue,
    };
    return Icon(Icons.circle, size: 12, color: color);
  }
}

class _Problem extends StatelessWidget {
  const _Problem(this.message, {required this.onRetry});
  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            FilledButton(onPressed: onRetry, child: const Text('Try again')),
          ],
        ),
      ),
    );
  }
}
