"""Exact equivalence of reversible circuits: verdicts, witnesses, ANFs and variable order."""
from symq import Budget, Circuit, check_equivalence, make_algebra, simulate
from symq.generators.arithmetic import cuccaro_adder

# A Toffoli applied twice is the identity; applied once it is not, and the witness proves it.
reference = Circuit(3)
assert check_equivalence(reference, Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)).equivalent
mutant = Circuit(3).ccx(0, 1, 2)
result = check_equivalence(reference, mutant)
print("different on input", result.witness, "output wire", result.output)
assert reference.run(result.witness) != mutant.run(result.witness)

# The exact output polynomials.
algebra = make_algebra("zdd", 3)
for wire, value in enumerate(simulate(mutant, algebra)):
    print(f"y{wire} = {algebra.to_anf(value)}")

# On arithmetic, the variable order decides the cost (never the verdict).
adder = cuccaro_adder(24)
fast = check_equivalence(adder, adder, backend="zdd", order="auto", budget=Budget(max_seconds=30))
print("24-bit adder checked:", fast.equivalent)
