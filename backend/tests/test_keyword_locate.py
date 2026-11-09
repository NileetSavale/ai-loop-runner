from core.keyword_locate import locate_by_keywords, tokens
from core.repo_map import build_repo_map, map_for_prompt


def test_tokens_split_identifiers():
    assert tokens("get_unitFormat of the HTTPServer") == ["unit", "format", "http", "server"]


def test_files_rank_by_their_best_function_and_name_it(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "units.py").write_text(
        "def parse_unit(text):\n    return text.split('/')\n\n\ndef other():\n    return 1\n")
    (tmp_path / "pkg" / "admin.py").write_text("def register(model):\n    return model\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_units.py").write_text("def test_parse_unit():\n    assert parse_unit('a/b')\n")
    (tmp_path / "web.js").write_text("export function drawUnit(unit) { return unit }\n")
    found = locate_by_keywords(str(tmp_path), "parse_unit splits a unit string wrongly", 5)
    assert found[0] == {"path": "pkg/units.py", "reason": "task words match parse_unit"}
    assert "tests/test_units.py" not in [f["path"] for f in found]  # tests are never a likely place
    assert "web.js" in [f["path"] for f in found] and "pkg/admin.py" not in [f["path"] for f in found]
    assert len(locate_by_keywords(str(tmp_path), "unit", 1)) == 1


def test_map_tolerates_focus_files_past_the_cap(tmp_path):
    (tmp_path / "a.py").write_text("def f():\n    pass\n")
    text = map_for_prompt(build_repo_map(str(tmp_path)), [{"path": "deep/z.py", "reason": "x"}])
    assert text.splitlines()[0] == "deep/z.py" and "a.py: f" in text
