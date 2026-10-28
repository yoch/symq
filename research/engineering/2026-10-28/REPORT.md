# Engineering report -- 28 October 2026

Reference SHA `aaff35f53e3b3997ed201196bb296bf44b5113a7`. Machine: 4-vCPU Intel Xeon VM, Linux
6.12, CPython 3.12.3, GCC 13.3.0 `-O3`. Every number below comes from a JSON file in this
directory or in `../innovation/2026-10-28/`, whose provenance records the SHA.

## 1. Repository state

`main` = `aaff35f`, CI green. Open: #26 (benchmarks), #27 (manuscript), #59 (innovation), #60
(corrected pilots), #61 (cache), #62 (order policy). Nothing merged by this mission.

## 2. Defects found in the previous pilots

| id | defect | effect | fixed in |
|---|---|---|---|
| C1 | `simulate(fragment)` restarts from the identity | every "chunk" was an independent simulation; all liveness figures described a state that never existed | `prototype/continuous.py` |
| C2 | liveness summed `manager.size` per root | shared nodes counted twice, so "dead" was an unbounded over-estimate | `prototype/liveness.py` |
| C3 | the rebuild imported roots then continued in the **old** manager | the measured "rebuild" never happened | `pilot_c_corrected.py` |
| C3b | rebuilding after the last fragment | stale ids, `node id outside this manager` | same |
| A1 | `constant_outcomes` accepted any single-monomial coefficient | `g_j = x0` treated as constant | `factored.py` |
| A2 | pair space built over `2*(data+ancillas)` | circuit width halved for no reason | `factored.py` |
| A3 | the factorisation escaped the budget | unbounded memory on the way in | `factored.py` |
| A4 | `trace_out_ancillas` was not a partial trace | Bell pair gave trace 2 instead of maximally mixed | `channel.py` |
| A5 | pair keys packed into 16-bit shifts | collision above width 16 | `channel.py` |
| A6 | A2b compared gadgets with the identity | answered the wrong question | `pilot_a_corrected.py` |
| B1 | the miter pilot measured nodes only | cannot see "fewer nodes, more time" | `pilot_b_corrected.py` |

All eleven are reproducible and now covered by tests. The historical result files
(`RESULTS.json`, `PILOTS.md`, `PILOT_{A,B,C}.md`) are untouched; corrected results are separate
files.

## 3. Corrected pilot verdicts

| pilot | verdict | evidence |
|---|---|---|
| A (channel criterion) | **sound, narrow** | 14 designed programs: 4 accepted by both criteria, **1 only by the channel criterion** (invertible syndrome pair), 0 disagreements with the exact density-matrix oracle; 550 random pairs in the test suite also agree |
| A (size) | **negative, restated** | expanded and factored phases have the *same* monomial count (1.00 at M = 2…64) because the phase is affine in the outcomes; the factorisation is a decomposition, not a compression |
| B (composed circuit) | **negative, route closed** | the miter is **3.2-6.7× slower** on the family it was designed for (long common prefix), neutral elsewhere |
| C (memory) | **collector justified** | 99.99 % of the unique table is unreachable; a rebuild turns a budget failure into a completed verification with -87 % peak nodes and -27 % time |

## 4. Engine improvements

### 4.1 Bounded cache: lazy allocation (PR #61)

Defect: the lossy cache allocated and `memset` its whole table in the constructor, so a
0.013 ms verification paid 0.5-9 ms clearing 1 M entries.

| arm | small structured (n=11) | dense random (n=3) |
|---|---:|---:|
| before the fix | **1.50×** slower than lossless | 0.63× |
| after the fix | **0.92×** (8 % faster) | **0.69×** (31 % faster) |

The table now starts at 2 048 entries and doubles without rehashing up to the ceiling;
`cache_info()` reports `capacity` (allocated) and `limit` (ceiling) separately.

### 4.2 Variable order: an explicit policy (PR #62)

Seven structural heuristics measured against the identity order:

| heuristic | small DEV (17) | reserved arithmetic (5) | new, unseen (19) |
|---|---:|---:|---:|
| **reversed** | **0.546** | **0.117** (8.5×) | **0.304** (3.3×) |
| degree | 0.894 | 0.223 | -- |
| last_use | 0.772 | 0.156 | -- |
| dfs | 0.954 | -- | -- |
| bfs | 0.967 | -- | -- |
| min_fill | 2.853 | -- | -- |

The textbook heuristics lose to simply reversing the wire order, because the Cuccaro carry chain
runs along `a[0..n-1]` and reversal follows it. The decision rule (≥1.2× geomean, ≤1 regression)
was fixed before the third campaign and met: 3.3× on 19 unseen circuits, 1 regression, 0 wrong
functions.

### 4.3 What was profiled and *not* changed

- **Three-product recursion**: 3.0-3.6 cache misses per node created, so the recursion is not the
  bottleneck; the working set is.
- **Min-fill / DFS / BFS orders**: measured, worse than reversal, not offered.
- **The composed-circuit strategy**: measured, slower, not integrated.
- **Native width > 64**: no connected circuit with a useful question was identified; not started.
- **A native collector in C**: the API-level rebuild already costs 0.3 % of the run, so a C
  implementation is not a priority; it is the version that would ship, not the version that
  decides whether to ship.

## 5. Baseline / improved table

| profile | baseline | improved | gain | memory | coverage | exactness |
|---|---|---|---|---|---|---|
| small DEV, 11 circuits | identity + lossless | reversed + lossless | **0.93** geomean | unchanged | unchanged | identical outputs |
| dense random, 3 circuits | identity + lossless | identity + bounded | **0.69** geomean | 463 MiB → 0 MiB RSS | unchanged | identical outputs, identical node counts |
| arithmetic 12/16/20 bits | identity | reversed | **2.77× / 4.08× / 6.26×** | 3 546 → 758 nodes at 12 bits | unchanged | identical outputs |
| hard circuit 14×200 | identity, monolithic | identity, rebuild at 400 k | budget failure → **38.1 s** | 12 M → **1.44 M nodes** (-87 %) | **+1 circuit** | identical outputs, checked schedule-independently |
| all 16 circuits pooled | -- | -- | **1.86×** total wall | -- | -- | -- |

Provenance: `RESULTS_CACHE.json`, `RESULTS_ORDER*.json`, `RESULTS_FINAL.json` (this directory) and
`../innovation/2026-10-28/RESULTS_C*.json`.

## 6. New capabilities

- `symq.order_for` / `algebra_order` with `POLICIES = ("identity", "reversed")`.
- `NativeZDDAlgebra.cache_info()` now distinguishes `capacity` from `limit`.
- `prototype/continuous.py`: apply a gate list to an existing state (the missing primitive that
  every pilot needed).
- `prototype/liveness.py`: exact live-node count.

## 7. Still open

1. **A native collector.** The API rebuild works; a C rebuild that copies the live sub-DAG would
   remove the 0.3 % transfer cost and the monomial expansion.
2. **Memory actually returned to the OS.** Node counts are exact; RSS after `free` depends on the
   allocator and was not measured.
3. **The order policy on non-arithmetic structure.** The one regression (`new_mcxchain_20`) is
   unexplained; the policy is documented as measured on structured reversible circuits.
4. **The channel criterion against Irene and phased outcome-complete simulation.** Not done;
   neither tool accepts this fragment directly.
5. **A public measurement-assisted corpus.** Until one is imported, the practical value of the
   criterion is unmeasured, not negative.

## 8. Priorities by impact

1. Native collector (turns budget failures into completions; measured headroom: -87 % nodes).
2. Order policy as the default for arithmetic circuits, once a structure detector exists.
3. Bounded cache as the default for large circuits, keeping lossless for sub-millisecond ones.
4. Everything else in section 7 is research, not engineering.

## 9. Scientific contribution

**None established.** The only non-trivial result is the channel criterion: sound, verified
against an exact oracle, and strictly more expressive than the outcome-independence obligation --
but it accepts one designed program class and no real compiler output was shown to need it. The
order and cache results are engineering: the reverse order beats min-fill because of how Cuccaro
adders lay out their carry chain, which is a fact about the circuits, not a new algorithm.

## Verdicts

**PILOTS: `PARTIALLY_VALIDATED`.** All three were measured correctly after the fixes, but two of
the three original conclusions were wrong (B inverted, C's magnitude understated) and pilot A's
criterion has no demonstrated user.

**ENGINE: `MATERIAL_IMPROVEMENT`.** A circuit that failed at every budget tried now verifies in
38 s with identical outputs (-87 % peak nodes), and 19 unseen circuits run 3.3× faster under a
validated order policy.

**Science: `ENGINEERING_ONLY`.** Nothing measured here is a new method; the strongest claim is a
correctness/expressiveness improvement with no demonstrated need.
