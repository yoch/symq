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
| `sparse-copy` | `set[int]`, copy on XOR | `copy_set` | Ablation: identical to `sparse` except the wire XOR. |
| `sparse` | `set[int]`, in-place XOR | `fast_set` | Product fast path for disjoint supports. |
| `zdd` | Python ZDD, hash-consed | `zdd` | `order=` sets the variable order. Arbitrary width. |
| `zdd-native` | C extension (`_zdd.c`), fused gate loop | — (new) | High-speed C core; max width 64 (`uint64_t` masks). |
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

The ZDD product uses the archive's three-product recursion
(`PQ = P0Q0 + v(P0Q1 + P1Q0 + P1Q1)`). It allocates exactly as many nodes as the archived
`src/zdd.py` on the DEV circuits. The earlier two-product form,
`v((P0 + P1)(Q0 + Q1) + P0Q0)`, has one fewer recursive product but builds larger cofactor
sums. Under the reversed variable order it allocated 238 615 nodes on `rd84_313` instead of
1 436, which made the order look far more critical than it is.

The variable order still matters. Putting the highest wire at the root, as the archive does,
cuts `c2_181` from 2 232 to 443 allocated nodes but slows `rd84_313` and `sym9_317` by about
1.5×. Any order heuristic must be tuned on DEV circuits only.

## Width Limits and Block Verification

`NativeZDDAlgebra` (`zdd-native`) encodes monomial variables as 64-bit integer masks (`uint64_t`)
to achieve maximum throughput and cache locality. Consequently, it enforces a strict limit
of `MAX_WIDTH = 64`. For circuits with more than 64 wires:
1. **Pure-Python `zdd`**: The Python ZDD backend supports arbitrary wire widths using Python's
   arbitrary-precision integers.
2. **Block Verification (`check_equivalence_by_blocks`)**: When a large circuit decomposes into
   independent wire interaction blocks (connected components) of width $\le 64$,
   `check_equivalence_by_blocks` isolates each block, verifies it via `zdd-native`, and verifies
   any counterexample witness on the full circuit.

## Domain Boundary: Boolean Algebra vs Phase/HMR

symq contains two distinct semantic engines with an explicit boundary:
- **Exact Boolean Algebra (`symq.backends`)**:
  Operates on pure reversible classical circuits (`Circuit`, gates `x`, `cx`, `ccx`, `mcx`).
  Supports pluggable backends (including the C native core `zdd-native`), formal budgets
  (`Budget`), and harmonized execution statistics (`Stats.gates`, `Stats.products`,
  `Stats.peak_terms`, `Stats.seconds`).
- **Sign-Phase & Measurement (`symq.phase`)**:
  Operates on reversible programs with Hadamard-Measure-Reset (`PhaseProgram`, `hmr`, `mcz`, `mcz_if`).
  Operates as a pure-Python formal reference layer over exact rational phase arithmetic $\mathbb{Z}_8$
  and canonical affine outcome reduction. It is unbudgeted and does **not** interface with the
  C native engine or `Algebra` backends.
