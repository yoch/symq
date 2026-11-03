# External adversarial audit — SymQ research wave A/B/C, 3 November 2026

**Repository:** [yoch/symq](https://github.com/yoch/symq)
**Coordinator:** [#179](https://github.com/yoch/symq/issues/179)
**Status:** independent audit and optional disposable integration assembly **only**.
**No merge, main write, API/default-engine promotion, release or manuscript publication.**

## Historical reference snapshot, NOT a substitute for rereading GitHub

- Main: `766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc` (squash of #178).
- [#183 reset proof/candidate](https://github.com/yoch/symq/pull/183):
  `1552cc0783e6de8341d026429f07d0582edf27de`.
- [#184 classical SAT-miter CNF/RUP](https://github.com/yoch/symq/pull/184):
  `11a3aeeedd4f848bffa6a83a4d46edbaccc4d754`.
- [#185 public-source / actual Qiskit](https://github.com/yoch/symq/pull/185):
  `332828316ab44c56a804be578e176cf351561d34`.
- [#181 roadmap handoff](https://github.com/yoch/symq/pull/181):
  `04b266f5fd6867df5e241d809f93b113b68acc8f`.

All three implementation PRs are still Draft at preparation. Earlier exact
HEADs had green CI, **but current HEAD checks and independent reviews must
be re-read before any conclusion**. No individual PR has an independent formal
review recorded at the opening of this mission.

### Mandatory first step

Read `AGENTS.md`, the full actual diffs and surrounding main implementation
(not just PR bodies), current repo default/base/head SHA, PR review submissions,
unresolved threads, all workflow run jobs and artifact identity for **every**
PR. Read the existing #140, #167, #170, #179, #180 discussions and
`docs/audit/next-wave-{compiler-handoff,hybrid-resets,proof-seam}.md`.
If local git is unavailable or stale, reconstruct SHA-identical snapshots
via the GitHub connector; do not trust a branch name as a tested commit.
Every correction: **read → conditional write (expected SHA, no force) → read
back full head/tree and final diff**. Run CI and test the final published tree,
not an earlier one. No background agent or assumed future CI completion.

## B — #183 affine support / coherent reset identity (highest safety priority)

Inspect ``ymq.labs.reset_support` source and tests against the actual
`HybridProgram` and independently implemented density/Kraus oracle.

1. Re-derive and test the theorem: for legal input span
   `span{|c ⊕ Bu⟩}` and a prefix of basis permutations plus diagonal
   sign gates, if the target-bit ANF is **identically zero** on every legal
   coordinate `u`, then every coherent output has a clean `|0⟩` factor and
   the CPTP reset acts as identity there. The declared domain is *caller
   supplied*, not proof of compiler reachability. This does **not** cover
   HMR, measurement, feed-forward or arbitrary mixed channels.
2. Challenge GF(2) affine rank validation, duplicate/dependent columns,
   nonzero offset, wires at arbitrary positions, ancilla zero restrictions,
   CSWAP, MCX, phase gates, dirty borrowed wires and external-reference
   coherence. Verify the minimum-degree ANF monomial really yields a basis
   witness with target 1 for a nonzero polynomial, against independently
   sampled and exhaustively enumerated small circuits.
3. Attack `build_clean_reset_candidate`: source mutation after snapshot,
   forged/modified report, partial prior clean resets followed by a
   nonclean one, unsupported classical control or HMR, nested deadlines,
   product/term/operation resource limits. Never return a candidate unless
   **all** removed reset sites passed a fresh proof on the actual frozen
   source. Specifically audit the new oversize-operations preflight:
   no source hash means **no source-bound certificate**.
4. Compare all matrix units `|x⟩⟨y|` in an independently implemented small
   oracle, both before and after reset deletion; don't use a shared SymQ
   ANF engine as the *only* oracle. Test phase changes preserving basis
   truth but not coherence; ensure unsupported returns no positive.
5. The 40-wire / 35-affine-rank / 89-reset fixture is **synthetic** and
   partly overlaps already-merged `affine_table` research. Do not present
   it as a real loader or novel general 40-bit HMR capability. Benchmark
   preflight and full process RSS, not just ANF monomial counts.

## C — #184 pinned SAT-miter CNF and solver-free LRAT/RUP

Inspect `miter_cnf.py`, `miter_proof_bundle.py`, `lrat_rup.py`,
`lrat_export.py`, ``ymq.sat.encoding`, ``ymq.sat.miter` and the tests.

1. Verify that the frozen source/`Contract` exactly determines the
   normalized Tseitin CNF. Removing duplicate literals and *tautological
   clauses* must preserve SAT/UNSAT. The normalized proof CNF is **not
   byte-identical** to the original SAT solver clauses; producers must
   generate proofs against the exact normalized CNF. Include empty
   clauses, contradictory constants, restored wires, partial observations,
   output maps, variable ordering, positive/negative literal signs and
   constraint satisfiability (vacuous domains).
2. Build a **separate reference oracle** for small complete reversible
   circuits and test per-input satisfiability both at source and CNF level,
   including wrong circuits and deliberately incomplete contracts. Attack
   canonical JSON/source SHA, mutable caller circuits and contract maps,
   different source under the same candidate, changes in the normalized
   formula after proof generation, and schema/encoder version drift.
3. Independently examine RUP hint replay, clause identifiers, positive-hint
   subset, malformed syntax, additions/deletions/RAT refusal, false-final
   contradiction, fake SAT/UNSAT success, budget expiry after success,
   oversized source/proof memory usage and read-after-mutating inputs.
   Producer is **untrusted**: replay the proof through the solver-free
   consumer with the actual independently supplied source fingerprint and
   rebuilt CNF; verify no PySAT is needed by the consumer. A forged bundle
   or the wrong source must not yield `proved`.
4. Evaluate the new complete-circuit contextual example (prefix, middle
   CCX, suffix) under an input-domain restriction, and its false-domain
   and mutated-prefix negatives. **Global classical equivalence under
   declared input conditions is not the stronger local cut-interface
   theorem** and is not a quantum channel theorem. Lean model theorems
   don't formally establish Python source→CNF refinement.
5. Record proof size, producer/consumer time, actual supported/proof-rejected/
   unsupported counts, numeric resource caps, optional solver failures and
   any positive that cannot be independently replayed. Do not relabel
   `inconclusive` as acceptance.

## A — #185 real public Qiskit workflow and performance evidence

Inspect both public-source seeds, pinned licenses, Qiskit script and
isolated workflow, SymQ parser, true source/candidate map, proof and replay.

1. Confirm that the third-party version is **exactly Qiskit 2.6.1** and
   that `transpile(..., optimization_level=0, basis_gates=[x,cx,ccx])`
   actually emitted the two 7-gate circuits. Compare in-memory qubit
   order against QASM2 parsed order, and verify source SHA-256 values
   `312b1320...` and `3269ab93...`. The one-gate alternatives were
   derived *independently*, **not by Qiskit's optimizer**.
2. Re-run at least one fresh pinned transpilation and a full
   `locate → prepare → SAT rewrite → replay`, including a dirty but
   unrelated global frame, wrong candidate and corrupted source/report.
   Verify the exact legal domain at **both initial input and cut**;
   previous A0 CI correctly rejected an incomplete cut predicate.
   For the small phase-free reversible grammar, independently compare
   every legal basis assignment (plus a coherent check on tiny cases);
   do not generalize to measurements/HMR.
3. Inspect the 30 raw timed rows in [artifact 13263531451](https://github.com/yoch/symq/actions/runs/41701010947/artifacts/13263531451)
   on source HEAD `b01ab4db...`. Reproduce at least one pair on a fresh
   environment; report operating system, CPU, Qiskit/Python versions, source
   QASM digests, commands, subprocess startup, wall/CPU, process-wide
   peak RSS and variability. Startup-inclusive median was ~537 ms on both
   tiny cases; proof ~8.8–8.9 ms and replay ~1.6–1.7 ms. These are **not**
   evidence of general compiler speedup or an apples-to-apples external
   verifier comparison.
4. Inspect installed wheel and sdist, absence of Qiskit as a runtime
   requirement, optional skips on general CI and non-skipped dedicated
   Qiskit jobs. Check the 15 paired samples per case and marker handling.
   The two Qiskit examples are near-related **development** cases, not an
   independent untouched corpus. Verify the third-party license notices.

## Cross-branch and integration-readiness checks

- Exact final refs, tree IDs, full diffs, all reviews and CI including
  Python 3.10–3.14, pure/native, Linux/macOS, SAT installed/uninstalled.
  Count optional versus **unexpected mandatory** skips.
- Do not claim any prior passing CI applies after a change; no automatic
  rebuild/merge merely because all branch CI is green. Keep three source
  PRs separate for review; if appropriate stage a fourth **disposable
  Draft** assembly from revalidated main and rerun combined-tree CI.
- Confirm maintained ``ymq`/`symq.experimental` never imports research
  `symq.labs` through an accidental new facade. No default/backend/API
  change, third-party private source dependency, package release or
  research-data publication without separate permission.
- Explicit verdict per PR: `MERGE_LABS_ONLY`, `NEEDS_FIX`,
  `KEEP_RESEARCH` or `DO_NOT_MERGE`. A status can be conditional on
  pending exact-HEAD CI or independent review; passing tests ≠ proof of
  general soundness ≠ merge authorization.
- Separate **critical soundness findings** from bounded-resource/corpus
  limitations. A hypothesis is not a confirmed bug. Preserve clean
  counterexamples/negative results as useful evidence.

## Required deliverables

1. Independent `docs/audit/2026-11-03-next-wave-independent-review.md` with
   PR/base/head/tree, exact reviewed file/line anchors, theorem, trust
   boundaries, adversarial proofs/reproducers, positive/negative/unsupported/
   timeout counters, CI run IDs and unresolved thread status.
2. Minimal isolated fixes/tests on **current exact PR HEADs** only if
   proven necessary; prefer reuse of existing PR branches when authorized,
   otherwise isolated Draft correction branches without touching main.
3. A concise per-PR promotion/integration recommendation, a list of
   remaining real-world corpus/certification gaps and a tested combined
   assembly recipe (not an automatic merge).
4. Update #179 with full SHA/evidence receipts, any blockers and
   the safe order of future decisions. Finish with a maintainer
   handoff, not just a narrative or green CI screenshot.

**Stop rule:** any false positive, proof bound to the wrong source/CNF,
unproven coherent reset elimination, Qiskit provenance error or
mutated contract accepted as proved blocks merging. No merge or public
release is authorized by this audit mission.
