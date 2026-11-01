"""Contextual SAT substitution: prove cut preparation before deleting a gate.

Run with pip install -e ".[sat]" and python examples/contextual_substitution.py.
"""
import json

from symq import Circuit
from symq.labs.contextual_substitution import (
    GateWeights,
    SubstitutionContract,
    check_substitution,
)

# The first two gates restore q2 to zero, given a *declared input* of q2=0.
# At this cut CX(q2,q0) is the identity, even though it is not identity
# on an arbitrary, unprepared q2. The unchanged suffix is retained.
source = Circuit(3).cx(0, 2).cx(0, 2).cx(2, 0).cx(0, 1)
result = check_substitution(
    source, (2, 3), Circuit(3),
    contract=SubstitutionContract(
        initial_constants=((2, 0),),
        clean_at_cut=(2,),
    ),
    weights=GateWeights(cx=3),
)
print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
assert result.equivalent and result.cost.weighted_delta == -3

# Without the prepared input, the prefix cannot establish the requested
# zero cut condition. It must refuse instead of trusting a declaration.
rejected = check_substitution(
    source, (2, 3), Circuit(3),
    contract=SubstitutionContract(clean_at_cut=(2,)),
)
assert rejected.outcome == "precondition_failed"
print("Without initial preparation:", rejected.outcome)

# A genuine decomposition: 3-control X implemented using three Toffolis
# and one clean scratch wire. The two blocks disagree when that scratch is
# dirty; both local programs must restore it to its own cut input value.
source_mcx = (Circuit(5).cx(0, 4).cx(0, 4)
              .mcx(0, 1, 2, 3).cx(3, 0))
decomposed = (Circuit(5).ccx(0, 1, 4)
              .ccx(4, 2, 3).ccx(0, 1, 4))
contract_mcx = SubstitutionContract(initial_constants=((4, 0),), clean_at_cut=(4,))
receipt = check_substitution(
    source_mcx, (2, 3), decomposed, contract=contract_mcx,
    weights=GateWeights(ccx=2, mcx=10),
)
assert receipt.equivalent and receipt.cost.weighted_delta == -4
print("Clean-ancilla 3-control decomposition:", receipt.outcome,
      "declared weighted delta:", receipt.cost.weighted_delta)
