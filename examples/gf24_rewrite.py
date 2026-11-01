"""Replace a GF(2^24) schoolbook multiplier by the 99-product tower and prove it exactly.

The proof is the total theorem with the packed degree-two engine: the block and its replacement
agree on all 2^72 inputs, so the rewrite is valid in any surrounding circuit. The weights are a
declared proxy (a Toffoli priced 32 CNOTs), not a T-count.
"""
from symq import Circuit
from symq.generators.gf2n import emit, schoolbook
from symq.labs.bilinear_substitution import gf24_rewrite, mapped_circuit
from symq.labs.rewrite import Weights

width = 76
wires = tuple(range(2, 74))  # the multiplier's 72 local wires inside a wider circuit
block = mapped_circuit(emit(24, schoolbook(24)).circuit, width, wires)
prefix, suffix = Circuit(width).cx(0, 2).ccx(0, 1, 74), Circuit(width).cx(73, 75)
source = Circuit(width, prefix.gates + block.gates + suffix.gates)
span = (len(prefix.gates), len(prefix.gates) + len(block.gates))

method, result = gf24_rewrite(source, span, wires=wires,
                              weights=Weights.from_mapping({"ccx": 32, "cx": 1}))
assert result.equivalent and result.theorem == "classical_total" and result.candidate is not None
counts = dict(result.cost.candidate_counts)
print(f"{method}: {result.outcome}; whole candidate circuit {counts['ccx']} CCX + {counts['cx']} CX, "
      f"declared weighted delta {result.cost.weighted_delta}")
