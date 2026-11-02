# Qualified phase-feature strategies: logarithmic separators and source seeds

Research PR #163, based on integrated main@755385e1e638365282e9cfccebdba4ce41fda451.
This note records the exact executable checkpoint, not a blanket claim about
later commits, the stable API, or real application circuits.

## Exact checkpoint and inspected artifact

- Executable HEAD: `a5447223f6fc4f12015903efc319506ea0e98f44`.
- Tree: `379bf88a192689159b25b55653be65ea737a6df0`.
- Synthetic CI merge: `94288501cfac2fea17542c4e65ea78593a0aa9cc`.
- The GitHub commit was reread: parents are the main SHA above and the executable
  HEAD; its tree equals the tested branch tree.
- [Installed-package qualification](https://github.com/yoch/symq/actions/runs/41510286384)
  passed Ruff, all six targeted test modules, then all three research campaigns.
- Downloaded artifact13172837994 ZIP SHA-256
  `e70c35c39abf6a13c0de0e5d8add142a4a21bece04c91352fe9376769262f39a`
  was independently recomputed and equals the GitHub API digest. Its commit.txt,
  tree.txt, passed flags, individual qualified rows and positive fresh-check results
  were inspected. The three JSONs retain all timed trials and source manifests.
- Recorded engine identities: phase_adaptive SHA-256
  `0a8832b0ccbdfac83bbaf48ebef16030cf2496e27ef919b01391e1dee8a3360a`
  (Git blob a71d0cbbb0ae96a718055c128c75db90240f1e39), phase_separator SHA-256
  `625fabbfbf64978be6a6b0b7988182de365eac4f1ee10fc43f8c7ce482f9f25b`
  (Git blob fbcb2514d1b5fb3d7d458c6283775667952fc39f).

Python3.12.15 on the platform recorded in each JSON. No local installed-SymQ,
PySAT or native/full-suite execution is claimed; local pure-kernel tests are
separate from the actual Glucose/source results produced by this CI run.

## 1. Degree bound: constructive but not a universal optimization

For N distinct signature samples a monomial with odd incidence exists of degree
at most floor(log2 N), constructively found by minority-cube splitting and parity
removal of negative literals. The bound is tight on a Boolean cube and is also a
consequence of Reed--Muller duality/distance, not a newly discovered coding theorem.

Local pure tests: all65,808 nonempty sets in widths1..4 pass the parity, degree and
deletion-minimality conditions;500 wider seeded sets reach width256. On those
small sets the halving degree is lower/equal/higher than the old greedy rule on
20,180/41,839/3,789 sets. These sets are not necessarily real learner obstructions.
For the retained constructed S_m family, old greedy gets stuck at degree m while
halving returns degree3 through m=255. This is a local feature-selection result.

The final source campaign checks all256 h=(ab,bc)->Z/4 functions for both methods:
512 successful positive rows, each with an exact channel oracle and fresh
external source-certificate check. Source seeding is also exercised on the same
256 functions in tests, not counted as an independent holdout.

Five randomized-order repetitions per method on three-term sparse source families:

| Signature bits | Greedy median ms | Halving median ms | Greedy samples/features | Halving samples/features |
| --- | ---: | ---: | --- | --- |
| 4 | 7.448 | 7.973 | 12/12 | 13/13 |
| 8 | 14.622 | 14.821 | 19/22 | 19/22 |
| 16 | 21.815 | 25.434 | 19/30 | 21/32 |
| 24 | 22.059 | 25.465 | 14/33 | 16/35 |

No end-to-end speedup is established here. Greedy remains the default.

## 2. Negative frontier: low-degree search can need exponentially many samples

For the jointly surjective signature h_i=a_i*b_i and phase bit product(h_i),
canonical ANF needs the degree-d monomial. Starting linear and using only the
logarithmically bounded rule requires at least2^d distinct signature samples.
Tests at d2/3/4 observe exactly4/8/16 samples. This is a lower bound for that
policy, not for sparse Boolean learning generally.

The separate24-row frontier campaign keeps a common64-sample cap. At degrees7
and9 BOTH unseeded strategies exhaust it; their refusal stays inconclusive.
Thus an unrestricted greedy separator alone does not solve this constructed
case either. Failed searches are not labelled channel differences.

## 3. Source structure avoids this frontier in a restricted but exact family

An optional source_monomials=True pass recognizes source phase monomials that
are exact products of monomial coordinates of the extracted effective signature.
Boolean variable-mask unions certify that local factorization. It only seeds the
INITIAL feature dictionary: the complete channel/phase obligation is still
queried and every positive freshly rechecked. Aggregate carries/cancellations
are not replaced with a predicatewise acceptance rule.

The72-row paired campaign compares seeded/unseeded greedy/halving on d3/5/7/9/16/32,
three randomized-order repetitions, the same initial constant/linear dictionary,
sample cap64 and feature cap256. Every expected trial qualifies. The table shows
the greedy choice; seeded halving has the same sample/feature counts and verdicts.

| Degree d | Unseeded result / samples | Source-seeded result / samples | Features with seed | Median unseeded / seeded ms |
| --- | --- | --- | ---: | --- |
| 3 | proved /8 | proved /4 | 5 | 3.658 /2.078 |
| 5 | proved /32 | proved /4 | 7 | 24.717 /2.447 |
| 7 | inconclusive /64 | proved /4 | 9 | 93.850 /2.844 |
| 9 | inconclusive /64 | proved /4 | 11 | 109.699 /3.460 |
| 16 | inconclusive /64 | proved /4 | 18 | 136.060 /5.292 |
| 32 | inconclusive /64 | proved /4 | 34 | 163.161 /12.034 |

Inconclusive-versus-proved times are not comparable completion speedups. The d5
pair is a measured improvement on this constructed family only. At d32 there are
64 free physical input variables,65 data/work wires and one dephaser ancilla.
No enumeration of that input cube or independent density simulation at that width
is claimed. The small fixture oracle and exact fresh symbolic verifier support
separate layers of validation.

With an explicitly constant-only seed plus the discovered product, unit tests
at d3/7/16/32 succeed in two samples. That different initial dictionary is not
silently substituted for the linear-seed paired benchmark.

## Boundaries, tests and adoption

The algebraic factor proposal was also tested locally on1600 seeded systems and
20116 reconstructed products; CI repeats independent scalar evaluation of a
smaller exhaustive-assignment cohort. Tests include invalid proposed masks,
wrong fresh proofs, cap refusals, source changes, real signature collisions,
late expiry and unchanged default behavior. Initial lint-only failures were
corrected with test-fixture fixes, not disabled checks.

No general sparse-learning complexity improvement, real compiler or KMB evidence,
untouched holdout, process RSS result, portable proof kernel or independently
checked SAT-UNSAT certificate is claimed. Source ANF extraction and subsequent
SAT can still expand. Nonmonomial signature/phase expressions simply receive no
structural seed and retain the original exact search route.

See [degree construction](../labs/phase-degree-bound.md) and
[source seed contract](../labs/phase-source-seeds.md). Both new options are explicit;
source_monomials=False and separator_strategy='greedy' remain the defaults. The
research PR remains Draft and requires independent review before integration.
