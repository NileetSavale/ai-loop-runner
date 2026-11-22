import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../config.dart';
import '../main.dart';
import '../models.dart';

final sessionsProvider = FutureProvider.autoDispose<List<Session>>((ref) => ref.watch(apiProvider).sessions());

class SessionsScreen extends ConsumerWidget {
  const SessionsScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final sessions = ref.watch(sessionsProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Sessions'),
        actions: [
          IconButton(tooltip: 'API keys', icon: const Icon(Icons.key), onPressed: () => context.go('/keys')),
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(sessionsProvider),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => context.go('/sessions/new'),
        icon: const Icon(Icons.add),
        label: const Text('New session'),
      ),
      body: sessions.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => _Problem(
          'Couldn\'t load sessions from ${Config.apiUrl}.\n$error',
          onRetry: () => ref.invalidate(sessionsProvider),
        ),
        data: (rows) => rows.isEmpty
            ? const Center(child: Text('No sessions yet. Start one with New session.'))
            : RefreshIndicator(
                onRefresh: () => ref.refresh(sessionsProvider.future),
                child: ListView.separated(
                  itemCount: rows.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (context, i) => _SessionTile(rows[i]),
                ),
              ),
      ),
    );
  }
}

class _SessionTile extends StatelessWidget {
  const _SessionTile(this.session);
  final Session session;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: StatusDot(session.status),
      title: Text(session.name.isEmpty ? session.id : session.name),
      subtitle: Text('${session.model} · ${session.totalIterations} attempt(s) · '
          '\$${session.totalCostUsd.toStringAsFixed(3)}'),
      trailing: Text(session.status),
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
        child: Column(mainAxisSize: MainAxisSize.min, children: [
          Text(message, textAlign: TextAlign.center),
          const SizedBox(height: 12),
          FilledButton(onPressed: onRetry, child: const Text('Try again')),
        ]),
      ),
    );
  }
}
