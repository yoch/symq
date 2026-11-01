# Contextual substitution roadmap — 2026-11-01

Reference: `yoch/symq` `main@a2fcadab86360444c46e8345a6ba63fa7b3cec28` (merged #122, ABI 6).
This file is a *plan*, not a claim that the features below are implemented or benchmarked.
Owner of final approval/merges: maintainer. All work goes through reviewable PRs.

## Product claim

Given an immutable source circuit, a specific instruction interval, a replacement, and an explicit
input/observation/ancilla contract, SymQ should decide whether the *replacement at that site*
preserves the requested behavior, show which obligations were checked, and report the declared
cost. An unsupported theorem, failed prerequisite, SAT timeout, or missing capability is never a
proof of inequivalence or permission to apply the rewrite.

A valid replacement is not necessarily a cheaper one. The verifier is not an optimization
synthesizer, a general quantum checker, or a formally checked SAT certificate producer.

## Reuse, do not rebuild

| Existing code | Contract it already supports | Adoption work |
| --- | --- | --- |
| `symq.sat.Contract` / `check_sat_equivalence` | Classical observed/restored wires and assumptions | Reachability at the cut, nonvacuity |
| `symq.sat.composition.check_composition` | Four relational obligations with an independent suffix lemma | Build the interface from an actual span and proven prefix |
| `symq.labs.classical_transcript` | Whole-stream, arbitrary-input total local rewrites | Keep for context-free rewrites, avoid duplicating it |
| `symq.labs.channel_composition` | Exact bounded local coherent channel/instrument substitutions | Public nontrivial embedded HMR evidence and convenient invocation |
| `symq.labs.ledger`, `symq.labs.proof_graph` | Phase-debt and independently recomputed obligation DAGs | Compose without trusting stored verdicts |
| `symq.verify` / `symq.experimental.verify` | Typed explicit theorem requests | Do not weaken or automatically select the theorem |

## PR A — Rebaseline contracts and public docs

- Reconcile stale references to the pre-#122 experimental channel API, ABI and caveats.
- Declare the typed input-frame, width, output and resource semantics of any new interface.
- Preserve scope separation: Boolean restriction to basis inputs is not a coherent channel theorem.

Acceptance: no public doc claims an installed capability is still unavailable, no promise of a
stable public API or independent UNSAT certificates, tests validating documentation remain green.

## PR B — Bounded classical contextual substitution (MVP)

- Caller supplies a global reversible `Circuit`, a validated [start, stop) gate interval,
  a replacement `Circuit` using the **same global wire numbering**, explicit original-input
  constants and desired clean/restored cut wires. No implicit wire map or guessed ancilla
  initialisation. The generated candidate is assembled immutably from the source.
- Prove initial-domain **nonemptiness**, prefix establishment of every cut invariant, and
  full-output equality of original and replacement blocks for *all* cut states satisfying the
  checked invariant, by reusing `symq.sat.composition`. Full equality implies safety under the
  actual, shared global suffix; a separate whole-program SAT miter is not necessary.
- Separately prove local restoration of clean and borrowed wires on **each side** under the
  established cut invariant. Equal dirty outputs on the two sides are insufficient.
- Return typed, never-vacuous statuses and obligation summaries. Counterexamples at a cut
  must be described as *cut states*, not fabricated global input witnesses.
- Record complete original/candidate/contract digests; compare exact gate counts and a
  caller-specified simple integer gate-weight model, without calling it T-count or depth.
- Honor a single shared budget, including restoration and result finalisation; refuse resource
  fields the SAT engine cannot enforce.
- Include a positive real-context case, missing-clean-input, swapped span, corrupt replacement,
  dirty-restoration, non-vacuity, timeout, and replay checks. Exhaust all inputs for small widths
  using `Circuit.run` as an independent oracle.

Acceptance: a correct rewrite is accepted, every positive decision follows the explicit four
SAT composition obligations plus any mandatory restoration obligations, and each negative
control is either rejected or reported nonconclusively without an unsound global claim.

## PR C — Contextual restricted HMR rewrite

Reuse `symq.labs.channel_composition.verify_channel_transcript`; do not shortcut to diagonal
Boolean equivalence. Establish clean input preparation from the global prefix, dirty-wire
**coherent-frame identity** (including off-diagonal correlations), live measurement instrument
equality and terminal-only discard. Reconstruct phase debt from *actual* measurement events,
then request an exact channel/instrument obligation rather than trusting the ledger alone.

First fixed public example: the existing small, source-pinned Qualtran/kickmix HMR corpus,
with a missing phase-correction mutant and an embedded connected-wide transcript.
The default bounded local oracle accepts at most six quantum wires and eight measurement
events; describe refusals and do not generalize a successful tiny example.

## PR D — A public comparative substitution corpus

Pair source and replacement streams with licensed provenance, source/compiler SHA, exact
generated commands and checksums; label generated vs hand-constructed vs synthetic.
Publish accepted/unsupported/inconclusive counts, adversarial mutants, complete wall/CPU/RSS
and conversion costs. Compare MQT QCEC, PyZX and Boolean SAT/AIG only on genuinely common
theorems. A QCEC unitary check is not an HMR-instrument baseline.

Current QCEC and Qualtran corpora were already used in development: they cannot be relabeled
as untouched holdout. Issues #18/#44/#46/#100 track the qualification and baseline work.

## PR E — Small maintained facade (separate promotion decision)

After PRs B-D are audited: a stable `check_substitution` interface, CLI, versioned report,
installed-wheel demo, precisely declared exceptions, support matrix and API compatibility policy.
Until then, new orchestration stays in `symq.labs`; do not promote automatically.

## Non-goals / stop rules

No H/S/T or arbitrary rotation semantics added just for coverage; no generalized quantum
claims from basis-state preconditions; no >128 native-ZDD extension without measured pressure;
no merge without independent maintainer authorization. SymQ must remain standalone: **no code,
fixture, import or runtime dependency from a private repository**.

Review gates: exact main/head SHAs, checked diff, mandatory tests with zero unexpected skips,
separate CI on the final published head, and reproducible public fixtures. Existing issue #100
is the qualification tracker; issues #89 and #91 are implemented research foundations, not
new implementation tickets.

## Execution snapshot — 2026-11-01 (experimental Drafts)

This section reconciles the originally proposed work with the currently published
GitHub research branches. It documents evidence, not merge approval or
production API guarantees.

| Workstream | Draft PR / pinned HEAD | Exact-head CI | Qualification boundary |
| --- | --- | --- | --- |
| A contract/docs rebaseline | #123 at 407aaeb1598f272935ce6e69eaeb8f0680e04fe7 | 13/13 | Documentation only |
| B classical contextual SAT | #124 at 4322ba256aa9691fac2fd5a403f2ed1b818b289b | 13/13 | Real cut preconditions, borrowed restoration, pinned proof recomputation, exhaustive randomized tests, conditional MCX decomposition |
| C coherent local HMR | #125 at 9519bc059aaeb20b2116cb65a0f33452b5569536 | 13/13 | Bounded full local coherent-channel/instrument theorem, borrowed identity frame, replay and explicit operation weights |
| D reproducible corpus and crosschecks | #126 at 3589340f63d23c832349838ca068af295f0070dc | 14/14 | 28/28 expectation matches; SAT/QCEC 12/12 correct decisions on identical full-function GF pairs |
| E maintained stable facade | Not proposed | N/A | Requires independent semantic review, integrated checkout and explicit API release decision |

All four Draft PRs still start independently from main at
a2fcadab86360444c46e8345a6ba63fa7b3cec28 (ABI 6);
no merge has been performed.

### Evidence and remaining gates

- The corpus is previously explored QCEC (MIT), Qualtran (Apache-2.0),
  synthetic tests, plus six arithmetic pairs made by different algorithms
  in ONE codebase (SymQ); not independently optimized external compiler pairs.
- The n=4 GF arithmetic pair shows 49 Karatsuba gates versus 28 rank-floor
  gates with an independent exhaustive integer oracle on 4096 inputs.
  This is a small gate-count case, not proof of a hardware/Qant cost gain.
- The 6 paired SAT and MQT QCEC complete-unitary checks returned 12/12
  correct decisions. The corrected timing protocol excludes library import
  but includes conversion: single-run medians ~11.1 ms SAT, ~8.0 ms QCEC.
  No statistically significant or general performance superiority claimed.
- Saved hashes and JSON are not independently certified proof artifacts.
  Experimental replay APIs rerun the same theorem from exact source and
  contract inputs; old positive flags and stale fingerprints cannot suffice.

Next: independent review of actual #124/#125 diffs and their theorem
semantics; reconcile any findings and rerun CI on changed heads;
add a source-cleared untouched corpus of independently compiled arithmetic
pairs, with matched repetition and uncertainty; then decide whether to
propose a small stable public facade. Prior to an authorized integration,
check all source and result identifiers again, verify the entire combined
diff and run post-integration tests on the merged exact tree.

No code, runtime dependency, private fixtures or data from another project
is introduced by this roadmap.
