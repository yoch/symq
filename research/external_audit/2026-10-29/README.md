# Independent SymQ verification guide

This directory is a **standalone public audit checklist** for the five pending research pull requests. It contains no code or fixtures taken from any inaccessible private repository.

## Review these source branches directly

- [PR #90](https://github.com/yoch/symq/pull/90): exact small hybrid CPTP and observed classical instruments.
- [PR #92](https://github.com/yoch/symq/pull/92): transcript-bound local equivalence over connected circuits.
- [PR #93](https://github.com/yoch/symq/pull/93): bounded ANF bitsets, finite domains, GF(2) dual unsat witnesses.
- [PR #94](https://github.com/yoch/symq/pull/94): HMR phase debt synthesis and checking.
- [PR #95](https://github.com/yoch/symq/pull/95): native C/ZDD channel checker and raw benchmark data.

## Mandatory independent checks

1. Compare all input coherences |x><y|, not just computational basis outputs, for every full-channel claim.
2. Distinguish a quantum channel with forgotten measurement records from an instrument with observed classical outputs.
3. Distinguish HMR X-basis measure/reset from arbitrary CPTP reset and from a reset of a provably clean qubit.
4. Mutate HMR feedback, phase signs, event identities, classical slots and borrowed ancilla contracts.
5. For transcript proofs, mutate the common prefix, suffix, local embedding, preserved wires, and pinned full source streams.
6. For bounded-degree ANF, reject overflow rather than truncating. Independently exhaust n<=5 and verify dual GF(2) certificates.
7. Compare native and pure-Python engines on identical accepted grammar, full-call time, process RSS, and resource limits.
8. Treat CI success, soundness, reproducibility and real-circuit performance as separate conclusions.

## Existing directly inspectable evidence

[PR #95 benchmark records](https://github.com/yoch/symq/blob/research/native-hmr-channel-20261029/research/hmr_native_channel/RESULTS/paired-native-20261029.json) and [CI measurements](https://github.com/yoch/symq/actions/runs/40839531614) record four paired synthetic cases (five fresh processes per engine). Their measured source SHA is `7a75f82717801fa8606a35715f5ddaae048a726b`. The C/ZDD path lost slightly on two affine HMR microcases, and won on two nonlinear cases; this is not sufficient for a production ROI claim.

## Unavailable private-source evidence

Historical reference experiments from the inaccessible private qant repository are **not** reproduced here. Do not claim their tests were executed, infer their coverage, or import them into production. If a particular independent fixture or exact theorem witness is essential, document its expected input/output schema and the missing artifact explicitly. A resource gap must never become a proof.

The repository's [AGENTS.md](https://github.com/yoch/symq/blob/main/AGENTS.md) requires self-contained public code, strict semantic eligibility, differential and mutation testing, and reviewable PRs without unauthorized merging.
