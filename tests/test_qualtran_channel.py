"""Authenticated external fixtures exercise scalable HMR channel obligations."""
from pathlib import Path

import pytest

from symq.backends import BACKENDS
from symq.experimental import VerificationContract, replay, verify
from symq.experimental.qualtran import load_qualtran_fixture
from symq.phase import PhaseProgram


@pytest.mark.parametrize("degree", [1, 2])
@pytest.mark.parametrize("backend", ["zdd", "zdd-native"])
def test_qualtran_import_reaches_coherence_kernel_and_replays_mutant(degree, backend):
    if backend not in BACKENDS:
        pytest.skip("optional native extension is absent")
    corpus = Path(__file__).resolve().parents[1] / "benchmarks/corpus/qualtran"
    fixture = load_qualtran_fixture(corpus / f"gf2mul_mbuc_m{degree}.json")
    reference, candidate = fixture.programs()
    contract = VerificationContract(theorem="full_channel", backend=backend)
    assert verify(reference, candidate, contract).outcome == "equivalent"
    correction = next(i for i, op in enumerate(candidate.ops) if op.kind == "mcz_if")
    mutant = PhaseProgram(candidate.data, candidate.ancillas,
                          candidate.ops[:correction] + candidate.ops[correction + 1:])
    difference = verify(reference, mutant, contract)
    assert difference.outcome == "different"
    assert difference.witness[0] != difference.witness[1]
    assert difference.witness_kind == "coherence"
    assert "kernel" in difference.reason
    assert replay(difference, reference, mutant, contract).witness_checked
