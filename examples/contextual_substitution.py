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
