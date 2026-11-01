"""Check many candidate rewrites against one reference without re-simulating it."""
import random

from symq import ReferenceChecker
from symq.generators import equivalent_variant, mutate
from symq.generators.gf2n import multiplier

reference = multiplier(8, "schoolbook")          # GF(2^8) multiplier on 24 wires
checker = ReferenceChecker(reference, backend="zdd")
rng = random.Random(0)
accepted = 0
for _ in range(20):
    candidate = (equivalent_variant(reference, rng, steps=10) if rng.random() < 0.5
                 else mutate(reference, rng)[0])
    accepted += checker.check(candidate).equivalent
print(f"{accepted} of 20 candidates are exact rewrites")
# Different decompositions of the same field multiplication are equivalent.
print("karatsuba == schoolbook:", checker.check(multiplier(8, "karatsuba")).equivalent)
