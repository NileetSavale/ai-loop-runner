import asyncio

from core.code_graph import CodeGraph
from core.repo_memory import RepoMemory
from core.tools import RepoTools

UNITS = '''from pkg.helpers import clean


class Unit:
    def parse(self, text):
        return clean(text).split("/")


def convert(text):
    return Unit().parse(text)
'''
HELPERS = "def clean(text):\n    return text.strip()\n"
TEST = "from pkg.units import convert\n\n\ndef test_convert():\n    assert convert(' a/b ') == ['a', 'b']\n"


def _repo(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "units.py").write_text(UNITS)
    (tmp_path / "pkg" / "helpers.py").write_text(HELPERS)
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_units.py").write_text(TEST)
    return tmp_path


def test_edges_come_from_calls_resolved_through_imports(tmp_path):
    graph = CodeGraph(str(_repo(tmp_path)))
    assert graph.callees["pkg/units.py::Unit.parse"] == {"pkg/helpers.py::clean"}
    assert graph.callers["pkg/helpers.py::clean"] >= {"pkg/units.py::Unit.parse"}
    assert graph.tests["pkg/units.py::convert"] == {"tests/test_units.py::test_convert"}


def test_lookup_finds_by_name_path_or_words_and_shows_valid_notes_only(tmp_path):
    repo = _repo(tmp_path)
    memory = RepoMemory(tmp_path / "m.json")
    memory.notes["pkg/helpers.py::clean"] = {"note": "strips whitespace", "hash": "stale", "task": "t"}
    graph = CodeGraph(str(repo), memory)
    assert graph.find("Unit.parse") == ["pkg/units.py::Unit.parse"] and graph.find("parse") == ["pkg/units.py::Unit.parse"]
    assert set(graph.find("pkg/units.py")) == {"pkg/units.py::Unit", "pkg/units.py::convert"}
    assert "teammate's note" not in graph.lookup("clean")  # the hash doesn't match the code
    from core.repo_memory import code_hash
    memory.notes["pkg/helpers.py::clean"]["hash"] = code_hash(HELPERS, "pkg/helpers.py", "clean")
    memory.add_read_together(["read_file pkg/helpers.py", "edit_file pkg/units.py", "run_tests"])
    shown = graph.lookup("clean")
    assert "teammate's note: strips whitespace" in shown and "called by: pkg/units.py::Unit.parse" in shown
    assert "also read: pkg/units.py (1x)" in shown
    assert "Nothing in the code graph" in graph.lookup("zzz")


def test_lookup_tool_is_offered_only_with_a_graph(tmp_path):
    repo = _repo(tmp_path)
    assert asyncio.run(RepoTools(str(repo), "true").run("lookup_code", {"query": "clean"}))[1]
    out, err = asyncio.run(RepoTools(str(repo), "true", knowledge=CodeGraph(str(repo))).run("lookup_code", {"query": "clean"}))
    assert not err and out.startswith("pkg/helpers.py::clean")
