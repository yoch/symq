# Adaptive source-bound phase dictionaries: qualified executable checkpoint

Repository yoch/symq, research PR #163; default/stable verification unchanged.
Main was merged into the existing research branch, without force-push; the PR now
targets main@755385e1e638365282e9cfccebdba4ce41fda451. The historical fixed discovery
engine and supplied certificate checker remain byte-identical.

## Exact source and CI receipt

- Executable HEAD: `1951cdef7f0bde325f7f0a7b9c47d571df3e259e`.
- Tree: `fd0240442e86b2c4912a4bc4d37bd5b81e8e474b`.
- GitHub synthetic merge: `880c6fa819516816ccbacf7bfaf6199f22ebec68`.
- Its parents are main@755385e and the executable HEAD above; its tree is identical.
- [Dedicated installed-package qualification](https://github.com/yoch/symq/actions/runs/41504061076)
  passed Ruff, the adaptive/fixed/adversarial/completion tests, then the campaign.
- Downloaded artifact 13170726480 ZIP SHA-256
  `160822457f337b4ab98c709dd79b822a717e3520bd308e24f72a91eb8ae1e5cc`
  equals GitHub's API digest. Its commit/tree files match the synthetic merge.
- Engine SHA-256 `cbc5a6ebf9d7b8f4413c4444c6626c77318728657e6ce80c611497caa27c3356`
  and benchmark SHA-256 `30e0c3ce7d045034a75aa5938a847bf1263f8dc7b9234062ddbfda5693fba345`
  were rehashed against the exact locally authored/published bytes. The six inherited
  source/oracle digests agree with the prior pinned campaign and those files are
  unchanged. The JSON retains all eight identities and every trial.

This receipt is for the specified executable checkpoint. General multi-platform CI
and any later documentation-only commit must be checked at their own HEAD. No
local installed-SymQ/PySAT/native/full-suite success is claimed.

## Cohort outcomes

Python 3.12.15, Linux-7.0.0-1017-azure-x86_64-with-glibc2.43. For all 256 functions
h=(ab,bc)->Z/4, each source pair is first confirmed equal by the independent exact
Kraus/cyclotomic oracle. The three-method campaign gives 768 successful expected
rows, with no failures:

| Method | Proved and freshly rechecked | Dictionary exhaustion |
| --- | ---: | ---: |
| Fixed degree <=1 | 64 | 192 |
| Fixed degree <=2 | 256 | 0 |
| Adaptive from degree <=1 | 256 | 0 |

All 576 positive rows receive both the learner's internal fresh source check and
the harness's external recheck. The 192 fixed-dictionary refusals are not channel
differences. The adaptive route adds the missing nonlinear feature in these cases;
its growth records independently satisfy zero-old-row XOR, nonzero label XOR,
odd new-column parity and increased rank. Literal source samples are checked too.
This is reused constructed development data, not a new independent holdout.

## Constructed scaling and retention of non-wins

Signature coordinates are disjoint pair-ANDs; source phases contain only three
simple terms of degrees 3,3,2, each at a different dyadic weight. The table below
is NOT a representative real compiler workload. These larger source claims are
symbolic, not exhaustive density simulations of their input cubes.

Feature cap is 256 for both discovery methods. Three complete-call trials:

| Signature bits | Full degree <=3 dictionary | Fixed result | Adaptive final features | Adaptive median |
| --- | ---: | --- | ---: | ---: |
| 4 | 15 | proved, 6.584 ms | 12 | 7.325 ms |
| 8 | 93 | proved, 13.909 ms | 22 | 14.563 ms |
| 16 | 697 | inconclusive, feature cap | 30 | 22.172 ms |
| 24 | 2325 | inconclusive, feature cap | 33 | 21.886 ms |

Every positive is rechecked. The last two rows demonstrate avoiding a dense
feature layer under a common explicit cap, not an inherent failure of a fixed
method with a more generous cap or a well-chosen manual dictionary. The first two
rows are retained counterexamples to a uniform speedup claim.

On the same paired cohort, incremental basis reuse reduces refits:

| Signature bits | Refit-every-sample rebuilds | Incremental rebuilds | Refit median | Incremental median |
| --- | ---: | ---: | ---: | ---: |
| 4 | 19 | 14 | 7.479 ms | 7.325 ms |
| 8 | 32 | 26 | 14.538 ms | 14.563 ms |
| 16 | 32 | 26 | 21.832 ms | 22.172 ms |
| 24 | 22 | 16 | 22.004 ms | 21.886 ms |

The candidates, samples, rank-growth history and SAT graphs agree exactly. Mixed
small timing changes over only three repetitions do not establish a runtime gain.
No total RSS measurement or memory-speed superiority is claimed.

## Defect found during wider qualification

At first checkpoint22516fb, the separator itself was correct and the small
installed-source campaign passed, but a wider pure-kernel test exposed an
excessively strict assertion: after adding one column the previously failing row
was required to become independent. A new column can instead consume an earlier
dependency; prefix rank increases while another inconsistency remains. This was
an exception/refusal on a solvable sample system, not a false positive proof.

Words (0,4,5,3,6,1,7), labels (137,119,149,233,245,150,254), starting features
(0,1,2,4) reproduce it. The correction checks the actual rank increase and continues
adding valid columns. The permanent regression fails on the first checkpoint and
passes on1951cdef. Further tests cover240 random multi-label systems and an actual
irregular modulo256 source, checked by the independent channel oracle.

The separator was tested locally on65,808 exhaustive sets plus500 wide random
sets. The corrected completion kernel passed1,200 seeded systems /13,987 feature
additions. These pure algebra tests are distinguished from actual Glucose/source
checks performed by CI.

## Remaining research and adoption gates

The greedy separator is deletion-minimal, not minimum degree. Its known suboptimal
example is retained in tests. Source ANF preparation, repeated SAT queries and
fresh checking may dominate, and large signature images can require exponentially
many samples. Initial degree is a seed, not a hard ban on higher-degree features.
Missing dependencies and feature/sample/time limits fail closed. False helper
results, changed sources, inherited budgets and expiry after fresh success are
covered, but this is not a formal proof assistant audit.

No real application loader, portable certificate, independently checked UNSAT
proof, external support preparation, controlled-use permission, optimal sparse
recovery or new general CEGIS theorem is claimed. Independent review is still
needed before integration. [Algorithm and proof](../labs/phase-adaptive.md).
