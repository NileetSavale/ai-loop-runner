import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../config.dart';
import '../main.dart';

const _providers = ['anthropic', 'openai', 'google', 'mistral'];

final _keysProvider = FutureProvider.autoDispose((ref) => ref.watch(apiProvider).keys());

/// The user's own model keys, saved encrypted on the backend. In local mode there are no accounts to save them to,
/// so the key goes in backend/.env instead.
class KeysScreen extends ConsumerWidget {
  const KeysScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Scaffold(
      appBar: AppBar(title: const Text('API keys')),
      floatingActionButton: Config.loginEnabled
          ? FloatingActionButton.extended(
              onPressed: () => _add(context, ref),
              icon: const Icon(Icons.add),
              label: const Text('Add key'),
            )
          : null,
      body: Config.loginEnabled ? _Saved() : const _LocalMode(),
    );
  }

  Future<void> _add(BuildContext context, WidgetRef ref) async {
    var provider = _providers.first;
    final key = TextEditingController();
    final saved = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Add a key'),
        content: StatefulBuilder(
          builder: (context, setState) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                initialValue: provider,
                decoration: const InputDecoration(labelText: 'Provider'),
                items: [for (final p in _providers) DropdownMenuItem(value: p, child: Text(p))],
                onChanged: (p) => setState(() => provider = p!),
              ),
              TextField(
                controller: key,
                decoration: const InputDecoration(labelText: 'Key'),
                obscureText: true,
              ),
            ],
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Save')),
        ],
      ),
    );
    if (saved != true || key.text.trim().isEmpty) return;
    try {
      await ref.read(apiProvider).addKey(provider, key.text.trim());
      ref.invalidate(_keysProvider);
    } catch (e) {
      if (context.mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Couldn\'t save: $e')));
    }
  }
}

class _Saved extends ConsumerWidget {
  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref
        .watch(_keysProvider)
        .when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Center(child: Text('$e')),
          data: (keys) => keys.isEmpty
              ? const Center(child: Text('No keys yet. Sessions use the server\'s key until you add one.'))
              : ListView(
                  children: [
                    for (final k in keys)
                      ListTile(
                        leading: const Icon(Icons.key),
                        title: Text(k.provider),
                        subtitle: k.label.isEmpty ? null : Text(k.label),
                        trailing: IconButton(
                          tooltip: 'Remove',
                          icon: const Icon(Icons.delete_outline),
                          onPressed: () async {
                            await ref.read(apiProvider).deleteKey(k.id);
                            ref.invalidate(_keysProvider);
                          },
                        ),
                      ),
                  ],
                ),
        );
  }
}

class _LocalMode extends StatelessWidget {
  const _LocalMode();

  @override
  Widget build(BuildContext context) {
    return const Center(
      child: Padding(
        padding: EdgeInsets.all(24),
        child: Text(
          'Local mode: there are no accounts, so keys aren\'t saved here.\n\n'
          'Put your model key in backend/.env (for example ANTHROPIC_API_KEY=...) and restart the backend.',
          textAlign: TextAlign.center,
        ),
      ),
    );
  }
}
