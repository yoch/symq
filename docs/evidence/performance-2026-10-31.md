# Performance changes of 31 October 2026

Paired, in-process measurements taken with `python -m benchmarks.quick` (median of five runs per
cell, the same circuits and the same seeds before and after each change). Machine: 4-core Intel
Xeon, CPython 3.13.18, python-sat 1.9.dev17 (Glucose 4.2), native core ABI 6; baseline commit
`eb43db3`. These are relative measurements of one implementation against its predecessor on one
machine, not comparisons with other tools. Raw JSON records are produced by the harness and not
committed.

`dev`, `holdout` and `extension` are the fixed QCEC corpus splits; `synthetic` is the harness's
family of Cuccaro adders (8, 16, 24 bits) and dense random circuits (14 wires, 60 and 90 gates).
The holdout split was not looked at while making these changes.

## SAT encoder: shared inputs, structural hashing, constant folding

Both circuits of a miter now read the same input variables (no tying clauses), identical AND/XOR
definitions are encoded once, and X gates become literal negations instead of a forced-true
variable plus a four-clause XOR.

| Split | Cells | Geometric mean time ratio (new/old) | Best | Worst |
| --- | --- | --- | --- | --- |
| dev | 10 | 0.50 | — | — |
| holdout | 12 | 0.45 | 0.23 | 0.65 |
| extension | 16 | 0.46 | 0.25 | 0.89 |
| synthetic | 14 | 0.26 | 0.007 | **1.45** |

Largest absolute changes: `add6_196` equivalence 660 ms → 296 ms; `random_14x90_1` equivalence
914 ms → 246 ms. One cell regressed: `random_14x60_1` equivalence, 1.45× slower, a solver-heuristic
effect on an otherwise smaller formula. Verdicts and witness replay are unchanged; the encoding is
checked against concrete execution on every input of random circuits
(`tests/test_sat_equivalence.py`).

## Variable order for equivalence: `order="auto"`

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

## Reusing one reference: `ReferenceChecker`

Twenty equivalent variants checked against one reference, `order="auto"`:

| Reference | Backend | Independent checks | `ReferenceChecker` |
| --- | --- | --- | --- |
| random 14×60 (seed 2) | zdd / zdd-native | 6249 ms / 669 ms | 646 ms / 100 ms |
| random 12×50 (seed 7) | zdd / zdd-native | 12369 ms / 1386 ms | 853 ms / 127 ms |
| Cuccaro 14-bit | zdd / zdd-native | 21.3 ms / 4.6 ms | 8.9 ms / 1.3 ms |

The reference is simulated once and the candidates share its sub-diagrams. The shared node table
keeps growing across checks, which `Budget.max_nodes` or `max_bytes` bounds.

## Rejected: one-pass inverse miter

Simulating `left ; right⁻¹` once and comparing with the identity was measured against simulating
both circuits. It was never faster on equivalent pairs (within ±2 %) and up to 9× slower on
non-equivalent pairs (`random_14x60_1`: 265 ms → 2368 ms), because the midpoint state is as large
as `left`'s outputs and the second half no longer shrinks for a mutant. It was not implemented.

## Not changed: Python ZDD operation cache

Replacing the clear-all operation cache of the Python ZDD with an unbounded one changed simulation
time by about 4 % on dense random circuits (2.31 s → 2.27 s, 8.50 s → 8.19 s). It was left as is.
