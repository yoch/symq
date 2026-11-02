# Affine target table qualification — exact checkpoint

Research PR #162, initial executable checkpoint
`d8bcd0ae740de7175626314a23777dc7c0abe26b`, based on #160 at
`9fb2996dcde790bb6ce5bdc64b4d1a40fb132cbb`.
Tested synthetic merge `02995d25690b34a826074adb95769d54b0a9755a`;
tree `27273e825e92a831a1309360c2e09405a6af3d06`.

[Qualification run](https://github.com/yoch/symq/actions/runs/41469391261).
Downloaded artifact 13154846953 ZIP SHA-256:
`ca895785d406ca7cc7f21578a56f2d1819c48c77da23a415470e3e4d252bbc57`.
The digest equals GitHub's API value; recorded commit/tree and all six executable
source hashes match the exact published and locally inspected contents.

## Actual results, not dimension-based extrapolation to real loaders

For each of ANF and SAT, 100 generated sources x6 affine target spaces give
600 small complete-density comparisons, with5 equivalent /595 not-proved and
595 independently checked physical witness pairs. The spaces include nonzero
offsets, singletons, proper correlated subsets and alternative full-rank bases.
This random cohort is dominated by negative cases; separate unit tests build
50 positive table loaders and exercise all their legal matrix units.

The large **synthetic** fixture uses128 physical wires,40 target bits of rank35,
1363 legal addresses,89 HMR and89 resets on proven-zero scratch. Both engines
return equivalent in all three repetitions, with all89 reset events eliminated.
The declared basis contains1363*2^35 = 46,832,323,395,584 states; these are
quantified symbolically, not enumerated or independently density-simulated.

| Metric | ANF | SAT |
| --- | ---: | ---: |
| Median whole call, three trials | 0.370190 s | 0.094537 s |
| Peak explicit term statistic | 3173 | not applicable |
| Polynomial products | 504210 | not applicable |
| Boolean graph nodes | not applicable | 5285 |
| CNF clauses | not applicable | 16997 |
| SAT calls | not applicable | 40 |

These are development-case timings, not a general speedup or process-memory claim.
The phase-sensitive fixture is deliberately invalid on a full40-bit target cube:
both engines reject the widened contract with a scalar-replayed phase witness.
All outputs and the five repeated coordinates remain observed.

## Baseline reset reproduction

The original #160 files were reconstructed and Git-blob authenticated locally:
`anchored_kraus.py` =05bcf86ed64eba0dc93f0f60e218674f99472009;
`anchored_stream.py` =7aec9d06589bbd4e2de70e76b717213ed48d8ca5.
On89 zero resets, the original reference returns inconclusive at5001 terms
(limit5000); streaming proves equivalence, eliminates89 events and peaks at4 terms.
The feedback about exponential support therefore applies to the reference path,
not to the already available streaming path. No proof of zero was assumed from a
caller label; the source equations establish it.

Local execution used an authenticated minimal Python snapshot:9 ANF tests passed;
no local native/PySAT/full-repository run is claimed. The installed-package CI
executes actual Glucose and the SAT tests. Invalid domains, missing legal rows,
phase/borrowed-output mutations, offsets, snapshot isolation and inherited caps
are retained. No actual production binary or independent table from an application
was supplied to this qualification. No scientific/private fixture was published.

See [the schema and theorem](../labs/affine-target-tables.md). A later documentation
commit does not inherit a CI status merely from identical engine bytes; its own
checks must still be read. Independent review remains required before adoption.
