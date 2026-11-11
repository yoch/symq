"""A test that asserts a ceiling on real elapsed time must carry the ``timing`` marker.

Some properties are about real time and cannot be tested on an injected clock: a hard wall-clock
limit that kills a subprocess, an interrupt that must stop a running solver. Their assertions
compare a measured duration with a ceiling, and a measured duration depends on what else the
machine is doing. Under ``pytest -n auto`` the other workers are that "what else".

So these tests are marked ``timing`` and CI runs them in a separate serial step (see
``.github/workflows/ci.yml``). This file keeps the rule from eroding: it reads every test module
and fails if a test compares the real clock with an upper bound without the marker. A test whose
clock is injected, or whose bound cannot be exceeded by a slow machine, is listed in
``NOT_LOAD_SENSITIVE`` with the reason.

The check is syntactic. It reads the module-level ``test_*`` functions (this suite has no test
classes) and recognises ``time.perf_counter()``, ``time.monotonic()`` and ``time.time()`` and the
conventional names ``elapsed`` and ``wall`` on the smaller side of a ``<`` or ``<=``; a ceiling
written another way, or inside a class, is not seen.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
CLOCK_CALLS = {"perf_counter", "monotonic", "time"}
DURATION_NAMES = {"elapsed", "wall"}

NOT_LOAD_SENSITIVE = {
    ("test_phase_proof_bundle.py",
     "test_guard_honors_caller_budget_and_limits_beyond_the_old_hidden_caps"):
        "the bound is the guard's own 10 s default seen just after its creation: the remaining "
        "time can only be lower on a slow machine, never above the bound",
}
"""(file, test) -> why a real-time comparison there cannot fail on a slow machine."""


def reads_real_time(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and child.id in DURATION_NAMES:
            return True
        if (isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute)
                and child.func.attr in CLOCK_CALLS
                and isinstance(child.func.value, ast.Name) and child.func.value.id == "time"):
            return True
    return False


def has_ceiling(function: ast.FunctionDef) -> bool:
    """Does the test assert ``<real time> < bound`` (or ``<=``) anywhere?"""
    for node in ast.walk(function):
        if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
            continue
        operands = [node.test.left, *node.test.comparators]
        for position, operator in enumerate(node.test.ops):
            if isinstance(operator, (ast.Lt, ast.LtE)) and reads_real_time(operands[position]):
                return True
    return False


def names_timing(node: ast.AST) -> bool:
    return any(isinstance(child, ast.Attribute) and child.attr == "timing"
               for child in ast.walk(node))


def unmarked_ceilings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_marked = any(
        isinstance(node, ast.Assign) and names_timing(node.value)
        and any(isinstance(target, ast.Name) and target.id == "pytestmark"
                for target in node.targets)
        for node in tree.body)
    found = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        if not has_ceiling(node) or (path.name, node.name) in NOT_LOAD_SENSITIVE:
            continue
        if not module_marked and not any(names_timing(item) for item in node.decorator_list):
            found.append(f"{path.name}::{node.name}")
    return found


def test_every_real_time_ceiling_is_marked_timing():
    unmarked = [name for path in sorted(TESTS.glob("test_*.py"))
                for name in unmarked_ceilings(path)]
    assert not unmarked, (
        "these tests compare the real clock with an upper bound; mark them "
        f"@pytest.mark.timing or inject the clock: {unmarked}")


def test_the_exceptions_still_exist():
    for file, test in NOT_LOAD_SENSITIVE:
        source = (TESTS / file).read_text(encoding="utf-8")
        assert f"def {test}(" in source, f"{file}::{test} is listed but no longer exists"


@pytest.mark.parametrize("source, expected", [
    ("def test_a():\n    assert time.perf_counter() - started < 2\n", ["m.py::test_a"]),
    ("def test_a():\n    assert elapsed <= 0.5\n", ["m.py::test_a"]),
    ("def test_a():\n    assert 0 <= wall - inner < 0.03\n", ["m.py::test_a"]),
    ("def test_a():\n    assert time.monotonic() - t0 < limit\n", ["m.py::test_a"]),
    # A lower bound, an injected duration and an inner-versus-outer comparison are not ceilings.
    ("def test_a():\n    assert elapsed >= 0.02\n", []),
    ("def test_a():\n    assert result.seconds < 5\n", []),
    ("def test_a():\n    assert verdict.total_seconds <= wall + 1e-3\n", []),
    # Marked, per test or for the whole module.
    ("@pytest.mark.timing\ndef test_a():\n    assert elapsed < 1\n", []),
    ("@pytest.mark.sat\n@pytest.mark.timing\ndef test_a():\n    assert elapsed < 1\n", []),
    (("pytestmark = [pytest.mark.sat, pytest.mark.timing]\n"
      "def test_a():\n    assert elapsed < 1\n"), []),
    ("pytestmark = pytest.mark.sat\ndef test_a():\n    assert elapsed < 1\n", ["m.py::test_a"]),
])
def test_the_check_sees_what_it_claims(tmp_path, source, expected):
    path = tmp_path / "m.py"
    path.write_text(source, encoding="utf-8")
    assert unmarked_ceilings(path) == expected
