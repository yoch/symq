"""A GF16 multiplier replacement with an actual prepared classical cut.

This exercises research PRs #124 and #126 together; it is not an HMR or
physical resource-cost certificate.
"""
from __future__ import annotations

from symq import Budget, Circuit
from symq.generators import gf2n
from symq.labs.bilinear_substitution import apply_tower_substitution
from symq.labs.contextual_substitution import GateWeights, SubstitutionContract

width = 13
original_block = gf2n.emit(4, gf2n.schoolbook(4)).circuit
prefix = Circuit(width).cx(0, 12).cx(0, 12).cx(2, 7)
suffix = Circuit(width).cx(11, 0)
source = Circuit(width, prefix.gates + original_block.gates + suffix.gates)
span = (len(prefix.gates), len(prefix.gates) + len(original_block.gates))

contract = SubstitutionContract(initial_constants=((12, 0),), clean_at_cut=(12,))
applied = apply_tower_substitution(
    source,
    span,
    n=4,
    modulus=0x13,
    wires=tuple(range(12)),
    contract=contract,
    weights=GateWeights(cx=1, ccx=12),
    budget=Budget(max_seconds=25),
)
assert applied.proof.certified
assert applied.proof.cost.weighted_delta < 0

print("Classical contextual substitution:", applied.proof.outcome)
print("Declared weighted delta:", applied.proof.cost.weighted_delta)
print("Frozen candidate SHA-256:", applied.proof.candidate_sha256)
