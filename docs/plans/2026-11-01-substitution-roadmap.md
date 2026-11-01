# Contextual substitution roadmap — 2026-11-01

Reference: `yoch/symq` `main@a2fcadab86360444c46e8345a6ba63fa7b3cec28` (merged #122, ABI 6).
This file is a plan; the integration status at the end says what is implemented.
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

## Integration status — 2026-11-01

The draft PRs #123 to #132 were reviewed and integrated into one branch from `main@a2fcada`.
Their branches are kept for reference. Status by workstream:

| Workstream | Status | Where |
| --- | --- | --- |
| A contract/docs rebaseline | Integrated | [rewrite guide](../guide/rewrite.md) |
| B classical contextual rewrite | Integrated: theorem `classical` (SAT) and `classical_total` (symbolic engines) | `symq.labs.contextual_substitution` |
| C coherent local HMR rewrite | Integrated: `local_coherent_channel` / `local_coherent_instrument` with library-side caps | `symq.labs.hybrid_substitution` |
| CLI and receipts | Integrated: `symq rewrite`, `symq replay`, one shared core proving each rewrite once | `symq.labs.rewrite`, `symq.labs.rewrite_request` |
| D public corpus and comparison | Integrated as development evidence with raw records | [comparative pilot](../evidence/comparative-pilot-2026-11-01.md), `benchmarks/corpus/bilinear_kmb` |
| GF(2^n) synthesis | Integrated: tower factors, pinned 2634-CX GF(2^24) order, exact rewrites | [synthesis guide](../guide/gf2n-synthesis.md) |
| E maintained stable facade | Not started | Needs a separate review and an explicit API decision |

Defects found in review and fixed during integration:

- A timeout in a second proof was reported as an input error; each rewrite is now proved once,
  and a timeout is `inconclusive`.
- A rewritten circuit could be built from a forged result; only the checker that proved a
  rewrite attaches its candidate.
- HMR cost weights never applied to Toffolis written as `mcx`; weights are keyed by name and
  arity, and the published deltas were recomputed.
- The HMR benchmark's "independent" oracle reused the checker's code; it now uses the
  independent Kraus oracle of the test kit.
- Cached factor builders skipped argument validation; validation now runs first.
- The GF(2^24) claims rested on sampled states; they are now proved on every input.

Remaining gates:

- The corpora were explored during development. An untouched corpus of independently compiled
  arithmetic pairs, with matched repetitions, is still needed before any comparative claim.
- Saved receipts are not independently certified proof artifacts; replay reruns the checker.
- Promotion of a stable facade (PR E) stays a separate maintainer decision.

No code, runtime dependency, private fixtures or data from another project
is introduced by this roadmap.
