# Symbolic backends

All backends implement `symq.backends.Algebra`: exact arithmetic in
GF(2)[x₀,…,xₙ₋₁]/(xᵢ²−xᵢ), driven gate by gate by `symq.simulate`. Every value is
canonical inside one algebra instance, so equivalence is equality of output polynomials
(`symq.check_equivalence`). A detected difference yields a witness assignment (a
minimum-degree monomial of the difference) that is re-checked by concrete execution
before it is returned.

| Backend | Representation | Archived name (handoff of 27 Oct 2026) | Notes |
|---|---|---|---|
| `reference` | immutable `ANF` (frozenset) | — | Simplest implementation, used as the in-package reference. |
| `sparse-copy` | `set[int]`, copy on XOR | `qant_set` | Ablation: identical to `sparse` except the wire XOR. |
| `sparse` | `set[int]`, in-place XOR | `fast_set` | Product fast path for disjoint supports. |
| `zdd` | Python ZDD, hash-consed | `zdd` | `order=` sets the variable order. |
| `auto-zdd` | sparse, then whole-state ZDD | `auto_zdd` | Irreversible switch at ≥850 monomials after a nonlinear gate. |
| `adaptive-wire` | per-wire sparse/ZDD | — (new) | Promotion only, never demotion. |
| `packed` | degree-≤2 combinadic bitset | `packed_only` | Refuses degree ≥3 (`ResourceLimitExceeded("degree")`). |
| `packed-fallback` | packed + exact sparse fallback | `adaptive` | Demotes back to packed when the degree drops. |
| `truthtable` | dense truth table (int) | `truth` | Independent oracle; refuses width >18 by default. |

The archived rows are **reconstructions from the handoff description**, not imports of
the archived code (the archive itself has not been supplied to this repository, see
[IMPORT_STATUS.md](IMPORT_STATUS.md)). Behavioural parity with the archive is therefore
unverified until issue #2 is completed.

## Resource guards

`Budget(max_terms=…, max_nodes=…, max_seconds=…)` is enforced inside products,
conversions and the ZDD unique table. Exceeding a limit raises
`ResourceLimitExceeded(resource, limit, observed)`; there is no approximate fallback.
Representation limits use the same exception (`"width"` for `truthtable` and `zdd`,
`"degree"` for `packed`). Conversions between representations are counted in
`Stats.conversions`, `Stats.conversion_terms` and `Stats.conversion_seconds`.

## Verification strategy

- Differential tests: every backend against concrete execution on all inputs of seeded
  random circuits (`tests/test_backends.py`), and ring operations against `ANF` with
  Hypothesis.
- Equivalence: semantics-preserving rewrites must be proven equivalent; structural
  mutants must agree with exhaustive enumeration, with concretely valid witnesses
  (`tests/test_equivalence.py`).
- Mutation tests of the backends themselves: deliberately broken algebras (no parity
  cancellation, missing ZDD cross term, OR instead of XOR) must be detected.

## Observations to carry into benchmarks

ZDD size is extremely sensitive to the variable order. On the public QCEC circuits,
reversing the order shrinks `c2_181` from 2 919 to 703 nodes but grows `rd84_313` from
1 658 to 238 615 nodes. Any order heuristic must be tuned on DEV circuits only.
