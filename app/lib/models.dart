/// The backend's JSON as the screens read it.
class Session {
  Session.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      name = json['name'] as String? ?? '',
      status = json['status'] as String? ?? 'running',
      model = json['model'] as String? ?? '',
      repoPath = json['repo_path'] as String? ?? '',
      totalIterations = json['total_iterations'] as int? ?? 0,
      maxIterations = json['max_iterations'] as int? ?? 0,
      totalCostUsd = (json['total_cost_usd'] as num?)?.toDouble() ?? 0,
      createdAt = DateTime.tryParse(json['created_at'] as String? ?? ''),
      waitingFor = json['waiting_for'] as String?,
      spec = (json['task'] as Map<String, dynamic>?)?['spec'] as String?;

  final String id;
  final String name;
  final String status;
  final String model;
  final String repoPath;
  final int totalIterations;
  final int maxIterations;
  final double totalCostUsd;
  final DateTime? createdAt;

  /// The approve step the session is waiting on (only in GET /sessions), or null.
  final String? waitingFor;

  /// Only in GET /sessions/{id}.
  final String? spec;

  bool get running => status == 'running';
}

/// One step of a session: saved (GET /sessions/{id}/events, the data flattened beside id and kind) or live (the
/// WebSocket's {"event", "data"}). Both carry the saved id, so a live event already loaded is shown once.
class SessionEvent {
  SessionEvent(this.kind, this.data) : id = data['id'] as int?;

  factory SessionEvent.saved(Map<String, dynamic> json) =>
      SessionEvent(json['kind'] as String? ?? '', Map.of(json)..remove('kind'));

  factory SessionEvent.live(Map<String, dynamic> json) =>
      SessionEvent(json['event'] as String? ?? '', (json['data'] as Map<String, dynamic>?) ?? {});

  final int? id;
  final String kind;
  final Map<String, dynamic> data;
}

/// What POST /sessions takes. Exactly one of repoPath (a folder on the backend's machine) and repoUrl is set.
class NewSession {
  NewSession({
    required this.name,
    required this.verifyCommand,
    required this.title,
    required this.spec,
    required this.model,
    this.repoPath,
    this.repoUrl,
    this.branch,
    this.maxIterations = 10,
    this.maxCostUsd,
    this.cascade = false,
    this.addTests = false,
    this.pipeline,
  });

  final String name;
  final String verifyCommand;
  final String title;
  final String spec;
  final String model;
  final String? repoPath;
  final String? repoUrl;
  final String? branch;
  final int maxIterations;
  final double? maxCostUsd;
  final bool cascade;
  final bool addTests;

  /// A pipeline in backend/pipelines/ to run instead of one model's loop.
  final String? pipeline;

  Map<String, dynamic> toJson() => {
    'name': name,
    if (repoPath != null) 'repo_path': repoPath,
    if (repoUrl != null) 'repo_url': repoUrl,
    if (branch != null && branch!.isNotEmpty) 'branch': branch,
    'verify_command': verifyCommand,
    'max_iterations': maxIterations,
    if (maxCostUsd != null) 'max_cost_usd': maxCostUsd,
    'cascade': cascade,
    'add_tests': addTests,
    if (pipeline != null) 'pipeline': pipeline,
    'model': model,
    'task': {'title': title, 'spec': spec, 'files_context': <String>[]},
  };
}

class ModelChoice {
  const ModelChoice(this.id, this.name, this.provider);
  final String id;
  final String name;
  final String provider;
}

class SavedKey {
  SavedKey.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      provider = json['provider'] as String,
      label = json['label'] as String? ?? '';

  final String id;
  final String provider;
  final String label;
}

/// A pipeline's step (backend/pipelines/*.yaml, core/pipeline.py): its kind, its model, and where each outcome leads.
class PipelineStep {
  PipelineStep.fromJson(Map<String, dynamic> json)
    : id = json['id'] as String,
      kind = json['kind'] as String,
      model = json['model'] as String,
      edges = (json['edges'] as Map<String, dynamic>).cast<String, String>(),
      options = (json['options'] as Map<String, dynamic>?) ?? const {};

  final String id;
  final String kind;
  final String model;
  final Map<String, String> edges;
  final Map<String, dynamic> options;
}

class Pipeline {
  Pipeline.fromJson(Map<String, dynamic> json)
    : name = json['name'] as String,
      description = json['description'] as String? ?? '',
      start = json['start'] as String? ?? '',
      error = json['error'] as String?,
      builtIn = json['built_in'] as bool? ?? false,
      steps = [for (final s in (json['steps'] as List?) ?? const []) PipelineStep.fromJson(s as Map<String, dynamic>)];

  final String name;
  final String description;
  final String start;

  /// Set when the file doesn't load; the backend says why.
  final String? error;

  /// Shipped with Loop Runner and read-only (the study's cascade); copy it to change it.
  final bool builtIn;
  final List<PipelineStep> steps;

  PipelineStep? step(String id) => steps.where((s) => s.id == id).firstOrNull;
}
