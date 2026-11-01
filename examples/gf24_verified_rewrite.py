"""A pinned GF24 all-input rewrite verified by the packed ANF transcript engine.

This demonstrates the source SHA contract on a 72-wire classical
reversible multiplier. It is not HMR/phase verification, a Kaggle score
or proof that the weights represent physical resource usage.
"""
from __future__ import annotations

from symq import Budget
from symq.generators.gf2n import emit, karatsuba
from symq.labs.gf24_verified_rewrite import (
    GF24GateWeights,
    apply_gf24_rewrite,
    replay_gf24_rewrite,
)

old = emit(24, karatsuba(24), strategy="pivot-scheduled").circuit
weights = GF24GateWeights(ccx=32, cx=1)
verified = apply_gf24_rewrite(
    old, (0, len(old.gates)), wires=tuple(range(72)),
    weights=weights, budget=Budget(max_seconds=35, max_terms=4000),
)
assert verified.proof.equivalent
assert verified.proof.backend == "packed"
assert (verified.cost.after_ccx, verified.cost.after_cx) == (99, 2646)
fresh = replay_gf24_rewrite(
    verified, old, budget=Budget(max_seconds=35, max_terms=4000)
)
assert fresh.candidate_sha256 == verified.candidate_sha256
print("GF24 exact full-input stream theorem:", fresh.theorem)
print("CCX/CX:", fresh.cost.after_ccx, fresh.cost.after_cx)
print("Declared weighted delta:", fresh.cost.delta)
print("Frozen candidate SHA-256:", fresh.candidate_sha256)
