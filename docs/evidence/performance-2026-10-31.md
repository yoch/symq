# Performance changes of 31 October 2026

## Scope and limitations

These are relative, in-process observations of one implementation against its predecessor, on one
machine. They are not comparisons with other tools and they do not establish a general speedup.

- One machine: 4-core Intel Xeon, CPython 3.13.18, python-sat 1.9.dev17 (Glucose 4.2).
- `python -m benchmarks.quick`: five repetitions per cell, budget 5 s per call, one process per
  split and tree. Many QCEC cells take well under a millisecond, where scheduling noise is a
  large fraction of the time.
- The CI job `quick-bench` runs the same harness for information only (`continue-on-error`); it
  never blocks a change.
- Only the paired SAT and backend tables below have retained raw records. The later sections are
  exploratory measurements without raw records. Read them as orientation, not as citable speedups.

## Paired measurement with receipts

Two clean source trees were measured with the same harness on the same machine:

| Side | Commit | Native ABI | Native binary SHA-256 (prefix) |
| --- | --- | --- | --- |
| base | `eb43db38c989ef57f162333be8567dbd74e44699` | 6 | `b1e84ebd35b142b6` |
| head | `51cc1b9db66a5ccc5eb211e8a839e7faa709b878` | 6 | `6d2de4a3eb0af1f8` |

The raw records are in [`data/2026-10-31/`](data/2026-10-31/), with a `SHA256SUMS` file. Every
record carries the machine description, a receipt (package path, commit, clean state, source
digest, native binary hash, python-sat version) and every repetition's time.

Two rounds ran the trees in opposite orders on each split. In the first round, the holdout and
synthetic splits measured `head` first. The non-SAT backends then looked 15–21 % slower on the
holdout split. The second round measured `base` first and found no difference. The pooled time of
a cell is the minimum of its per-round medians on each side, and every table below is regenerated
from the records by:

```bash
python -m benchmarks.paired docs/evidence/data/2026-10-31/round1 docs/evidence/data/2026-10-31/round2
```

`tests/test_evidence.py` checks the checksums, the receipts and that each table equals that
output. A cell counts only when every record measured it; cells that hit the 5 s budget on both
sides (the 24-bit adder, the 90-gate random circuits on the explicit and ZDD backends) are left out
and are identical on both sides. Ratios are head / base, so smaller is faster. `dev`, `holdout` and
`extension` are the fixed QCEC corpus splits; `synthetic` is the harness's family of Cuccaro adders
(8, 16, 24 bits) and dense random circuits (14 wires, 60 and 90 gates). The holdout split was not
used to tune any change.

### SAT miter: shared inputs, structural hashing, constant folding

Both circuits of a miter read the same input variables (no tying clauses), identical AND/XOR
definitions are encoded once, and X gates are literal negations instead of a forced-true variable
plus a four-clause XOR.

<!-- paired:sat -->
| Split | Cells | Geometric mean ratio (head/base) | Best | Worst | Cells above 1.10 |
| --- | --- | --- | --- | --- | --- |
| dev | 10 | 0.54 | 0.23 | 0.84 | 0 |
| holdout | 12 | 0.48 | 0.22 | 0.91 | 0 |
| extension | 16 | 0.49 | 0.28 | 0.70 | 0 |
| synthetic | 14 | 0.25 | 0.01 | 1.45 | 1 |
<!-- /paired -->

Largest changes: `random_14x90_1` non-equivalence 153 ms → 1.2 ms and `add6_196` non-equivalence
10.5 ms → 2.9 ms. One cell is slower in both rounds: `random_14x60_1` equivalence, 73 ms → 106 ms
(1.45×), a solver-heuristic effect on an otherwise smaller formula. Verdicts and witness replay are
unchanged; the encoding is checked against concrete execution on every input of random circuits
(`tests/test_sat_equivalence.py`).

### The other backends between the same commits

The symbolic backends were not optimized between these commits; they gained resource checks
(`max_terms` on every intermediate value) and a variable-order option. The tables show what that
costs when no limit is set.

`sparse`:

<!-- paired:sparse -->
| Split | Cells | Geometric mean ratio (head/base) | Best | Worst | Cells above 1.10 |
| --- | --- | --- | --- | --- | --- |
| dev | 15 | 1.00 | 0.94 | 1.05 | 0 |
| holdout | 18 | 1.01 | 0.96 | 1.07 | 0 |
| extension | 24 | 1.01 | 0.94 | 1.09 | 0 |
| synthetic | 10 | 1.01 | 0.98 | 1.10 | 1 |
<!-- /paired -->

`zdd` (Python):

<!-- paired:zdd -->
| Split | Cells | Geometric mean ratio (head/base) | Best | Worst | Cells above 1.10 |
| --- | --- | --- | --- | --- | --- |
| dev | 15 | 1.02 | 0.97 | 1.09 | 0 |
| holdout | 18 | 1.05 | 0.99 | 1.09 | 0 |
| extension | 24 | 1.04 | 1.00 | 1.09 | 0 |
| synthetic | 12 | 1.01 | 0.96 | 1.08 | 0 |
<!-- /paired -->

`zdd-native`:

<!-- paired:zdd-native -->
| Split | Cells | Geometric mean ratio (head/base) | Best | Worst | Cells above 1.10 |
| --- | --- | --- | --- | --- | --- |
| dev | 15 | 1.00 | 0.94 | 1.03 | 0 |
| holdout | 18 | 1.00 | 0.95 | 1.09 | 0 |
| extension | 24 | 1.01 | 0.93 | 1.08 | 0 |
| synthetic | 13 | 1.01 | 0.96 | 1.30 | 1 |
<!-- /paired -->

The Python ZDD is 4–5 % slower on the holdout and extension splits in both rounds, and 2 % slower
pooled on dev, where the rounds disagree: its public `xor` now wraps the recursive one to apply the
term limit. The single native cell above 1.10, `cuccaro_16`
simulation, was re-measured separately: 15 interleaved runs per tree, three times, gave
35.5–35.9 ms on both sides.

## Exploratory: variable order for equivalence, `order="auto"`

No raw records were kept for this section.


`check_equivalence(..., order="auto")` applies the existing structural rule
(`symq.strategy.choose_order`) to the reference circuit. Native ZDD, minimum of three runs, budget
10 s:

| Workload | `identity` order | `auto` |
| --- | --- | --- |
| Cuccaro 16-bit, equivalent / mutant | 85 ms / 1592 ms | 0.34 ms / 0.36 ms |
| Cuccaro 24-bit and 30-bit | exceeds 10 s | 0.6–1.0 ms |
| Random 14×60 (two seeds) | 34–317 ms | 0–4.5 % slower |
| QCEC holdout and extension (26 pairs) | 0.04–1.4 ms | 1.1–2.4× slower |

The rule picks `last_use` for the adders and `identity` elsewhere, so the slowdown on QCEC is the
fixed cost of computing the features and the order (about 0.1–0.3 ms on circuits that take well
under a millisecond). The option is therefore **opt-in** in the library; `symq check` uses it by
default for ZDD engines. Computing the rule on the concatenation of both circuits instead of the
reference hides the staging (the second circuit touches every wire near the end) and selected
`identity` for the adders; the reference circuit alone is used.

## Exploratory: reusing one reference with `ReferenceChecker`

No raw records were kept for this section; the ratios are orientation only.


Twenty equivalent variants checked against one reference, `order="auto"`:

| Reference | Backend | Independent checks | `ReferenceChecker` |
| --- | --- | --- | --- |
| random 14×60 (seed 2) | zdd / zdd-native | 6249 ms / 669 ms | 646 ms / 100 ms |
| random 12×50 (seed 7) | zdd / zdd-native | 12369 ms / 1386 ms | 853 ms / 127 ms |
| Cuccaro 14-bit | zdd / zdd-native | 21.3 ms / 4.6 ms | 8.9 ms / 1.3 ms |

The reference is simulated once and the candidates share its sub-diagrams. The shared node table
keeps growing across checks, which `Budget.max_nodes` or `max_bytes` bounds.

## Exploratory and rejected: one-pass inverse miter

Simulating `left ; right⁻¹` once and comparing with the identity was measured against simulating
both circuits. It was never faster on equivalent pairs (within ±2 %) and up to 9× slower on
non-equivalent pairs (`random_14x60_1`: 265 ms → 2368 ms), because the midpoint state is as large
as `left`'s outputs and the second half no longer shrinks for a mutant. It was not implemented.

## Exploratory, not changed: Python ZDD operation cache

Replacing the clear-all operation cache of the Python ZDD with an unbounded one changed simulation
time by about 4 % on dense random circuits (2.31 s → 2.27 s, 8.50 s → 8.19 s). It was left as is.
