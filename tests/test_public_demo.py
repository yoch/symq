"""Exercise the exact public demo in both native and pure-Python CI jobs."""
from __future__ import annotations

import json
import runpy
from pathlib import Path

from symq import Circuit

ROOT = Path(__file__).resolve().parents[1]


def test_public_demo_reports_checked_classical_and_coherent_examples(capsys):
    runpy.run_path(str(ROOT / "examples" / "public_demo.py"), run_name="__main__")
    result = json.loads(capsys.readouterr().out)

    classical = result["classical"]
    assert classical["equivalent"] is True
    assert classical["mutant_equivalent"] is False
    witness = classical["counterexample_input"]
    assert type(witness) is int and 0 <= witness < 8
    assert Circuit(3).run(witness) != Circuit(3).ccx(0, 1, 2).run(witness)
    assert classical["target_anf_degree"] == 2

    channel = result["hmr"]
    assert channel["equivalent"] is True
    assert channel["uncorrected_outcome"] == "different"
    x, y = channel["coherence_witness"]
    assert type(x) is int and type(y) is int and x != y
    assert channel["witness_replayed"] is True
    assert channel["backend"] == "zdd (pure Python)"
    assert "no general quantum" in result["limitations"]
