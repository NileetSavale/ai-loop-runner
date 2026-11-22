import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../main.dart';

final _diffProvider = FutureProvider.autoDispose.family<String, String>((ref, id) => ref.watch(apiProvider).diff(id));

/// The session's changes as a patch: added lines green, removed red, file headers bold. Copy puts the whole patch
/// on the clipboard, ready for `git apply`.
class DiffScreen extends ConsumerWidget {
  const DiffScreen({super.key, required this.id});
  final String id;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final diff = ref.watch(_diffProvider(id));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Changes'),
        actions: [
          if (diff.value case final patch? when patch.isNotEmpty)
            IconButton(
              tooltip: 'Copy the patch',
              icon: const Icon(Icons.copy),
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: patch));
                if (context.mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Patch copied')));
                }
              },
            ),
        ],
      ),
      body: diff.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(padding: const EdgeInsets.all(24), child: Text('$e')),
        ),
        data: (patch) =>
            patch.trim().isEmpty ? const Center(child: Text('No changes yet.')) : _Patch(patch.split('\n')),
      ),
    );
  }
}

class _Patch extends StatelessWidget {
  const _Patch(this.lines);
  final List<String> lines;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    const mono = TextStyle(fontFamily: 'Menlo', fontFamilyFallback: ['Courier New', 'monospace'], fontSize: 12.5);
    return SelectionArea(
      child: ListView.builder(
        padding: const EdgeInsets.symmetric(vertical: 8),
        itemCount: lines.length,
        itemBuilder: (context, i) {
          final line = lines[i];
          final header = line.startsWith('diff --git') || line.startsWith('+++') || line.startsWith('---');
          final (Color? background, FontWeight weight) = switch (line) {
            _ when header => (scheme.surfaceContainerHighest, FontWeight.bold),
            _ when line.startsWith('@@') => (scheme.secondaryContainer, FontWeight.normal),
            _ when line.startsWith('+') => (Colors.green.withValues(alpha: 0.18), FontWeight.normal),
            _ when line.startsWith('-') => (Colors.red.withValues(alpha: 0.18), FontWeight.normal),
            _ => (null, FontWeight.normal),
          };
          return Container(
            color: background,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 1),
            child: Text(line.isEmpty ? ' ' : line, style: mono.copyWith(fontWeight: weight), softWrap: false),
          );
        },
      ),
    );
  }
}
