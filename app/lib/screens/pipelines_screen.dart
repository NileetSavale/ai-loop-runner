import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../main.dart';
import '../models.dart';
import '../widgets/pipeline_map.dart';

final pipelinesProvider = FutureProvider.autoDispose<List<Pipeline>>((ref) => ref.watch(apiProvider).pipelines());

/// One pipeline by name, for a session's live map.
final pipelineProvider =
    FutureProvider.autoDispose.family<Pipeline, String>((ref, name) => ref.watch(apiProvider).pipeline(name));

/// What each step kind does, in a sentence.
String explainKind(String kind) => switch (kind) {
      'scout' => 'Explores the repo read-only and notes the code that matters, for the next model.',
      'fix' => 'One model\'s verify-and-retry loop: edits the code and runs the tests until they pass or the '
          'attempts run out. With undo, it first resets the repo and hears what the earlier attempt tried.',
      'review' => 'A second model reads the fix\'s diff against the task and accepts or rejects it.',
      _ => kind,
    };

String explainModel(String model) => switch (model) {
      'cheap' => 'the cheap model',
      'main' => 'the session\'s own model',
      _ => model,
    };

class PipelinesScreen extends ConsumerStatefulWidget {
  const PipelinesScreen({super.key, this.initial});

  /// The pipeline to open with, e.g. one just saved.
  final String? initial;

  @override
  ConsumerState<PipelinesScreen> createState() => _PipelinesScreenState();
}

class _PipelinesScreenState extends ConsumerState<PipelinesScreen> {
  late String? _name = widget.initial;
  String? _step;

  Future<void> _delete(Pipeline p) async {
    final sure = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete ${p.name}?'),
        content: const Text('Its file is removed from backend/pipelines/. Sessions that ran it keep their history.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Delete')),
        ],
      ),
    );
    if (sure != true) return;
    try {
      await ref.read(apiProvider).deletePipeline(p.name);
      setState(() => _name = null);
      ref.invalidate(pipelinesProvider);
    } catch (e) {
      if (mounted) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Couldn\'t delete: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    final pipelines = ref.watch(pipelinesProvider);
    return Scaffold(
      appBar: AppBar(
        automaticallyImplyLeading: false,
        title: const Text('Pipelines'),
        actions: [
          IconButton(
              tooltip: 'Refresh', icon: const Icon(Icons.refresh), onPressed: () => ref.invalidate(pipelinesProvider)),
          TextButton.icon(
            onPressed: () => context.go('/pipelines/new'),
            icon: const Icon(Icons.add),
            label: const Text('New pipeline'),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: pipelines.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('Couldn\'t load pipelines: $e')),
        data: (all) {
          if (all.isEmpty) return const Center(child: Text('No pipelines in backend/pipelines/.'));
          final selected = all.firstWhere((p) => p.name == _name, orElse: () => all.first);
          return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            SizedBox(
              width: 260,
              child: ListView(children: [
                for (final p in all)
                  ListTile(
                    selected: p.name == selected.name,
                    leading: Icon(p.error == null ? Icons.account_tree_outlined : Icons.error_outline),
                    title: Text(p.name),
                    subtitle: Text(p.error == null ? '${p.steps.length} steps' : 'doesn\'t load'),
                    onTap: () => setState(() {
                      _name = p.name;
                      _step = null;
                    }),
                  ),
              ]),
            ),
            const VerticalDivider(width: 1),
            Expanded(
              child: _Detail(
                selected,
                step: _step,
                onStep: (id) => setState(() => _step = id),
                onDuplicate: () => context.go('/pipelines/new?from=${selected.name}'),
                onEdit: selected.builtIn ? null : () => context.go('/pipelines/${selected.name}/edit'),
                onDelete: selected.builtIn ? null : () => _delete(selected),
              ),
            ),
          ]);
        },
      ),
    );
  }
}

class _Detail extends StatelessWidget {
  const _Detail(this.pipeline,
      {required this.step, required this.onStep, required this.onDuplicate, this.onEdit, this.onDelete});
  final Pipeline pipeline;
  final String? step;
  final ValueChanged<String> onStep;
  final VoidCallback onDuplicate;

  /// Null for a built-in pipeline, which is read-only.
  final VoidCallback? onEdit;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    if (pipeline.error != null) {
      return Padding(padding: const EdgeInsets.all(24), child: SelectableText(pipeline.error!));
    }
    final chosen = step == null ? null : pipeline.step(step!);
    return ListView(padding: const EdgeInsets.all(16), children: [
      Row(children: [
        Expanded(child: Text(pipeline.name, style: text.headlineSmall)),
        if (pipeline.builtIn) const Chip(label: Text('built in, read-only')),
        const SizedBox(width: 8),
        OutlinedButton.icon(onPressed: onDuplicate, icon: const Icon(Icons.copy), label: const Text('Duplicate')),
        if (onEdit != null) ...[
          const SizedBox(width: 8),
          FilledButton.icon(onPressed: onEdit, icon: const Icon(Icons.edit_outlined), label: const Text('Edit')),
        ],
        if (onDelete != null)
          IconButton(tooltip: 'Delete', icon: const Icon(Icons.delete_outline), onPressed: onDelete),
      ]),
      if (pipeline.description.isNotEmpty) ...[const SizedBox(height: 6), Text(pipeline.description)],
      const SizedBox(height: 12),
      Card(child: PipelineMap(pipeline: pipeline, selected: step, onSelect: onStep)),
      const SizedBox(height: 12),
      if (chosen == null)
        Text('Click a step to see what it does.', style: text.bodySmall)
      else
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text('${chosen.id}  ·  ${chosen.kind}', style: text.titleMedium),
              const SizedBox(height: 6),
              Text(explainKind(chosen.kind)),
              const SizedBox(height: 6),
              Text('Model: ${explainModel(chosen.model)}'),
              for (final MapEntry(:key, :value) in chosen.options.entries) Text('$key: $value'),
              const SizedBox(height: 6),
              for (final MapEntry(key: outcome, value: target) in chosen.edges.entries)
                Text('${outcome.replaceFirst('on_', '')} → $target'),
            ]),
          ),
        ),
    ]);
  }
}
