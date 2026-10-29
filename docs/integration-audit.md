# Corrective integration audit of PRs 106–112

The independent audit reviewed combined HEAD
`9a1825da91d2811e1f53c73bee398ca3a41507f3`, based on
`main@dcbd41a6e4642b9d2f7150ae7058ceca1611fc2a`. Its tests were fetched directly
from [PR 113](https://github.com/yoch/symq/pull/113), commit
`1f24a81c19cd02da911407d27c73a6c734cb7ef4`. Re-executing that exact source
reproduced **six strict expected failures and two positive passes**. The audit's
green workflow was a reproduction receipt, not evidence of correction.

## Defect disposition

| Independent case | Correction | Required result |
| --- | --- | --- |
| Classical blocks lose elapsed time twice | Absolute inherited deadline; whole-call checks include concrete witness replay | Ordinary PASS |
| Temporal transcript loses elapsed time twice | Same shared deadline API for local lemmas, restoration and suffix work | Ordinary PASS |
| Parent pickle reconstruction escapes hard wall | Closed, bounded worker-side JSON encoding; deadline-bounded receive/decode; no returned object reconstruction | Ordinary PASS |
| Nonlinear phase term with coefficient 0 | Normalize before event dispatch | Ordinary PASS |
| Nonlinear phase term with coefficient 8 | Normalize before event dispatch | Ordinary PASS |
| Seven-wire hybrid inspection claims support | Grammar, static bounds, availability, physical contract and runtime limits reported separately | Ordinary PASS |

`tests/test_stack106_112_adversarial.py` retains the independent assertions and
removes the xfail decorators. Its former IPC skip is strengthened: the
reconstruction marker must remain absent, the result must be inconclusive, and
the elapsed-time assertion remains. Both positive controls remain unchanged.
The dedicated audit workflow requires eight tests, zero failures and zero skips.

Additional tests cover deterministic deadline boundaries and nesting, two local
slots, node/term intersections, late witnesses, preserved wires, suffixes and
isolated graph leaves. Typed-IPC tests exercise arbitrary-object rejection,
oversized results, a delayed parent decoder and valid primitive round trips.
Native tests exercise high words, custom orders, collisions, transfers and
resource failures. Capability tests distinguish raw native widths from paired
channel widths, backend absence, physical mappings, and hybrid width/event caps.
Modular-phase tests exhaust exact outcome sums for k=2,3,4, including negative
coefficients, multiples of the modulus, constants and noncontiguous events.

## Soundness boundaries

| Engine or layer | Established invariant | Explicit limit |
| --- | --- | --- |
| Classical ANF/ZDD | Every deterministic output polynomial agrees; a difference has a concretely replayed input | Reversible Boolean grammar; no quantum-channel conclusion |
| Native 64/wide | Same Boolean ring semantics; owner-local roots, admissible per-root level maps, untruncated external masks | Explicit engines, at most 64/128 variables; no default change |
| Factorized sign/HMR full channel | Outputs, coherence kernel and surviving relative signs agree on every admitted input matrix unit | Declared sign/HMR grammar, prepared ancillas, forgotten events |
| Reduced channel | Ordered retained outputs agree; traced outputs enter each program's coherence kernel | Explicit partial trace, not equality of discarded functions |
| Coherent domain | Both coordinates of every admitted coherence are restricted; parametrizations are injective | Nonempty validated domains/preparations; no diagonal-only shortcut |
| Hybrid exact channel/instrument | Exact Kraus propagation of every input matrix unit, including observed classical records | Six physical wires, eight events, dynamic branch/resource caps |
| Dyadic diagonal phases | Exact multilinear integer polynomial modulo 2^k and deterministic basis permutation | Exact binary rational angles; controlled expansion; strict/global equality distinguished |
| Cyclotomic reference | Exact bounded sums in a cyclotomic ring, with a separately derived affine-event helper | Nonzero nonlinear event terms rejected by helper; no Boolean-kernel type substitution |
| Optional QCEC | External unitary comparison with explicit global-phase convention | Declared unitary fragment only; no dynamic channels |
| Local composition and graph | Complete transcripts, injective maps, proved clean ancillas, dirty correlations, live records and terminal traces; untrusted leaves replayed | Receipts/disk caches have no proof authority; two quantum subprocesses repeat one algorithm |
| Prepared references | Immutable content/contract identity; serialized comparisons in an owned manager; complete live-root remapping | No foreign-manager node reuse or disk receipt accepted as a proof |

See [resource semantics](verification-resources.md) for the exact inherited-clock,
typed-result, trusted-input and OS-cleanup boundaries. Decisions are cooperative
engine evidence, replayed witnesses or composition checks; these are not
independently checked UNSAT certificates.

## Corpus, history and performance

The Apache-2.0 Qualtran GF2MulMBUC fixtures for m=1 and m=2, their source hashes,
bit conventions, product preparation and normalization are unchanged. The m=2
fixture has six physical wires, at the dense oracle's boundary. Strict hybrid
lowering preserves physical operations and needed events; unsupported value
feed-forward/reset semantics are refused. The historical PR 88 importer is
represented by the installed implementation plus compatibility reexports;
integrating another independent copy would duplicate it.

All 210 historical campaign executions and their raw files remain unchanged.
The campaign JSON SHA-256 remains
`939fc71fb911ba1e586f0253fec3bf284322eebbc2d3078ed5b277e780b87218`.
Their original source fingerprints continue to identify the measured sources,
not this corrective HEAD. No scientific campaign was rerun for this audit.

The historical synthetic full-call comparison shows near parity: all six
decisive-family ratio intervals straddle one. Native shared rename/DAG
microbenchmarks showed narrow positive results, while the small fused wrapper
case was slower. Those kernel observations do not establish full-call speedups.
Instrumented profiles, uninstrumented public calls and process startup/IPC/RSS
remain separate boundaries. The new result protocol has not been qualified as a
performance improvement. A future confirmatory campaign should prioritize larger
external circuits rather than additional favorable microbenchmarks.

## Integration decision and order

The seven branches retain their original commits. Corrections are additive;
dependency synchronization uses ancestry-preserving commits, with no force
update or rewrite of research history. No PR is merged and main is unchanged.

After all checks for each published HEAD succeed, the research integration order
is **106 → 107 → 108 → 109 → 110 → 111 → 112**. Each step depends on its previous
stack branch. Revalidate combined-main CI after each separately authorized merge.
The corrected stack is suitable for `MERGE_RESEARCH`, not stable-facade adoption.
A failing/missing exact-HEAD check means `REQUIRES_FIX`; a demonstrated false
equivalence, broken ancestry or provenance change means `STOP`.

The final published HEADs, individual CI receipts, ordinary audit test results
and per-PR decision matrix are recorded in the closure section of
[PR 112](https://github.com/yoch/symq/pull/112). This document deliberately does not
rewrite historical benchmark provenance as a claim about its own later commit.
