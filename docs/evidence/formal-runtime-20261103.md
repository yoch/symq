# Formal runtime soundness — first executable qualification (3 Nov 2026)

This is **Lean in development/CI**, not SymQ runtime and not per-instance
proof export. The checkpoint below is exact executable evidence, not a
claim that the subsequent documentation-only HEAD inherited its CI.

- Base: `main@7861aa9d4a31791644382df8bdfd5abbcdf4a628`.
- Executable PR #169 HEAD: `0f3dde73d213cbc2756c108336035c1989f63fb7`.
- Git tree: `0246f1a77498599677d10505efbdc278830a6df4`.
- Synthetic merge: `ef33b57d9045c52351a1428ed6d9e097bbb514d2`.
- The merge parents (revalidated through GitHub): the base SHA above and
  the exact executable HEAD; its tree matches the branch tree.
- [Dedicated CI run 41589535614](https://github.com/yoch/symq/actions/runs/41589535614)
  passed: Ruff, Python gate/phase conformance tests, the existing graph tests,
  pinned Lean build, standalone Lean theorem elaboration and strict independent
  axiom-report allowlist checks.
- Downloaded artifact 13208734921 SHA-256
  `c16f16d065928c7b09e885b43838f04a902833a093ed8e41b42133f18a3b703a`;
  independently recalculated locally, identical to the GitHub digest.
- The archive contains `commit.txt`, `tree.txt`, `theorems.log`;
  all three were read and match the exact synthetic-merge provenance.

## Six general theorems accepted by Lean 4.19

| Name | Statement / scope | Reported axioms |
| --- | --- | --- |
| andCNF_exact | 3-clause AND ⇔ gate output, arbitrary signed inputs | propext |
| xorCNF_exact | 4-clause XOR ⇔ gate output, arbitrary signed inputs | propext |
| encode_exact | arbitrary finite gate list: combined CNF iff all gate equations | propext |
| unsat_excludes_gate_counterexample | relational graph + root UNSAT excludes gate-consistent root | propext |
| fullAdder_exact | every full-adder input, sum + double carry = integer input total | none |
| addWords_exact | induction for any equal-length little-endian input words | propext, Classical.choice, Quot.sound |

The standard axioms are reported by Lean itself; `sorryAx` and unfamiliar
axiom dependencies are rejected by CI. The kernel still trusts the pinned
Lean toolchain/library/runtime and computing environment.

## What is NOT proved

The models above are universal mathematical statements, but **their relationship
to the existing Python implementations is not itself machine-certified**.
Actual `Graph._clauses_for`, the Python signed-graph evaluator and the
`nonlinear_phase_bits._phase_bits` accumulator are independently tested on
small exhaustive cases and randomized deterministic families, not extracted
from certified Lean implementations.

In particular, `encode_exact` proves an equality for the *relational gate
constraints* over arbitrary finite lists. It does not yet prove acyclic
evaluation, the existence/uniqueness of auxiliary-variable assignments,
hash-consing/constant-folding correctness or source-to-graph fidelity. The
UNSAT implication thus uses a hypothesis about a **correct graph**; it is
not yet the complete quantum source/channel soundness theorem.

No actual qant/KMB circuit, production workload, general scalability or
frozen API is certified. `#168` remains an independent optional
proof-export research path.

## Reproduce

```bash
python -m pytest -q tests/test_formal_runtime_contract.py tests/test_formal_phase_bits.py tests/test_formal_axioms.py tests/test_kraus_graph.py
cd formal/symq_runtime
lake build   # at this commit only GateCNF was a lake target
lean GateCNF.lean
lean PhaseBits.lean
```

The exact 11-file runnable source is retained on the branch. The model
checker and proof assistant are not imported by normal SymQ API calls.
