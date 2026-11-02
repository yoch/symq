# Streaming Kraus obligations: eliminate deterministic events, reject leaks early

Research follow-up on #160. The original `anchored_kraus` ANF engine is kept as a
reference; after the #164 audit it also runs under the shared Guard/VerificationSession
(no restarted deadline, inherited node/byte caps refused) and bounded JSON snapshots. `anchored_stream.verify_stream` accepts the same closed
source/table documents and explicitly selects `backend="anf"` or `backend="sat"`.
It is not generic channel or observable-instrument comparison.

## Prefix-information lemma and exact reduction

After eliminating earlier Z/reset events, let r denote only preceding HMR
outcomes. Every r is reachable on every legal basis input with probability
2^(-H_prefix). Immediately before a Z measurement/reset of q, prove

```math
D(x)(q(x,r)\oplus q(x_0,r))=0.
```

If it fails, an immutable prefix environment record distinguishes two legal
inputs. The prefix-record distributions have strictly subunit classical fidelity.
An isometry on the declared coherent support has an input-independent complementary
channel, so a trace-preserving suffix cannot restore the ideal isometry after this
leak. The witness contains two legal inputs, the HMR prefix and operation index;
a separate scalar interpreter replays it before a result escapes. Overwriting a
user-facing classical slot is not erasure of the measurement environment.

If the identity holds, replace the outcome by q(x0,r), a function of existing
HMR variables. No support product and no new random variable are needed. The
measured quantum bit can also be replaced by this expression on D; reset sets it
to zero. Induction gives a support-free symbolic trace. Final all-output equality
and input-independent branch phase are necessary and sufficient for the declared
isometry contract. This specializes information-disturbance / rank-one Kraus facts,
not a claim to discover the general theorem.

Primary background: [Nielsen et al., reversible measurement](https://arxiv.org/abs/quant-ph/9706064)
and [Beny–Oreshkov, channel simulation](https://arxiv.org/abs/1103.0649). These works
are background, not claims that this exact implementation appears there.

## Two representations, one obligation

ANF proves a zero polynomial or gives a minimum-monomial satisfying assignment.
The SAT route builds a shared complemented-edge AND/XOR DAG and incremental
Tseitin clauses. Glucose answers each violation query, under a watchdog sharing
the original deadline. SAT witnesses are independently evaluated through the DAG,
then replayed on the actual scalar source. UNSAT still trusts the solver/encoding;
no LRAT or independently checked SAT proof is emitted.

The whole call includes exact-primitive detached snapshots, preparation, proof,
negative replay and solver cleanup under the original Guard/VerificationSession.
Unsupported inherited node/byte caps are refused. JSON size/depth and graph/clause
caps are explicit. `max_terms` caps explicit polynomials in ANF and generated
clauses in SAT mode; neither is an OS RSS guarantee. No implicit backend fallback.
Dead mutable slots are released after their last read. Live proof expressions
still retain all immutable HMR variables they need.

## Qualification of the executable checkpoint

Checkpoint `c2c9437b44a9df087a29d01e5d2d6337911bae70`:
[run 41460046023](https://github.com/yoch/symq/actions/runs/41460046023),
synthetic merge `385009eaec914a5a8780fb9f890bcf680c7dbe5c`,
tree `eed3d0ae1d31ddf25f2a1648a31e43c8e959799e`.
Downloaded artifact 13147404375 has SHA-256
`d7945146fa131e5537b52837e0623c9386066b5b0336c00793cee15bbbb7cb5f`,
equal to GitHub's digest. Its five source hashes match the published files.
Python 3.12.15, python-sat 1.9.dev17; the benchmark records the runner platform.

At seed311, each new backend agrees with the independent rational-density oracle
on 400 sources x 12 contracts: **4800 decisions, 340 positive / 4460 negative**.
Every negative witness pair is checked on the full coherent channel. These are
synthetic development data, not an untouched holdout.

Median of three complete-call trials (milliseconds); Python allocation peaks are
measured in a separate run, never included in the timing trials:

| Constructed case | Reference ANF | Streaming ANF | Streaming SAT |
| --- | --- | --- | --- |
| 12 input-leaking Z measurements | inconclusive, 2.708 | refuted at first op, 0.176 | refuted, 0.261 |
| 128 measurements of known-zero work | inconclusive, 4.096 | proved, 1.460 | proved, 1.252 |
| Corrected 256-HMR chain | proved, 8.739 | proved, 11.750 | proved, 10.644 |
| Dense conjunction, n=32, inverse control order | inconclusive, 4.751 | inconclusive, 7.088 | proved, 1.165 |
| Same dense case with uncompute omitted | inconclusive, 4.518 | inconclusive, 6.899 | refuted, 1.250 |

The dense n=32 case has 66 physical wires; 161 graph nodes / 319 clauses suffice
for the positive case and 129 / 222 for its mutant (one SAT query each). It is a
constructed representation stress test; recognizing inverse MCX control sets
could also simplify it. These are not speedups against QCEC or another library.

**Retained regression:** strict snapshots/checks make the streaming methods slower
on the easy HMR chain. Slot collection reduces the peak polynomial-term statistic
262 -> 8 and live slots 256 -> 1, but total Python allocation is about 917 KB versus
614 KB in the reference, due to source preparation and other retained objects.
Do not label the term-count reduction a total-memory reduction.

## Reproduction and remaining gates

```bash
python -m pytest -q tests/test_anchored_stream.py tests/test_kraus_graph.py
python -m benchmarks.anchored_stream --programs 400 --output evidence/streaming-kraus.json
```

The dedicated workflow requires SAT, records exact Git commit/tree, and uploads
all trials and source hashes. `tests/test_anchored_independent.py` additionally checks
all three routes against a different generator (scrambled roles, restricted targets,
memory-routed corrections, slot reuse) and the explicit-matrix oracle of #157; the audit
ran the same harness on 1,500 sources (1,188 positive) with no disagreement. Local tests used a connector-authenticated minimal
snapshot; local DAG/CNF checks additionally used an independent Sympy DPLL solver.
The installed-package CI above, not that fallback, validates the actual Glucose
backend. No local full-repository execution is claimed.

Independent semantic audit, portable proof/replay, a more representative licensed
compiler corpus and normalization-aware paired comparisons remain adoption gates.
No default engine or stable API is changed. Nonlinear dyadic phase certificates
are a separate experiment, not silently supported by this sign-only theorem.
