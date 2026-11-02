# SymQ research priorities after #158 — 2 November 2026

Baseline: main@91c1d3d1a4a157c8e8e5b9badb198e3d623ffc60, tree
b821ca0e04f0ce5f40a04f95cbaba621439ce225. Priority 1 is new proof capability;
priority 2 is controlled promotion of mature interfaces. These are separate gates.

## 1. State of the art: what to reuse, not rediscover

The scope is exact compiler/circuit verification, not experimental verification
of an untrusted quantum computer. The following are primary research or official
documentation, checked on 2 November 2026. This is a targeted review, not an
exhaustive systematic survey or a claim that all implementations were benchmarked.

| Family | Relevant work | Consequence for SymQ |
| --- | --- | --- |
| DD portfolios and ZX rewriting | [MQT QCEC documentation](https://mqt.readthedocs.io/projects/qcec/en/stable/equivalence_checking.html), [PyZX API](https://pyzx.readthedocs.io/en/latest/api.html) | Complement exact proof and counterexample routes. Failed rewriting is not inequivalence. Do not duplicate a universal matrix/ZX checker. |
| Symbolic paths plus decision procedure | [Huang et al., TACAS 2026](https://arxiv.org/abs/2604.24504) | Reduction first, WMC on the residual closes gaps beyond Clifford normalization. Relevant as a fallback, not a reason to expand every arithmetic block. |
| Hybrid programs | [Chareton et al., Hybrid Path-Sums, PLDI 2026](https://arxiv.org/abs/2604.24578), [Ricciardi et al., deferred measurement bridge](https://arxiv.org/abs/2511.22523) | Symbolic hybrid execution and separation/projected comparisons are established directions. Explicit branch enumeration is not a fundamental requirement. |
| All-outcome stabilizer reasoning | [Kliuchnikov, Paetznick, da Silva, 2026](https://arxiv.org/abs/2603.24717) | Track phases and symbolic outcomes jointly. Their symbolic-angle equivalence needs angle correspondence; it is not arbitrary non-Clifford equivalence. |
| Relational invariants | [Amy and Lunderville, POPL 2025](https://arxiv.org/abs/2410.23493) | Linear/nonlinear abstract relations and phase folding are prior art. Our opportunity is source-bound certificates at arithmetic cuts, not claiming to invent nonlinear invariants. |
| Local projections | [Manjushri, 2026](https://arxiv.org/abs/2601.22372) | Local constraint representations can win on shallow workloads; circuit depth/structure matters. Published benchmark ratios do not transfer to SymQ's corpus. |
| Families, not instances | [Parameterized Verification of Quantum Circuits, POPL 2026](https://arxiv.org/abs/2511.19897) | Eventually certify generator families rather than one emitted width. This needs an induction/automata interface, not more random tests. |
| Quantitative guarantees | [SAQR-QC, PLDI 2026](https://arxiv.org/abs/2507.13635) | Approximate guarantees need a separately typed norm/error contract. They must not weaken exact equivalence labels. |

Recommendation: specialize in source-bound arithmetic, phase and measurement
obligations, with independently checked witnesses and reusable proof obligations.
Keep QCEC/PyZX and future HPS/WMC routes as comparisons/complements.

## 2. New executable direction: anchored Kraus separability

The #157 checker enumerates legal basis inputs and up to 2^H HMR outcomes.
For its closed sign/permutation/hybrid grammar, instead compile one symbolic trace:

```math
K_m|x\rangle = 2^{-H/2}s(x,m)(-1)^{p(x,m)}|F(x,m)\rangle.
```

Here m includes *immutable* HMR/Z-measure/reset events; s is Boolean branch support,
p is the sign exponent, and F is the full output bit vector. Slots may be overwritten,
but event identities never are. Guarded measurement/reset is not admitted, so H is
fixed by the source. A real source document is parsed and hashed; the caller does
not supply trusted F/s/p polynomials. Let D denote the nonempty legal input domain,
x0 a legal basis anchor, and U the exact XOR-table isometry with every output retained.

Check the following Boolean identities for all x,m:

```math
D(x)(s(x,m)\oplus s(x_0,m))=0,
```
```math
D(x)s(x,m)(F_i(x,m)\oplus U_i(x))=0\quad\text{for every output }i,
```
```math
D(x)s(x,m)(p(x,m)\oplus p(x_0,m))=0.
```

**Proof.** The first identity makes every branch either active for the entire legal
support or identically zero there. The second fixes its output vector. The third
makes its sign independent of the legal input. Thus on the whole coherent span,
K_m=c_m U with c_m=2^(-H/2)s(x0,m)(-1)^p(x0,m). Trace preservation of the validated
source grammar gives sum |c_m|^2=1, hence equality of full channels, including an
external reference. Conversely, an isometric target channel has rank-one Choi
support, so every Kraus restriction must be proportional to U; all three identities
follow. This is a specialization of the rank-one-channel criterion already used
in #157, **not a new Kraus theorem**.

The computational improvement is to decide symbolic identities instead of
materializing every branch. The pilot uses canonical Boolean ANFs. A nonzero ANF
has a concrete satisfying assignment: take a minimum-popcount monomial and set
exactly those variables. The campaign independently checks every resulting
refutation against rational density evolution. A future CNF/SAT route can check
the same obligations without expanding ANFs; that route is not implemented here.

This is a new SymQ research direction, not a verified novelty claim over HPS or
all-outcome simulation. It includes nonlinear MCX and conditional value updates,
but excludes general H/S/T/rotation interference, visible records, discarded
quantum outputs and arbitrary non-isometric target channels.

### Pilot results and limits

The local standalone pilot was executed, not merely sketched. At seed 159:
400 generated programs times 12 table/domain contracts gave 4,800 comparisons;
366 positive and 4,434 negative verdicts agreed with an independently implemented
rational density oracle, and all 4,434 reported witness pairs were checked.
Sources include mutable classical slots, conditional permutations/signs, HMR,
Z measurement, reset and arbitrary borrowed input bits.

A synthetic repeated AND/target-update/HMR/CZ-correction family was decided at
H=1,4,16,32,64,128,256 with no branch enumeration. At H=256 the recorded peak
symbolic-term statistic is 262 and the polynomial-product count is 1,024. The
formal family has 2^256 HMR histories; we did **not** execute or independently
simulate that many histories. Dense full-coherence checks cover H<=4; larger
cases depend on the proved criterion and symbolic implementation. Omitting the
last phase correction is rejected at every tested H.

A counter-frontier is retained: 12 successive Z measurements cause explicit
support-polynomial expansion. At a 5,000-term cap the pilot returns inconclusive,
although one small off-diagonal oracle check already exposes a difference. This
shows why raw ANF is not a universal replacement: early support obligations,
SSA/CNF/SAT and sparse effect representations are the next experiments.

All data are synthetic development data, no untouched holdout. Timings in the JSON
are whole pilot calls on the recorded machine, not speedups over #157, QCEC or HPS.
No stable API, portable certificate, shared VerificationSession integration or
formal proof-assistant kernel is claimed. The pilot's closed parser is independent
research code; unification with maintained snapshots is an adoption prerequisite.

Run from an installed checkout:

```bash
python -m pytest -q tests/test_anchored_kraus.py
python -m benchmarks.anchored_kraus --programs 400 --output evidence/anchored-kraus.json
```

The dedicated workflow binds source hashes and the tested Git commit/tree. Local
standalone runs do not substitute for that installed-package qualification.

## 3. Beyond affine signatures: phase cancellation before factoring (#148)

The desired obligation is delta(x)=R(h(x)) mod 2^k, with h extracted from the real
dephaser and outputs already checked. Factoring *each phase predicate separately*
through h is sufficient but incomplete, because weighted predicates can cancel.
For a,b Boolean, let h=ab, p=a and q=a XOR ab. Neither p nor q is constant on the
h=0 fibre, yet

```math
2[p]+2[q]=2[h]\pmod 4.
```

A per-predicate factorization rejects this valid aggregate identity. Therefore
prioritize certificates for successive bits of the **aggregate** modular residual:

```math
r_j=(\delta-\sum_{i<j}2^i[b_i(h)])/2^j,
\qquad r_j\bmod 2=b_j(h).
```

The division is allowed only after exact divisibility of the numerator is proved;
it is not inversion of 2 in Z/(2^k). Induction gives a checkable k-level certificate.
This converts discovery into Boolean functional-dependence problems and can
exploit the existing invariant/cut machinery. It remains a research proposal,
not an implemented general nonlinear phase checker in this PR.

## 4. Priorities and promotion

First: anchored symbolic HMR obligations, then a SAT fallback on the same theorem,
nonlinear dyadic fibre certificates, and independent proof-kernel/replay evidence.
Next: typed composition and cached preparation at cuts; integrate representatives
from real compilers with licensed provenance before performance claims.

The mature initial API candidate is the standalone phase-free table XOR adapter:
its unchanged audited implementation can move to an explicit maintained opt-in
namespace with legacy imports preserved. This is handled in a separate API PR.
Do not promote the new anchored pilot, HMR prototype or basis-search study. Phase
delta binding and ancilla-property interfaces require helper/API separation first.
