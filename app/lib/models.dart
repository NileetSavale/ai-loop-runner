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
