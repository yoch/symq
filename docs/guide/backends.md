# Symbolic backends

All backends implement `symq.backends.Algebra`: exact arithmetic in
GF(2)[x₀,…,xₙ₋₁]/(xᵢ²−xᵢ), driven gate by gate by `symq.simulate`. Every value is canonical
inside one algebra instance, so equivalence is equality of output polynomials
(`symq.check_equivalence`). A detected difference yields a witness assignment (a minimum-degree
monomial of the difference) that is re-checked by concrete execution before it is returned.
Values from different algebra instances must never be mixed.

| Backend | Representation | Width limit | Notes |
| --- | --- | --- | --- |
| `reference` | immutable `ANF` (frozenset of monomial masks) | none | Simplest implementation; the in-package reference |
| `sparse-copy` | `set[int]`, copy on XOR | none | Ablation of `sparse` (copying XOR) |
| `sparse` | `set[int]`, in-place XOR | none | Product fast path for disjoint supports |
| `zdd` | Python ZDD, hash-consed | 256 variables | `order=` sets the variable order |
| `zdd-native` | C extension, fused gate loop | 64 variables | Same algebra as `zdd`; optional, see [getting started](../getting-started.md) |
| `zdd-native-wide` | C extension, two-word masks at the boundary | 128 variables | Explicit opt-in; diagram operations shared with `zdd-native` |
| `auto-zdd` | sparse, then whole-state ZDD | 256 variables | Irreversible switch at ≥850 monomials after a nonlinear gate |
| `adaptive-wire` | per-wire sparse/ZDD | 256 variables | Promotion only, never demotion |
| `packed` | degree-≤2 combinadic bitset | none | Refuses degree ≥3 with `ResourceLimitExceeded("degree")` |
| `packed-fallback` | packed + exact sparse fallback | none | Demotes back to packed when the degree drops |
| `truthtable` | dense truth table | 18 inputs by default | Independent oracle |

No backend wins on every circuit. Variable order, intermediate diagram size, output extraction
and manager lifetime can each dominate the cost, and the 128-variable mode raises a
representation ceiling, not the worst-case exponential cost.

## Resource guards

`Budget(max_terms=…, max_nodes=…, max_seconds=…)` is enforced inside products, conversions and
the ZDD unique table. Exceeding a limit raises `ResourceLimitExceeded(resource, limit, observed)`;
there is no approximate fallback. Representation limits use the same exception (`"width"`,
`"degree"`). Conversions between representations are counted in `Stats.conversions`,
`Stats.conversion_terms` and `Stats.conversion_seconds`. See [resources](resources.md) for
deadlines and isolated execution.

## Variable order

The order changes diagram sizes by orders of magnitude but never results or witnesses.
`check_equivalence(..., order=...)` takes `"auto"`, a policy name (`identity`, `reversed`,
`last_use`) or an explicit permutation; `"auto"` applies the structural rule of
`symq.strategy.choose_order` to the reference circuit. On ripple-carry adders this turns a timeout
into a sub-millisecond check; on small circuits it adds a fixed cost of a fraction of a
millisecond ([measurements](../evidence/performance-2026-10-31.md)). It is never applied unless
requested; `symq check` requests it for ZDD engines. `symq.order_for(circuit, policy)` returns the
order itself.

## Wide circuits and block verification

For more than 64 coupled wires use `zdd-native-wide` (up to 128), the Python `zdd` backend (up to
256), or block verification. `check_equivalence_by_blocks` splits both circuits along the
connected components of their **joint** interaction graph and checks each block separately:
`zdd-native` up to `max_block_width` wires, the `fallback` backend (`zdd` by default) beyond.
A counterexample from a block is re-checked on the full circuits. `Budget.max_seconds` bounds the
whole check; `max_terms` and `max_nodes` apply to each block. A connected circuit is not
decomposable this way; arbitrary cuts need an explicit interface contract (see
[relational composition](sat.md#relational-composition)).

## Native operation cache

The native operation cache is lossless by default: entries are never evicted and the table grows
with the work. `cache_limit=n` switches to a fixed direct-mapped table of the largest power of two
not above `n` entries (16 bytes each), where a store overwrites its slot. Results, node ids,
`node_count` and every statistic except time are identical in both modes, because node ids are
hash-consed; only recomputation changes. `cache_info()` reports the mode, capacity and the number
of cache misses. A limit far below the working set can cost a multiple of the lossless time.

## Native collection

Native node handles are plain integers, so collection follows an **owned, one-shot** contract.
`NativeZDDAlgebra(width, collect_every=n)` simulates in slices and, whenever the unique table holds
at least `n` nodes, replaces the manager by a copy of the live DAG reachable from the current
roots (`clone_roots`). The transfer copies nodes directly; it does not enumerate monomials, so a
compact diagram with an exponential number of monomials is collected as cheaply as any other.

- Collection requires a fresh manager and a single simulation; reusing an algebra whose handles
  were already exposed raises instead of silently invalidating them.
- `check_equivalence(..., backend_options={"collect_every": n})` uses `simulate_pair`, which pins
  the first circuit's outputs as live roots while simulating the second.
- Inside a `VerificationSession`, both tables are reserved during the transfer, so `max_nodes`
  accounts for the temporary peak.

Collection trades time for peak memory. It is opt-in, and no default enables it.

## Boolean algebra versus phase programs

`symq.backends` covers reversible classical circuits (`Circuit` with `x`, `cx`, `ccx`, `mcx`).
Sign-phase programs with X-basis measure-and-reset (`symq.phase.PhaseProgram`) have their own
reference semantics; the experimental channel checker lowers them onto a native manager through
`NativeZDDAlgebra.simulate_hmr`. The two layers answer different questions: see the
[HMR specification](../reference/phase-hmr-spec.md) and the [experimental guide](experimental.md).

## How the backends are tested

- Every backend against concrete execution on all inputs of seeded random circuits, and the ring
  operations against `ANF` with Hypothesis (`tests/test_backends.py`).
- Semantics-preserving rewrites must be proven equivalent, and structural mutants must agree with
  exhaustive enumeration with concretely valid witnesses (`tests/test_equivalence.py`).
- Deliberately broken algebras (no parity cancellation, missing ZDD cross term, OR instead of XOR)
  must be detected.
- The native core is additionally run under AddressSanitizer and UndefinedBehaviorSanitizer
  (`tools/sanitize_native.py`).
