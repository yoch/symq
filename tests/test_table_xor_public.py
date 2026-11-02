"""Promotion preserves the audited engine and the legacy import identities."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from symq import Circuit
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


def test_promoted_engine_is_byte_identical_to_audited_implementation():
    raw = Path(public.__file__).read_bytes()
    git_blob = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
    assert git_blob == "9e488dddff8796ebb34cf437f9cf9e889ade0ef1"


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
