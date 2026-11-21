"""Pipelines: a session's steps written as data instead of code, so which model does which step, and what happens
next on each outcome, can change without touching the engine.

A pipeline is a YAML file in backend/pipelines/:

    name: reviewed-cascade
    start: scout
    steps:
      scout:   {kind: scout, model: cheap, budget_usd: 0.05, next: cheap}
      cheap:   {kind: fix, model: cheap, on_pass: review, on_fail: escalated}
      review:  {kind: review, model: claude-sonnet-5-5, on_accept: done, on_reject: escalated}
      escalated: {kind: fix, model: main, undo: true, on_pass: done, on_fail: done}

Step kinds and the outcomes each one leads on:
- scout: a cheap model notes which code matters; `next`.
- fix: one model's verify-and-retry loop (run_loop); `on_pass` / `on_fail`. `undo: true` first resets the repo to the
  commit the session started from and hands the model what the earlier attempt tried.
- review: a second model reads the last fix's diff against the task; `on_accept` / `on_reject`.

`model` is a model id, or `cheap` (the cheap model) or `main` (the session's own model). `done` ends the session.
A pipeline is checked when it is loaded: unknown kinds, models or fields, an edge to a missing step, a step nothing
reaches, and a cycle are refused with the reason. Cycles wait for a step budget, so every pipeline ends.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from providers.base import SUPPORTED_MODELS

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
DONE = "done"
ALIASES = ("cheap", "main")
OUTCOMES = {"scout": ("next",), "fix": ("on_pass", "on_fail"), "review": ("on_accept", "on_reject")}
OPTIONS = {"scout": {"budget_usd"}, "fix": {"undo"}, "review": set()}
_MODELS = {m["id"] for models in SUPPORTED_MODELS.values() for m in models}


class PipelineError(ValueError):
    pass


@dataclass(frozen=True)
class Step:
    id: str
    kind: str
    model: str
    edges: dict[str, str]
    options: dict = field(default_factory=dict)

    def after(self, outcome: str) -> str:
        """The step that follows this outcome, or "done"."""
        return self.edges[outcome]


@dataclass(frozen=True)
class Pipeline:
    name: str
    start: str
    steps: dict[str, Step]


def parse(document: dict, source: str = "pipeline") -> Pipeline:
    """Build a pipeline from its YAML document, refusing anything the engine can't run as written."""
    def refuse(reason: str):
        raise PipelineError(f"{source}: {reason}")

    if not isinstance(document, dict):
        refuse("expected a mapping with name, start and steps")
    unknown = set(document) - {"name", "start", "steps", "description"}
    if unknown:
        refuse(f"unknown fields {sorted(unknown)}")
    name, start, raw = document.get("name"), document.get("start"), document.get("steps")
    if not isinstance(name, str) or not name:
        refuse("name is missing")
    if not isinstance(raw, dict) or not raw:
        refuse("steps is missing or empty")
    if DONE in raw:
        refuse(f'"{DONE}" ends a pipeline, so no step may be called that')

    steps: dict[str, Step] = {}
    for step_id, spec in raw.items():
        if not isinstance(spec, dict):
            refuse(f"step {step_id!r} is not a mapping")
        kind = spec.get("kind")
        if kind not in OUTCOMES:
            refuse(f"step {step_id!r} has kind {kind!r}; the kinds are {sorted(OUTCOMES)}")
        model = spec.get("model")
        if model not in ALIASES and model not in _MODELS:
            refuse(f"step {step_id!r} has model {model!r}: use a supported model id, or cheap or main")
        allowed = {"kind", "model", *OUTCOMES[kind], *OPTIONS[kind]}
        extra = set(spec) - allowed
        if extra:
            refuse(f"step {step_id!r} ({kind}) has unknown fields {sorted(extra)}; it takes {sorted(allowed)}")
        missing = [outcome for outcome in OUTCOMES[kind] if outcome not in spec]
        if missing:
            refuse(f"step {step_id!r} ({kind}) doesn't say where {missing} lead")
        steps[step_id] = Step(step_id, kind, model, {o: spec[o] for o in OUTCOMES[kind]},
                              {k: spec[k] for k in OPTIONS[kind] if k in spec})

    if start not in steps:
        refuse(f"start {start!r} is not a step")
    for step in steps.values():
        for outcome, target in step.edges.items():
            if target != DONE and target not in steps:
                refuse(f"step {step.id!r} sends {outcome} to {target!r}, which is not a step or {DONE}")

    # Every step reachable from start, and no path that comes back to a step it left
    reached: set[str] = set()

    def walk(step_id: str, path: tuple[str, ...]):
        if step_id == DONE:
            return
        if step_id in path:
            refuse(f"steps form a cycle: {' -> '.join(path[path.index(step_id):] + (step_id,))}")
        reached.add(step_id)
        for target in steps[step_id].edges.values():
            walk(target, path + (step_id,))

    walk(start, ())
    unreached = sorted(set(steps) - reached)
    if unreached:
        refuse(f"nothing leads to steps {unreached}")
    return Pipeline(name, start, steps)


def load(name: str) -> Pipeline:
    """A pipeline from backend/pipelines/<name>.yaml."""
    path = PIPELINES / f"{name}.yaml"
    if not path.is_file():
        raise PipelineError(f"no pipeline {name!r} in {PIPELINES}")
    return parse(yaml.safe_load(path.read_text()), path.name)


def resolve(model: str, cheap: str, main: str) -> str:
    return {"cheap": cheap, "main": main}.get(model, model)
