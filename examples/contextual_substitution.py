"""Contextual classical rewrites: prove the cut before relying on a clean scratch wire.

Run with ``pip install -e ".[sat]"`` and ``python examples/contextual_substitution.py``.
The same requests can be proved from files with ``symq rewrite examples/rewrite/request.json``.
"""
from symq import Budget, Circuit
from symq.generators import gf2n
from symq.labs.bilinear_substitution import apply_tower_substitution
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.rewrite import Weights

# The first two gates restore q2 to zero, given a declared input q2 = 0. At this cut CX(q2, q0)
# is the identity, although it is not the identity on an unprepared q2.
source = Circuit(3).cx(0, 2).cx(0, 2).cx(2, 0).cx(0, 1)
contract = SubstitutionContract(initial_constants=((2, 0),), clean_at_cut=(2,))
result = check_substitution(source, (2, 3), Circuit(3), contract=contract,
                            weights=Weights.from_mapping({"cx": 3}))
assert result.equivalent and result.cost.weighted_delta == -3
print("delete a gate at a proved clean cut:", result.outcome, result.cost.weighted_delta)

# Without the declared input the prefix cannot establish the clean cut: refused, not trusted.
rejected = check_substitution(source, (2, 3), Circuit(3),
                              contract=SubstitutionContract(clean_at_cut=(2,)))
assert rejected.outcome == "precondition_failed" and rejected.candidate is None
print("without the declared input:", rejected.outcome)

# A 3-control X decomposed into three Toffolis through a clean scratch wire q4. Under the
# weights below (3-wire mcx = ccx priced 2, larger mcx priced 10) it is 4 units cheaper.
source_mcx = Circuit(5).cx(0, 4).cx(0, 4).mcx(0, 1, 2, 3).cx(3, 0)
decomposed = Circuit(5).ccx(0, 1, 4).ccx(4, 2, 3).ccx(0, 1, 4)
receipt = check_substitution(
    source_mcx, (2, 3), decomposed,
    contract=SubstitutionContract(initial_constants=((4, 0),), clean_at_cut=(4,)),
    weights=Weights.from_mapping({"ccx": 2, "mcx": 10}))
assert receipt.equivalent and receipt.cost.weighted_delta == -4
print("clean-scratch 3-control decomposition:", receipt.outcome, receipt.cost.weighted_delta)

# A GF(16) schoolbook multiplier replaced in place by the certified 9-product tower multiplier.
width = 13
block = gf2n.emit(4, gf2n.schoolbook(4)).circuit
prefix = Circuit(width).cx(0, 12).cx(0, 12).cx(2, 7)
tower_source = Circuit(width, prefix.gates + block.gates + Circuit(width).cx(11, 0).gates)
applied = apply_tower_substitution(
    tower_source, (len(prefix.gates), len(prefix.gates) + len(block.gates)), n=4, modulus=0x13,
    wires=tuple(range(12)),
    contract=SubstitutionContract(initial_constants=((12, 0),), clean_at_cut=(12,)),
    weights=Weights.from_mapping({"cx": 1, "ccx": 12}), budget=Budget(max_seconds=25))
assert applied.equivalent and applied.candidate is not None
print("GF(16) tower multiplier:", applied.outcome, "weighted delta", applied.cost.weighted_delta)
