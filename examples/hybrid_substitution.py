"""A full coherent HMR replacement at a real global span (public demo)."""
import json

from symq.experimental.hybrid import HOp, HybridProgram
from symq.labs.channel_composition import HybridFragment
from symq.labs.hybrid_substitution import check_hybrid_substitution

reference = HybridProgram(3, 1, [
    HOp("ccx", (0, 1, 3)),
    HOp("cx", (3, 2)),
    HOp("ccx", (0, 1, 3)),
])
replacement = HybridFragment(4, (
    HOp("ccx", (0, 1, 3)),
    HOp("cx", (3, 2)),
    HOp("hmr", (3,), slot="b0"),
    HOp("cz", (0, 1), condition="b0"),
))
proof = check_hybrid_substitution(
    reference, (0, 3), replacement, wires=(0, 1, 2, 3), clean=(3,),
)
assert proof.equivalent
print(json.dumps(proof.to_dict(), indent=2, sort_keys=True))

mutant = HybridFragment(4, replacement.ops[:-1])
rejected = check_hybrid_substitution(
    reference, (0, 3), mutant, wires=(0, 1, 2, 3), clean=(3,),
)
assert rejected.outcome == "not_proved"
print("Missing corrective CZ:", rejected.outcome)
