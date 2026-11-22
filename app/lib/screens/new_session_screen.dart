import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../main.dart';
import '../models.dart';
import 'sessions_screen.dart';

final modelsProvider = FutureProvider<List<ModelChoice>>((ref) => ref.watch(apiProvider).models());

/// A folder on this machine needs the backend running on it too; a phone or a remote backend clones a GitHub repo.
bool get _canPickFolder =>
    !kIsWeb && const {TargetPlatform.macOS, TargetPlatform.windows, TargetPlatform.linux}.contains(defaultTargetPlatform);

class NewSessionScreen extends ConsumerStatefulWidget {
  const NewSessionScreen({super.key});

  @override
  ConsumerState<NewSessionScreen> createState() => _NewSessionScreenState();
}

class _NewSessionScreenState extends ConsumerState<NewSessionScreen> {
  final _form = GlobalKey<FormState>();
  final _name = TextEditingController();
  final _folder = TextEditingController();
  final _repoUrl = TextEditingController();
  final _branch = TextEditingController();
  final _verify = TextEditingController(text: 'pytest -q');
  final _title = TextEditingController();
  final _spec = TextEditingController();
  final _maxCost = TextEditingController();
  late bool _useFolder = _canPickFolder;
  String? _model;
  double _maxIterations = 10;
  bool _cascade = false;
  bool _addTests = false;
  bool _busy = false;
  String? _error;

  Future<void> _pickFolder() async {
    final path = await getDirectoryPath(confirmButtonText: 'Use this repo');
    if (path != null) setState(() => _folder.text = path);
  }

  Future<void> _start() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final id = await ref.read(apiProvider).createSession(NewSession(
            name: _name.text.trim().isEmpty ? _title.text.trim() : _name.text.trim(),
            repoPath: _useFolder ? _folder.text.trim() : null,
            repoUrl: _useFolder ? null : _repoUrl.text.trim(),
            branch: _useFolder ? null : _branch.text.trim(),
            verifyCommand: _verify.text.trim(),
            title: _title.text.trim(),
            spec: _spec.text.trim(),
            model: _model!,
            maxIterations: _maxIterations.round(),
            maxCostUsd: double.tryParse(_maxCost.text.trim()),
            cascade: _cascade,
            addTests: _addTests,
          ));
      ref.invalidate(sessionsProvider);
      if (mounted) context.go('/sessions/$id');
    } catch (e) {
      setState(() => _error = '$e');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  String? _required(String? value) => (value == null || value.trim().isEmpty) ? 'Required' : null;

  @override
  Widget build(BuildContext context) {
    final models = ref.watch(modelsProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('New session')),
      body: Form(
        key: _form,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            if (_canPickFolder)
              SegmentedButton<bool>(
                segments: const [
                  ButtonSegment(value: true, label: Text('Folder on this machine'), icon: Icon(Icons.folder)),
                  ButtonSegment(value: false, label: Text('GitHub repo'), icon: Icon(Icons.link)),
                ],
                selected: {_useFolder},
                onSelectionChanged: (choice) => setState(() => _useFolder = choice.single),
              ),
            const SizedBox(height: 12),
            if (_useFolder)
              Row(children: [
                Expanded(
                  child: TextFormField(
                    controller: _folder,
                    decoration: const InputDecoration(
                        labelText: 'Repo folder', helperText: 'A git repo on the machine the backend runs on'),
                    validator: _required,
                  ),
                ),
                const SizedBox(width: 8),
                OutlinedButton.icon(onPressed: _pickFolder, icon: const Icon(Icons.folder_open), label: const Text('Choose')),
              ])
            else ...[
              TextFormField(
                controller: _repoUrl,
                decoration: const InputDecoration(labelText: 'GitHub repo URL', hintText: 'https://github.com/owner/repo'),
                validator: _required,
              ),
              TextFormField(controller: _branch, decoration: const InputDecoration(labelText: 'Branch (optional)')),
            ],
            TextFormField(
              controller: _verify,
              decoration: const InputDecoration(
                  labelText: 'Test command', helperText: 'Runs after every attempt; the session passes when it does'),
              validator: _required,
            ),
            const Divider(height: 32),
            TextFormField(controller: _title, decoration: const InputDecoration(labelText: 'Task'), validator: _required),
            TextFormField(
              controller: _spec,
              decoration: const InputDecoration(labelText: 'What should change, and how to tell it worked'),
              minLines: 3,
              maxLines: 8,
              validator: _required,
            ),
            TextFormField(controller: _name, decoration: const InputDecoration(labelText: 'Session name (optional)')),
            const Divider(height: 32),
            models.when(
              loading: () => const LinearProgressIndicator(),
              error: (e, _) => Text('Couldn\'t load the models: $e'),
              data: (choices) {
                _model ??= (choices.where((m) => m.id == 'claude-sonnet-5-5').firstOrNull ?? choices.first).id;
                return DropdownButtonFormField<String>(
                  initialValue: _model,
                  decoration: const InputDecoration(labelText: 'Model'),
                  items: [
                    for (final m in choices) DropdownMenuItem(value: m.id, child: Text('${m.name} (${m.provider})')),
                  ],
                  onChanged: (id) => setState(() => _model = id),
                );
              },
            ),
            const SizedBox(height: 12),
            Text('Up to ${_maxIterations.round()} attempts'),
            Slider(
              value: _maxIterations,
              min: 1,
              max: 50,
              divisions: 49,
              label: '${_maxIterations.round()}',
              onChanged: (v) => setState(() => _maxIterations = v),
            ),
            TextFormField(
              controller: _maxCost,
              decoration: const InputDecoration(
                  labelText: 'Spending cap in USD (optional)', helperText: 'Empty uses the server\'s cap'),
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              validator: (v) => (v == null || v.trim().isEmpty || (double.tryParse(v.trim()) ?? 0) > 0)
                  ? null
                  : 'A positive number',
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Cascade'),
              subtitle: const Text('A cheap model tries first; a reviewer checks its fix; this model redoes it only '
                  'if that fails. Needs a Claude model other than Haiku.'),
              value: _cascade,
              onChanged: (v) => setState(() => _cascade = v),
            ),
            SwitchListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Add tests'),
              subtitle: const Text('Ask the agent to write tests for its change'),
              value: _addTests,
              onChanged: (v) => setState(() => _addTests = v),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ],
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _busy || _model == null ? null : _start,
              icon: const Icon(Icons.play_arrow),
              label: const Text('Start session'),
            ),
          ],
        ),
      ),
    );
  }
}
