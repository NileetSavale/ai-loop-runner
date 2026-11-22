import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../main.dart';
import '../models.dart';
import '../shell.dart';
import '../widgets/pipeline_map.dart';
import 'new_session_screen.dart';
import 'pipelines_screen.dart';

const _kinds = ['scout', 'fix', 'review', 'command', 'approve'];
const _outcomes = {
  'scout': ['next'],
  'fix': ['on_pass', 'on_fail'],
  'review': ['on_accept', 'on_reject'],
  'command': ['on_pass', 'on_fail'],
  'approve': ['on_accept', 'on_reject'],
};

/// One step while it's being edited.
class _Draft {
  _Draft({
    required this.id,
    required this.kind,
    this.model = 'main',
    Map<String, String>? edges,
    Map<String, dynamic>? options,
  }) : edges = edges ?? {},
       options = options ?? {};

  factory _Draft.of(PipelineStep s) =>
      _Draft(id: s.id, kind: s.kind, model: s.model, edges: Map.of(s.edges), options: Map.of(s.options));

  String id;
  String kind;
  String model;
  Map<String, String> edges;
  Map<String, dynamic> options;

  /// Keep only this kind's outcomes and options, defaulting a new outcome to done.
  void fitKind() {
    edges = {for (final o in _outcomes[kind]!) o: edges[o] ?? 'done'};
    options = {
      if (kind == 'scout') 'budget_usd': options['budget_usd'] ?? 0.05,
      if (kind == 'fix' && options['undo'] == true) 'undo': true,
      if (kind == 'command') 'run': options['run'] ?? '',
      if (kind == 'approve') 'timeout_hours': options['timeout_hours'] ?? 24,
    };
    // Steps that run no model
    if (kind == 'command' || kind == 'approve') model = '';
    if (kind != 'command' && kind != 'approve' && model.isEmpty) model = 'main';
  }

  Map<String, dynamic> toYamlStep() => {'kind': kind, if (model.isNotEmpty) 'model': model, ...options, ...edges};

  Map<String, dynamic> toJson() => {'id': id, 'kind': kind, 'model': model, 'edges': edges, 'options': options};
}

/// Build or change a pipeline: steps on the left, the map redrawn on the right as you edit. Saving asks the backend,
/// which refuses a pipeline it couldn't run (an arrow to nowhere, a step nothing reaches, a cycle) and says why.
class PipelineEditorScreen extends ConsumerStatefulWidget {
  const PipelineEditorScreen({super.key, this.from, this.editing = false});

  /// The pipeline to start from: edited in place, or copied when it's built in or a new one is made from it.
  final String? from;
  final bool editing;

  @override
  ConsumerState<PipelineEditorScreen> createState() => _PipelineEditorScreenState();
}

class _PipelineEditorScreenState extends ConsumerState<PipelineEditorScreen> {
  final _name = TextEditingController();
  final _description = TextEditingController();
  final _scroll = ScrollController();
  List<_Draft> _steps = [];
  String _start = '';
  bool _loaded = false;
  bool _saving = false;
  String? _error;
  String? _selected;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    if (widget.from == null) {
      _steps = [
        _Draft(id: 'fix', kind: 'fix', model: 'main', edges: {'on_pass': 'done', 'on_fail': 'done'}),
      ];
      _start = 'fix';
    } else {
      final p = await ref.read(apiProvider).pipeline(widget.from!);
      _steps = [for (final s in p.steps) _Draft.of(s)];
      _start = p.start;
      _description.text = p.description;
      _name.text = widget.editing ? p.name : '${p.name}-copy';
    }
    if (mounted) setState(() => _loaded = true);
  }

  Pipeline get _preview => Pipeline.fromJson({
    'name': _name.text,
    'start': _start,
    'steps': [for (final s in _steps) s.toJson()],
  });

  /// The step ids an arrow can point to.
  List<String> get _targets => [for (final s in _steps) s.id, 'done'];

  void _rename(_Draft step, String id) {
    final old = step.id;
    setState(() {
      step.id = id;
      for (final s in _steps) {
        s.edges.updateAll((_, target) => target == old ? id : target);
      }
      if (_start == old) _start = id;
      if (_selected == old) _selected = id;
    });
  }

  void _add() {
    var n = _steps.length + 1;
    while (_steps.any((s) => s.id == 'step$n')) {
      n++;
    }
    setState(() {
      final step = _Draft(id: 'step$n', kind: 'command', options: {'run': ''})..fitKind();
      _steps.add(step);
      _selected = step.id;
    });
    // The new step's card is last: bring it into view to fill it in
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) {
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    _name.dispose();
    _description.dispose();
    super.dispose();
  }

  void _remove(_Draft step) {
    setState(() {
      _steps.remove(step);
      for (final s in _steps) {
        s.edges.updateAll((_, target) => target == step.id ? 'done' : target);
      }
      if (_start == step.id) _start = _steps.isEmpty ? '' : _steps.first.id;
    });
  }

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final name = _name.text.trim();
      await ref.read(apiProvider).savePipeline(name, {
        'name': name,
        if (_description.text.trim().isNotEmpty) 'description': _description.text.trim(),
        'start': _start,
        'steps': {for (final s in _steps) s.id: s.toYamlStep()},
      });
      ref.invalidate(pipelinesProvider);
      ref.invalidate(pipelineProvider(name));
      if (mounted) context.go('/pipelines?name=$name');
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final models = ref.watch(modelsProvider).value ?? const <ModelChoice>[];
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.editing ? 'Edit ${widget.from}' : 'New pipeline'),
        actions: [
          TextButton.icon(onPressed: _add, icon: const Icon(Icons.add), label: const Text('Add step')),
          const SizedBox(width: 8),
          FilledButton.icon(
            onPressed: _saving ? null : _save,
            icon: const Icon(Icons.save_outlined),
            label: const Text('Save'),
          ),
          const SizedBox(width: 12),
        ],
      ),
      body: _layout(context, models),
    );
  }

  /// Steps beside the map on a wide window; on a phone, the map on top and the steps scrolling under it.
  Widget _layout(BuildContext context, List<ModelChoice> models) {
    final map = Card(
      child: _start.isEmpty
          ? const Padding(padding: EdgeInsets.all(24), child: Text('Add a step to start.'))
          : PipelineMap(pipeline: _preview, selected: _selected, onSelect: (id) => setState(() => _selected = id)),
    );
    final form = ListView(
      controller: _scroll,
      padding: const EdgeInsets.all(16),
      children: [
        TextField(
          controller: _name,
          enabled: !widget.editing,
          decoration: const InputDecoration(
            labelText: 'Name',
            helperText: 'Lowercase letters, digits and hyphens; also the file name',
          ),
          onChanged: (_) => setState(() {}),
        ),
        TextField(
          controller: _description,
          decoration: const InputDecoration(labelText: 'Description'),
          maxLines: 2,
        ),
        const SizedBox(height: 8),
        DropdownButtonFormField<String>(
          initialValue: _steps.any((s) => s.id == _start) ? _start : null,
          decoration: const InputDecoration(labelText: 'Starts at'),
          items: [for (final s in _steps) DropdownMenuItem(value: s.id, child: Text(s.id))],
          onChanged: (id) => setState(() => _start = id!),
        ),
        const SizedBox(height: 12),
        for (final step in _steps)
          _StepCard(
            key: ObjectKey(step),
            step: step,
            selected: step.id == _selected,
            targets: _targets.where((t) => t != step.id).toList(),
            models: models,
            onChanged: () => setState(() {}),
            onRename: (id) => _rename(step, id),
            onRemove: _steps.length > 1 ? () => _remove(step) : null,
          ),
        if (_error != null) ...[
          const SizedBox(height: 12),
          Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
        ],
      ],
    );
    if (MediaQuery.sizeOf(context).width < wideLayout) {
      return Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(8, 8, 8, 0),
            child: SizedBox(height: 200, child: map),
          ),
          Expanded(child: form),
        ],
      );
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(width: 440, child: form),
        const VerticalDivider(width: 1),
        Expanded(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text('Map', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 4),
              Text('Redrawn as you edit. Click a step to find its card.', style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 8),
              map,
            ],
          ),
        ),
      ],
    );
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard({
    super.key,
    required this.step,
    required this.selected,
    required this.targets,
    required this.models,
    required this.onChanged,
    required this.onRename,
    this.onRemove,
  });

  final _Draft step;
  final bool selected;
  final List<String> targets;
  final List<ModelChoice> models;
  final VoidCallback onChanged;
  final ValueChanged<String> onRename;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final modelIds = ['cheap', 'main', for (final m in models) m.id];
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: selected ? scheme.primary : scheme.outlineVariant, width: selected ? 2 : 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: TextFormField(
                    initialValue: step.id,
                    decoration: const InputDecoration(labelText: 'Step id', isDense: true),
                    onChanged: (v) => onRename(v.trim()),
                  ),
                ),
                const SizedBox(width: 12),
                SizedBox(
                  width: 130,
                  child: DropdownButtonFormField<String>(
                    initialValue: step.kind,
                    decoration: const InputDecoration(labelText: 'Kind', isDense: true),
                    items: [for (final k in _kinds) DropdownMenuItem(value: k, child: Text(k))],
                    onChanged: (k) {
                      step
                        ..kind = k!
                        ..fitKind();
                      onChanged();
                    },
                  ),
                ),
                IconButton(tooltip: 'Remove step', icon: const Icon(Icons.delete_outline), onPressed: onRemove),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Text(explainKind(step.kind), style: Theme.of(context).textTheme.bodySmall),
            ),
            if (step.kind != 'command' && step.kind != 'approve')
              DropdownButtonFormField<String>(
                initialValue: modelIds.contains(step.model) ? step.model : null,
                decoration: const InputDecoration(labelText: 'Model', isDense: true),
                items: [for (final id in modelIds) DropdownMenuItem(value: id, child: Text(explainModel(id)))],
                onChanged: (m) {
                  step.model = m!;
                  onChanged();
                },
              ),
            if (step.kind == 'command')
              TextFormField(
                initialValue: step.options['run'] as String? ?? '',
                decoration: const InputDecoration(
                  labelText: 'Command',
                  hintText: 'ruff check .',
                  helperText: 'Runs in the repo; passes on exit 0',
                ),
                style: const TextStyle(fontFamily: 'Menlo', fontFamilyFallback: ['Courier New', 'monospace']),
                onChanged: (v) {
                  step.options['run'] = v;
                  onChanged();
                },
              ),
            if (step.kind == 'approve')
              TextFormField(
                initialValue: '${step.options['timeout_hours'] ?? 24}',
                decoration: const InputDecoration(
                  labelText: 'Time limit (hours)',
                  helperText: 'No answer by then counts as a rejection',
                  isDense: true,
                ),
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                onChanged: (v) {
                  step.options['timeout_hours'] = double.tryParse(v) ?? 24;
                  onChanged();
                },
              ),
            if (step.kind == 'scout')
              TextFormField(
                initialValue: '${step.options['budget_usd'] ?? 0.05}',
                decoration: const InputDecoration(labelText: 'Budget (USD)', isDense: true),
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                onChanged: (v) {
                  step.options['budget_usd'] = double.tryParse(v) ?? 0.05;
                  onChanged();
                },
              ),
            if (step.kind == 'fix')
              CheckboxListTile(
                contentPadding: EdgeInsets.zero,
                dense: true,
                title: const Text('Undo the earlier attempt first'),
                subtitle: const Text('Reset the repo and tell this model what was tried'),
                value: step.options['undo'] == true,
                onChanged: (v) {
                  if (v == true) {
                    step.options['undo'] = true;
                  } else {
                    step.options.remove('undo');
                  }
                  onChanged();
                },
              ),
            const SizedBox(height: 4),
            for (final outcome in _outcomes[step.kind]!)
              Row(
                children: [
                  SizedBox(width: 90, child: Text(outcome.replaceFirst('on_', ''))),
                  const Icon(Icons.arrow_right_alt, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: DropdownButton<String>(
                      isExpanded: true,
                      value: targets.contains(step.edges[outcome]) ? step.edges[outcome] : null,
                      hint: const Text('pick a step'),
                      items: [for (final t in targets) DropdownMenuItem(value: t, child: Text(t))],
                      onChanged: (t) {
                        step.edges[outcome] = t!;
                        onChanged();
                      },
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
