"""Every example script runs to completion."""
from __future__ import annotations

import runpy
from pathlib import Path

import pytest

EXAMPLES = sorted((Path(__file__).resolve().parents[1] / "examples").glob("*.py"))


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.name)
def test_example_runs(path, capsys):
    # The classical rewrite checker proves with the SAT engine by default.
    if path.name in {"sat_contract.py", "contextual_substitution.py"}:
        from symq import sat

        if not sat.available():
            pytest.skip("needs python-sat")
    runpy.run_path(str(path), run_name="__main__")
    assert capsys.readouterr().out
