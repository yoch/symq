# Experimental roadmap implementation status

Base: `main@dcbd41a6e4642b9d2f7150ae7058ceca1611fc2a`.
The stable verification facade retains its existing theorems. New capabilities
are opt-in, installed experimental APIs. These are computational checks with
explicit trust boundaries, not a formally verified implementation.

| Lot | Delivered behavior | Remaining adoption gate or deliberate limit |
| --- | --- | --- |
| A0 | Capability inspection, source-pinned fixtures, development/holdout manifest, reproducible evidence | Synthetic holdout does not establish external workload generality |
| A1 | Shared VerificationSession, inherited native deadlines, SAT budget rejection, spawned hard-limit runner | Cooperative guards and address-space limits remain different guarantees |
| A2 | Exclusive profiling of the actual public verifier, JSON/HTML and real counters | Instrumentation overhead excluded from comparative timing claims |
| A3 | PR88 strict importer reused; actual pinned Qualtran GF2MulMBUC decomposition, m1/m2 fixtures and mutants | Large Qualtran sizes are not yet independently checked with a dense oracle |
| A4 | Installed contracts, diagnostics, monolithic/block eligibility and explicit dispatch | No automatic theorem or backend fallback |
| B1 | Shared rename_many, per-root admissibility and diagonal precheck before y | Workload-wide speedup not established by microbenchmarks |
| B2 | Explicit native 128-variable mode and high-bit witnesses | 256 deferred: no demonstrated corpus pressure beyond 128 paired variables |
| B3 | Reduced sign/HMR channels with ordered output maps and different ancillas | The output map is explicit; observed classical records require an instrument |
| B4 | GF(2) coefficient reduction modulo constants with reconstruction metadata | Applies to forgotten outcomes; metadata is not a standalone certificate |
| B5 | Strict fused native HMR propagation with Python/scalar references | Tiny wrapper benchmark includes a slowdown; no general speedup or stable adoption claim |
| B6 | Reachable union, memory statistics, direct DAG collection and simultaneous clone reservation | Owned handles only; hard memory enforcement comes from subprocess isolation |
| C1 | FullCube, affine, reversible preparation and Boolean predicate coherent domains | Basis-state spans; no arbitrary quantum-state preparation grammar |
| C2 | Frozen prepared reference, owner-local roots, per-compare budgets and bounded result cache | Sign/HMR monolithic engines only; no persistent raw IDs |
| C3 | Transcript-bound local channels/instruments, proved clean cuts, terminal traces, dirty correlation identity, phase ledger | Exact local oracle bounded; clean preparation analysis deliberately conservative |
| C4 | Versioned obligation DAG, replaying kernel, dependency-addressed cache and bounded parallel subprocess audits | Disk receipts are untrusted; repeated hybrid oracle runs are not implementation diversity |
| C5 | Installed API/CLI, self-contained replay artifacts, example documents, HTML profiles, wheel checks | Stable facade adoption remains separate |
| D1 | Sparse exact phases modulo 2**k with complete XOR lifting and global-phase distinction | Polynomial expansion remains resource-bounded |
| D2 | Exact bounded cyclotomic reference and validated affine-event factorization | Boolean coherence kernel does not generalize; exact counterexample documented |
| D3 | Immutable event/SSA view, strict QASM3 subset, protected lowering and exact shared hybrid branches | General hybrid path remains exponential; live-classical branch limit documented |
| D4 | Optional QCEC unitary H/Clifford+T adapter with explicit global-phase convention | Dynamic circuits and arbitrary floating-angle lowering rejected |

## Validation and qualification

The suites include independent scalar/Kraus comparisons on all small-domain
coherences, negative mutants, high-bit native boundaries, deadline regressions,
native memory stress, transcript/graph mutations and installed CLI roundtrips.
See [evidence and commands](roadmap-evidence.md), [phase semantics](experimental-phases.md),
[composition limits](experimental-composition.md) and [Qualtran provenance](../benchmarks/corpus/qualtran/README.md).

An independent implementation audit compared 301 program pairs and 3,610
coherences against the hybrid oracle, including affine/predicate/prepared
domains and prepared comparisons. It exposed and fixed two prepared-reference
defects: validation time outside the budget and mutable public contract state.
Their deterministic regression tests remain in the suite.

Performance qualification retains negative results. The public campaign
compares current Python ZDD and native ZDD on declared cases; it does not by
itself isolate the effect of each new optimization against the previous native
engine. The native microbenchmark separately measures shared renaming, DAG
reconstruction and fused HMR wrapper costs. No production-wide gain is claimed.

## Existing issue reconciliation

- #57: 128-variable representation implemented; 256 remains gated.
- #56: existing reconstruction replaced by owned DAG transfer; reachability and clone peaks measured.
- #85: typed SSA/import/lowering and existing exact hybrid semantics installed; scalability boundary retained.
- #89: existing classical transcript preserved and installed, with separate quantum composition.
- #91: explicit HMR event/phase-debt obligations checked; no optimizer or automatic rewrite discovery claimed.
- #100: public corpus, evidence, explicit API and package qualification supplied; stable promotion remains open.

Development changes are reviewed as stacked pull requests. Merging requires
separate authorization. Historical archives remain byte-identical.
