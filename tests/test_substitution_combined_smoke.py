"""CI-only combined snapshot regression: both research APIs must coexist."""
import pytest

from benchmarks.substitution_qualification import load_manifest
from symq import Circuit
from symq.experimental.hybrid import HOp, HybridProgram, same_channel
from symq.labs.channel_composition import HybridFragment
from symq.labs.contextual_substitution import (
    SubstitutionContract,
    apply_verified_substitution,
    check_substitution,
)
from symq.labs.hybrid_substitution import (
    apply_verified_hybrid_substitution,
    check_hybrid_substitution,
)

pytestmark = pytest.mark.sat


def test_combined_immutable_rewrite_apis_and_qualification():
    reference = Circuit(3).cx(0, 1).cx(0, 1).ccx(0, 1, 2)
    contract = SubstitutionContract()
    receipt = check_substitution(reference, (0, 2), Circuit(3), contract=contract)
    applied = apply_verified_substitution(
        receipt, reference, (0, 2), Circuit(3), contract=contract
    )
    assert applied.proof.certified
    for x in range(8):
        assert applied.candidate.circuit().run(x) == reference.run(x)

    source = HybridProgram(3, 1, [
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("ccx", (0, 1, 3)),
    ])
    replacement = HybridFragment(4, (
        HOp("ccx", (0, 1, 3)), HOp("cx", (3, 2)),
        HOp("hmr", (3,), slot="b0"),
        HOp("cz", (0, 1), condition="b0"),
    ))
    coherent_receipt = check_hybrid_substitution(
        source, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,),
    )
    coherent_applied = apply_verified_hybrid_substitution(
        coherent_receipt, source, (0, 3), replacement,
        wires=(0, 1, 2, 3), clean=(3,),
    )
    assert coherent_applied.proof.certified
    assert same_channel(source, coherent_applied.candidate.to_program()).equivalent
    assert len(load_manifest()["cases"]) == 28
