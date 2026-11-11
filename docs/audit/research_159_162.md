# Audit handoff boundary — 2 November 2026

> **Historical brief.** This file is the instruction given to an independent reviewer at the
> time, kept for provenance. It is not a review report, and the pinned SHAs, pull-request states
> and authorizations it mentions are those of its date, not current ones.

The maintainer requested an independent integration audit of #159–#162 before
adoption, and parallel further research on a separate branch. No merge authorized.

| PR | Pinned HEAD | Parent |
| --- | --- | --- |
| #159 public XOR API | 5dc5808dad8ecfc8103b63d4dac786eef98c1568 | main |
| #160 symbolic/streaming Kraus | 9fb2996dcde790bb6ce5bdc64b4d1a40fb132cbb | main |
| #161 aggregate nonlinear phase bits | 2f992a61a0cf0a60a9e1204ccb2c4c4cd79384d2 | #160 |
| #162 wide affine targets | ad563b802e06f055e9bbafff2909f56519da8f9c | #160 |

main was re-read at 91c1d3d1a4a157c8e8e5b9badb198e3d623ffc60. Re-read remote
metadata, exact diffs, comments/threads and checks before any mutation. Audit
claims attach to exact contents; moving a parent invalidates affected evidence.

Focus: mathematical Kraus/isometry conditions and prefix information leakage;
closed snapshots and event/slot semantics; SAT encodings, watchdogs and literal
witness replay; source-bound aggregate carry arithmetic; dictionary candidate
failure versus true channel difference; affine target rank, offsets, physical
witness decoding, all outputs and independent table construction. Restore all
89 reset obligations, do not rely on an asserted clean annotation. Test the 40-bit
physical /35-free target domain without widening it. The large fixtures are
synthetic, not proof of any real application loader.

The API audit must check byte/object identity, compatibility, import/extras,
packaging and absence of labs dependencies from maintained code. Correct every
reproduced defect on its original PR and requalify dependents. Build a separate
Draft assembly only after individual decisions, preserving exact source content,
then run complete installed/native/SAT/checkout and packaging/doc gates, download
artifacts and verify their identities. No default backend promotion or main write.

The phase discovery work on this branch is **outside that audit scope**. It may
be audited later, after its own qualification; do not add it to the integration
assembly simply because it exists or has green CI. The four original branches
were not edited by this research continuation.
