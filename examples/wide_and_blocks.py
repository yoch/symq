"""Wide circuits: affine stages of any width, and block-wise checks of disconnected circuits."""
import random

from symq import Circuit, check_equivalence, check_equivalence_by_blocks

rng = random.Random(1)
stage = Circuit(800)
for _ in range(20_000):
    a, b = rng.sample(range(800), 2)
    stage.cx(a, b)
round_trip = Circuit(800, [*stage.gates, *stage.inverse().gates])
print("800-wire linear stage undone:",
      check_equivalence(round_trip, Circuit(800), backend="linear").equivalent)

# Two independent 3-wire blocks inside a 200-wire register.
wide = Circuit(200).ccx(0, 1, 2).ccx(0, 1, 2).cx(150, 151)
print("block-wise:", check_equivalence_by_blocks(wide, Circuit(200).cx(150, 151)).equivalent)
