import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../models.dart';

/// Where a step stands in one session. A pipeline shown on its own has every step idle.
enum StepState { idle, active, passed, failed, skipped }

const _done = 'done';
const _nodeWidth = 176.0;
const _nodeHeight = 72.0;
const _columnGap = 84.0;
const _rowGap = 28.0;

/// A pipeline drawn left to right: each step in the column of its longest path from the start, an arrow per
/// outcome labelled with it, and a final "done". With [states], the session's progress: the running step pulses,
/// finished steps are green or red, and the arrows it took are drawn bold.
class PipelineMap extends StatefulWidget {
  const PipelineMap({
    super.key,
    required this.pipeline,
    this.states = const {},
    this.taken = const {},
    this.selected,
    this.onSelect,
    this.models = const {},
  });

  final Pipeline pipeline;
  final Map<String, StepState> states;

  /// Arrows the session took, as (from step, outcome).
  final Set<(String, String)> taken;
  final String? selected;
  final ValueChanged<String>? onSelect;

  /// What cheap and main stand for in this session, to show the real model on a step.
  final Map<String, String> models;

  @override
  State<PipelineMap> createState() => _PipelineMapState();
}

class _PipelineMapState extends State<PipelineMap> with SingleTickerProviderStateMixin {
  late final _pulse = AnimationController(vsync: this, duration: const Duration(milliseconds: 1100));

  @override
  void initState() {
    super.initState();
    _syncPulse();
  }

  @override
  void didUpdateWidget(PipelineMap old) {
    super.didUpdateWidget(old);
    _syncPulse();
  }

  /// Animate only while something runs, so an idle map costs nothing.
  void _syncPulse() {
    final active = widget.states.values.contains(StepState.active);
    if (active && !_pulse.isAnimating) _pulse.repeat(reverse: true);
    if (!active && _pulse.isAnimating) _pulse.stop();
  }

  @override
  void dispose() {
    _pulse.dispose();
    super.dispose();
  }

  /// Column = the longest path from the start (pipelines have no cycles), so every arrow points right.
  Map<String, Offset> _layout() {
    final p = widget.pipeline;
    final depth = <String, int>{p.start: 0};
    var changed = true;
    while (changed) {
      changed = false;
      for (final step in p.steps) {
        final d = depth[step.id];
        if (d == null) continue;
        for (final target in step.edges.values) {
          if ((depth[target] ?? -1) < d + 1) {
            depth[target] = d + 1;
            changed = true;
          }
        }
      }
    }
    final last = depth.values.fold(0, math.max);
    depth[_done] = math.max(depth[_done] ?? 0, last);
    final columns = <int, List<String>>{};
    for (final id in [...p.steps.map((s) => s.id), _done]) {
      if (depth.containsKey(id)) columns.putIfAbsent(depth[id]!, () => []).add(id);
    }
    final tallest = columns.values.fold(1, (n, ids) => math.max(n, ids.length));
    final height = tallest * _nodeHeight + (tallest - 1) * _rowGap;
    return {
      for (final MapEntry(key: col, value: ids) in columns.entries)
        for (final (row, id) in ids.indexed)
          id: Offset(
            col * (_nodeWidth + _columnGap),
            (height - (ids.length * _nodeHeight + (ids.length - 1) * _rowGap)) / 2 + row * (_nodeHeight + _rowGap),
          ),
    };
  }

  @override
  Widget build(BuildContext context) {
    final positions = _layout();
    final width = positions.values.fold(0.0, (w, o) => math.max(w, o.dx)) + _nodeWidth;
    final height = positions.values.fold(0.0, (h, o) => math.max(h, o.dy)) + _nodeHeight;
    final scheme = Theme.of(context).colorScheme;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.all(16),
      child: SizedBox(
        width: width,
        height: height,
        child: Stack(
          children: [
            Positioned.fill(
              child: CustomPaint(
                painter: _Arrows(
                  widget.pipeline,
                  positions,
                  widget.taken,
                  scheme,
                  Theme.of(context).textTheme.labelSmall!,
                ),
              ),
            ),
            for (final MapEntry(key: id, value: at) in positions.entries)
              Positioned(
                left: at.dx,
                top: at.dy,
                width: _nodeWidth,
                height: _nodeHeight,
                child: AnimatedBuilder(
                  animation: _pulse,
                  builder: (context, _) => _Node(
                    step: widget.pipeline.step(id),
                    state: id == _done
                        ? (widget.states[_done] ?? StepState.idle)
                        : (widget.states[id] ?? StepState.idle),
                    selected: widget.selected == id,
                    pulse: _pulse.value,
                    model: widget.models[widget.pipeline.step(id)?.model] ?? widget.pipeline.step(id)?.model,
                    onTap: id == _done || widget.onSelect == null ? null : () => widget.onSelect!(id),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _Node extends StatelessWidget {
  const _Node({
    required this.step,
    required this.state,
    required this.selected,
    required this.pulse,
    this.model,
    this.onTap,
  });
  final PipelineStep? step;
  final StepState state;
  final bool selected;
  final double pulse;
  final String? model;
  final VoidCallback? onTap;

  static IconData icon(String? kind) => switch (kind) {
    'scout' => Icons.travel_explore,
    'fix' => Icons.build_circle_outlined,
    'review' => Icons.rate_review_outlined,
    'command' => Icons.terminal,
    'approve' => Icons.how_to_reg_outlined,
    _ => Icons.flag_outlined,
  };

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (Color border, Color fill) = switch (state) {
      StepState.active => (Colors.blue, Colors.blue.withValues(alpha: 0.10 + 0.15 * pulse)),
      StepState.passed => (Colors.green, Colors.green.withValues(alpha: 0.14)),
      StepState.failed => (Colors.red, Colors.red.withValues(alpha: 0.14)),
      StepState.skipped => (scheme.outlineVariant, scheme.surface),
      StepState.idle => (scheme.outline, scheme.surfaceContainerHigh),
    };
    final faded = state == StepState.skipped;
    final text = Theme.of(context).textTheme;
    return Opacity(
      opacity: faded ? 0.45 : 1,
      child: Material(
        color: fill,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: selected ? scheme.primary : border, width: selected ? 3 : 1.5),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(12),
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Row(
              children: [
                Icon(icon(step?.kind), color: border),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(step?.id ?? 'done', style: text.titleSmall, overflow: TextOverflow.ellipsis),
                      if (step != null)
                        Text(
                          '${step!.kind} · $model',
                          style: text.bodySmall,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// One curve per outcome, from the right edge of a step to the left edge of the next, with the outcome's name.
class _Arrows extends CustomPainter {
  _Arrows(this.pipeline, this.positions, this.taken, this.scheme, this.label);
  final Pipeline pipeline;
  final Map<String, Offset> positions;
  final Set<(String, String)> taken;
  final ColorScheme scheme;
  final TextStyle label;

  static String short(String outcome) => switch (outcome) {
    'on_pass' => 'pass',
    'on_fail' => 'fail',
    'on_accept' => 'accept',
    'on_reject' => 'reject',
    _ => outcome,
  };

  @override
  void paint(Canvas canvas, Size size) {
    for (final step in pipeline.steps) {
      final from = positions[step.id];
      if (from == null) continue;
      final outgoing = step.edges.entries.toList();
      for (final (i, MapEntry(key: outcome, value: target)) in outgoing.indexed) {
        final to = positions[target];
        if (to == null) continue;
        // Spread a step's arrows down its right edge so two outcomes to one target stay apart
        final startY = from.dy + _nodeHeight * (i + 1) / (outgoing.length + 1);
        final start = Offset(from.dx + _nodeWidth, startY);
        final end = Offset(to.dx, to.dy + _nodeHeight / 2);
        final bold = taken.contains((step.id, outcome));
        final color = bold
            ? scheme.primary
            : (outcome == 'on_fail' || outcome == 'on_reject' ? scheme.error.withValues(alpha: 0.6) : scheme.outline);
        final paint = Paint()
          ..color = color
          ..style = PaintingStyle.stroke
          ..strokeWidth = bold ? 3 : 1.5;
        final bend = (end.dx - start.dx) / 2;
        final path = Path()
          ..moveTo(start.dx, start.dy)
          ..cubicTo(start.dx + bend, start.dy, end.dx - bend, end.dy, end.dx, end.dy);
        canvas.drawPath(path, paint);
        // Arrowhead
        canvas.drawPath(
          Path()
            ..moveTo(end.dx, end.dy)
            ..lineTo(end.dx - 9, end.dy - 5)
            ..lineTo(end.dx - 9, end.dy + 5)
            ..close(),
          Paint()..color = color,
        );
        final mid = path.computeMetrics().first;
        final at = mid.getTangentForOffset(mid.length / 2)!.position;
        final painter = TextPainter(
          text: TextSpan(
            text: short(outcome),
            style: label.copyWith(color: color, fontWeight: bold ? FontWeight.bold : null),
          ),
          textDirection: TextDirection.ltr,
        )..layout();
        final box = Rect.fromCenter(center: at, width: painter.width + 8, height: painter.height + 2);
        canvas.drawRRect(RRect.fromRectAndRadius(box, const Radius.circular(4)), Paint()..color = scheme.surface);
        painter.paint(canvas, at - Offset(painter.width / 2, painter.height / 2));
      }
    }
  }

  @override
  bool shouldRepaint(_Arrows old) => old.taken != taken || old.positions != positions || old.scheme != scheme;
}
