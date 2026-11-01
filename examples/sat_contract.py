"""SAT contracts: observed outputs, restored (possibly dirty) wires and input assumptions."""
from symq import Circuit
from symq.sat import Contract, available, check_sat_equivalence
from symq.sat.assumptions import Eq, Var

if not available():
    raise SystemExit("install the SAT engine: pip install -e '.[sat]'")

left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
right = Circuit(3)
contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))
print("restored ancilla:", check_sat_equivalence(left, right, contract).outcome)

# Two circuits that agree only when x0 == x1.
left, right = Circuit(3).ccx(0, 1, 2), Circuit(3).cx(0, 2)
print("everywhere:", check_sat_equivalence(left, right).outcome)
diagonal = Contract(assumption=Eq(Var("x.0"), Var("x.1")))
print("on x0 == x1:", check_sat_equivalence(left, right, diagonal).outcome)
