# Research roadmap (27 October 2026)

## Scientific question

Can an exact verifier select and combine heterogeneous symbolic representations using locally measurable structural features, improving end-to-end runtime and memory without sacrificing semantic correctness?

## Work streams

| Work | Priority | Falsifiable hypothesis | Required evidence |
|---|---|---|---|
| Sparse ANF in-place XOR and fast paths | P0 | Reduces median runtime without correctness regressions | Paired DEV/holdout benchmarks |
| Adaptive ANF/ZDD selection | P0 | Robust gains on structurally difficult circuits after conversion cost | Unseen circuit families; fixed budgets |
| Exact corpus & provenance replay | P0 | Every imported public circuit matches source hash | Content-addressed verification |
| CUDD/PolyBoRi external baselines | P1 | Native baselines distinguish representation from Python overhead | Equivalent semantic contract |
| Hybrid subcircuit representations | P1 | Local conversions outperform whole-circuit conversion | End-to-end ablation with memory |
| Structure-aware decomposition | P1 | Dependency/separator structure predicts symbolic cost | Cross-corpus predictive validation |
| SAT/SMT/e-graph synthesis | P2 | Certified rewrites reduce verification costs | Independent equivalence checker |
| Phase/HMR extensions | P2 | Formal subset semantics match a separate oracle | Explicit assumptions and exhaustive small cases |

## Experimental controls

Capture CPU, RAM, Python version, OS, source SHA, warmups, repetitions, failures, timeouts, RSS and conversions. Separate tuning from final holdout. Compare against reference algebra and external native libraries when available. Never infer universal performance from favorable special cases.

## Publication criteria

A claim should establish novelty against related work, correctness on a precise semantic subset, meaningful external baselines, reproducible data with licensed provenance, and statistics robust to adverse circuits. Negative results should be published in the benchmark record rather than discarded.
