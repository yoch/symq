"""Public contracts retain legacy import identities and replay compatibility."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from symq import Circuit
from symq.circuit import circuit_from_dict
from symq.experimental import (
    ReceiptMismatch,
    TableXorContract,
    TableXorResult,
    check_table_xor,
    replay_table_xor,
)
from symq.experimental import table_xor as public
from symq.hashing import canonical_sha256
from symq.labs import table_xor_contract as legacy


@pytest.mark.sat
def test_receipt_from_audited_v1_implementation_still_replays():
    # Generated from exact base 0aa2bef53e33966c5b4be07bf590b47188e387a6,
    # whose table_xor.py blob was 9e488dddff8796ebb34cf437f9cf9e889ade0ef1.
    # The extension changes source bytes; preserve the actual consumer contract.
    root = Path(__file__).resolve().parents[1] / "examples/table_xor"
    source = circuit_from_dict(json.loads((root / "linear.json").read_text()))
    spec = TableXorContract.from_dict(json.loads((root / "contract.json").read_text()))
    receipt = {
        "kind": "symq_table_xor_result", "schema_version": 1,
        "status": "equivalent", "reason": "SAT UNSAT on all declared inputs",
        "theorem": "coherent", "backend": "sat", "witness": None,
        "checked_states": 0, "sat_clauses": 64,
        "source_sha256": "bf60ffe15f3e4abdf680e838b356b129a15215d943bb792b67367a8c0517f14e",
        "contract_sha256": "840d10542ae076e8e290be7fab798dbad883ad10c0cef482a58c44e33b4cf895",
    }
    assert replay_table_xor(
        source, spec, receipt, expected_source_sha256=receipt["source_sha256"],
        expected_contract_sha256=receipt["contract_sha256"], backend="sat",
    ).equivalent


def test_old_and_new_imports_have_identical_objects():
    for name in public.__all__:
        assert getattr(legacy, name) is getattr(public, name)
    assert TableXorResult is public.TableXorResult
    assert ReceiptMismatch is public.ReceiptMismatch


def test_public_contract_full_dirty_target_and_fresh_replay():
    source = Circuit(3).cx(0, 1)
    spec = TableXorContract(
        width=3, address_wires=(0,), target_wires=(1,), clean_wires=(),
        borrowed_wires=(2,), table=(0, 1), legal_addresses=(0, 1),
        target_values=None, table_id="public-table", slot_id="public-slot",
        theorem="coherent")
    source_pin = canonical_sha256(source.to_dict())
    contract_pin = spec.sha256
    proof = check_table_xor(source, spec, backend="exhaustive")
    assert proof.equivalent and proof.checked_states == 8
    assert replay_table_xor(
        source, spec, proof.to_dict(), expected_source_sha256=source_pin,
        expected_contract_sha256=contract_pin, backend="exhaustive").equivalent
    source.x(2)
    with pytest.raises(ReceiptMismatch):
        replay_table_xor(
            source, spec, proof.to_dict(), expected_source_sha256=source_pin,
            expected_contract_sha256=contract_pin, backend="exhaustive")


def test_maintained_import_loads_no_labs_module_and_no_solver():
    """Audit #164: the maintained surface must not depend on labs (fresh interpreter)."""
    import subprocess
    import sys

    code = ("import sys, symq.experimental, symq.experimental.table_xor;"
            "print(sorted(m for m in sys.modules if m.startswith('symq.labs')));"
            "print('pysat' in sys.modules)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True).stdout.split()
    assert out == ["[]", "False"]


def test_public_guide_is_reachable_from_the_documentation_index():
    root = Path(__file__).resolve().parents[1]
    assert "guide/table-xor-public-api.md" in (root / "docs" / "index.md").read_text()
