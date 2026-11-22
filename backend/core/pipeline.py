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
- command: runs `run` (a shell command: a linter, a type checker, more tests) in the repo the way the session's own
  test command runs, in its sandbox if it has one; `on_pass` / `on_fail` by the exit code. It takes no model.

`model` is a model id, or `cheap` (the cheap model) or `main` (the session's own model). `done` ends the session.
A pipeline is checked when it is loaded: unknown kinds, models or fields, an edge to a missing step, a step nothing
reaches, and a cycle are refused with the reason. Cycles wait for a step budget, so every pipeline ends.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from providers.base import SUPPORTED_MODELS

PIPELINES = Path(__file__).resolve().parent.parent / "pipelines"
DONE = "done"
ALIASES = ("cheap", "main")
OUTCOMES = {"scout": ("next",), "fix": ("on_pass", "on_fail"), "review": ("on_accept", "on_reject"),
            "command": ("on_pass", "on_fail")}
OPTIONS = {"scout": {"budget_usd"}, "fix": {"undo"}, "review": set(), "command": {"run"}}
NO_MODEL = {"command"}  # kinds that run no model
BUILT_IN = {"reviewed-cascade"}  # the study's pipeline: read-only, so its results stay reproducible
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
    description: str = ""

    def to_json(self) -> dict:
        return {"name": self.name, "description": self.description, "start": self.start,
                "built_in": self.name in BUILT_IN,
                "steps": [{"id": s.id, "kind": s.kind, "model": s.model, "edges": s.edges, "options": s.options}
                          for s in self.steps.values()]}


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
        model = spec.get("model", "")
        if kind in NO_MODEL:
            if model:
                refuse(f"step {step_id!r} ({kind}) runs no model, so it takes none")
        elif model not in ALIASES and model not in _MODELS:
            refuse(f"step {step_id!r} has model {model!r}: use a supported model id, or cheap or main")
        if kind == "command" and not (isinstance(spec.get("run"), str) and spec["run"].strip()):
            refuse(f"step {step_id!r} (command) needs `run`: the shell command to run in the repo")
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
    description = document.get("description") or ""
    return Pipeline(name, start, steps, description.strip() if isinstance(description, str) else "")


def load(name: str) -> Pipeline:
    """A pipeline from backend/pipelines/<name>.yaml."""
    path = PIPELINES / f"{name}.yaml"
    if not path.is_file():
        raise PipelineError(f"no pipeline {name!r} in {PIPELINES}")
    return parse(yaml.safe_load(path.read_text()), path.name)


NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def document(pipeline: Pipeline) -> dict:
    """A pipeline as its YAML file holds it."""
    steps = {}
    for step in pipeline.steps.values():
        spec = {"kind": step.kind, **({"model": step.model} if step.model else {}), **step.options, **step.edges}
        steps[step.id] = spec
    return {"name": pipeline.name, **({"description": pipeline.description} if pipeline.description else {}),
            "start": pipeline.start, "steps": steps}


def save(name: str, doc: dict) -> Pipeline:
    """Check a pipeline and write it to backend/pipelines/<name>.yaml. The file's name and the pipeline's name are
    the same, the name is a short lowercase slug, and a built-in pipeline is never overwritten."""
    if not NAME.match(name):
        raise PipelineError("the name must be 1-40 lowercase letters, digits and hyphens, starting with a letter or digit")
    if name in BUILT_IN:
        raise PipelineError(f"{name!r} is built in and read-only; save a copy under another name")
    pipeline = parse({**doc, "name": name}, f"{name}.yaml")
    (PIPELINES / f"{name}.yaml").write_text(yaml.safe_dump(document(pipeline), sort_keys=False))
    return pipeline


def delete(name: str) -> None:
    if name in BUILT_IN:
        raise PipelineError(f"{name!r} is built in and can't be deleted")
    path = PIPELINES / f"{name}.yaml"
    if name not in names():
        raise PipelineError(f"no pipeline {name!r}")
    path.unlink()


def names() -> list[str]:
    """Every pipeline in backend/pipelines/, by name."""
    return sorted(path.stem for path in PIPELINES.glob("*.yaml"))


def resolve(model: str, cheap: str, main: str) -> str:
    return {"cheap": cheap, "main": main}.get(model, model)
