# External audit mission — SymQ integration wave, 3 November 2026

**Repository:** `yoch/symq`. **Tracking:** #171.
**Role:** independently adversarial reviewer and pre-integration architect. You may create isolated *Draft* audit/integration work for review, but **no merge, no mutation of main, no publication, no automatic API promotion**. Respect `AGENTS.md`.

## Mandatory revalidation before any claims or writes

At preparation, `main@7861aa9d4a31791644382df8bdfd5abbcdf4a628`, open #135 HEAD `a5b59fa1b9661aeaf1dd4596d77e157db8e34cba`, #168 HEAD `148efeba7d28dc8379c1f707b68c1954f327e7d2`, #169 HEAD `12b5b0e47c18ad98e37585be523608a1fcd0ff4c`, #26 HEAD `5cd554c49ec5659b34d0ac48f2d69de89cb851d2`, #27 HEAD `dfd4dc0503c4514a9f8a6368bbe996855479ca92`.

FIRST use connected GitHub to reread owner/repo, main SHA, each PR base+head SHA, **actual diff/files**, reviews, unresolved threads, workflow runs and relevant jobs. Historical CI receipts are not validation of another SHA or assembled merge. If no Git network, refuse mutations and limit conclusions to SHA-identical cached bytes only. Read `AGENTS.md`, `docs/plans/2026-11-03-integration-readiness.md`, `docs/plans/2026-11-01-substitution-roadmap.md`, the existing rewrite/table-XOR/experimental/HMR guides and relevant tests.

## Priority 1: establish why #135 remained open; then adversarially audit it

Read the real PR diff (not description), especially `src/symq/labs/rewrite_prepare.py`, CLI changes, `tests/test_rewrite_prepare.py`, locator, full-width rewrite parser and replay.

Try to break:
- uniqueness / multiple spans, incomplete/unmapped wires, noninjective maps, bool-as-int, malformed gate or out-of-bounds index;
- frozen source, exact [start,stop) match and remapping; mutated inputs after preparation; stale path hashes;
- classical contract requirements, dirty borrowed wires, false restoration, invalid coherent/HMR substitutions;
- source- or JSON-tampered report, lost original files, early timeout, absent SAT, inconsistent result;
- incomplete serialization, 2 MiB input cap, overwrite, concurrent output directory creation, symlink and `os.rename` TOCTOU semantics (a check-then-rename may not guarantee race-free no-replacement on every platform);
- the distinction `ready_for_proof` vs `proved` vs `application.applied`, and user-specified cost weights vs official quantum cost.

Reproduce small exhaustive reference truths and one **authentic public** wider dirty-frame case. Count independent negative refutations vs safe unsupported/inconclusive statuses. Make the final API proposal only after this audit, not as a substitute.

## Priority 2: independently audit #168 proofs

Read `src/symq/labs/lrat_rup.py`, `lrat_export.py`, `phase_proof_bundle.py`, `lrat_lean.py`, the pinned `formal/portable_lrat` project, tests, source obligation generation and two CI workflows.

Attack malformed DIMACS/LRAT, unknown/duplicate/out-of-order hints, RAT/deletion semantics, tautologies, zero/header/counter handling, int/Unicode/byte/visit/time bounds, false final conflict, stale success fields and forged source/candidate/support/contract/digest. Rebuild the obligation from actual source independent of untrusted bundle; check exact CNF pin and witness validity without PySAT installed. Where possible, cross-check tiny formulas against brute force and a distinct C proof checker.

For Lean, verify literal polarity, clause numbering, exact formula identity, the actual kernel-run success, permitted axioms and negative-trace meanings. Prove that `emit_lean` says **emitted**, not verified, until Lean has actually run. Separate restricted RUP formula proof from higher-level source-to-CNF correctness and from channel semantics; no generic end-to-end quantum certification claim.

## Priority 3: independently audit #169 formal algorithm invariants

Inspect *all* new Lean files, axiom checker, Python graph snapshot validator and actual Graph/SAT code, not only the theorem names. Pay special attention to duplicate logical keys: a free-input physical DAG may be SAT with two independent nodes sharing one logical input name; completeness needs the proven uniqueness guard. Test Python `True == 1` interning-history counterexample and whether post-hoc graph snapshots can prove the original call-site types (they cannot without extra invariant). Examine signed physical edges, node1 true, root asserted separately, lazy clause emission and phase carry. Distinguish an abstract formal theorem from machine-checked refinement of actual Python source.

Lean is dev/CI only. Report precisely which universal properties are proved and which implementation and quantum semantics remain trusted.

## Priority 4: staging integration, interfaces and docs

After standalone verdicts, build disposable integration branches from a *revalidated current main*, one PR at a time and then eligible combinations; never write the original PR branches as an alternative to review. Check duplicate index edits in `docs/labs/README.md` (#168/#169), toolchain/workflow coexistence, packaging, Python 3.10–3.14, macOS, native/pure, wheel/sdist, tests and strict non-skipped SAT/formal obligations. Run CI and review **published final tree**, not a predecessor.

API: `symq.experimental.table_xor` is **already supported** after #159/#165; use it as the model. Consider a narrow `symq.experimental.rewrites` only after #135 and its dependencies are genuinely maintained outside labs. Do not introduce a shallow facade that imports labs or collapse SAT/Boolean equivalence into coherent channel truth. Keep synthetic-only HMR affine/reset, phase discovery and proof modules under `symq.labs` until representative real serialized licensed loader proofs and public contract/replay evidence exist.

README: current root was recently carefully rewritten; produce a more task-first navigable version with a short tutorial, theorem/API capability matrix, precise statuses and layers, link integrity and tested commands. Move deep technical and historical details to guides, keeping safety caveats intact. The current statement about no independent UNSAT certificate cannot be rewritten before #168's integration is validated.

#26/#27: do not bulk merge 189 files; #119 already integrated the independent CUDD lifetime repair. Keep paper scientific qualification, negative benchmark evidence, holdout and release approval separate.

## Required output and verdicts

Deliver:
1. A per-PR matrix: fresh base/HEAD/tree, reviewed file paths/diff, actual reviews/threads, **exact-SHA CI**, abstract and source-level theorems, limitations, finding severity and reproduction.
2. Minimal regressions (or proof arguments), distinguishing confirmed bug, hypothesis and safe unsupported; no invented run claims.
3. Exact recipe and manifest of independently staged (not merged) integration trees, cumulative conflicts and final CI.
4. API decision per candidate: `PROMOTE_OPT_IN`, `MERGE_LABS_ONLY`, `NEEDS_FIX`, `KEEP_RESEARCH` or `DO_NOT_MERGE`; define typed migration/compatibility policy where applicable.
5. README outline or isolated docs-only Draft PR and command/link tests.
6. Short maintainer handoff: merge order, blockers, what can safely be delegated next.

Stop on unproved positive, false source pin, inherited budget violation, unsupported quantum theorem, stale CI, missing reviews or unexamined final tree. **No merges or publication without separate maintainer approval.**


## Required first step — historical exclusion vs technical rejection

Before deciding **anything** about #135, independently corroborate:
- [#147](https://github.com/yoch/symq/issues/147) explicitly *excluded* #135
  from its audited five-PR integration; #158 merged a deliberately selected
  different set. Follow-up #165 was scoped to #159–#162.
- #135 is still Draft/unmerged, has no independent review/threads/comments,
  and its own description says no merge authorization was granted.
- main lacks `prepare-rewrite` and `labs/rewrite_prepare.py`. Its new behavior
  is not duplicated by #134's `locate` / `rewrite` / `replay`, nor by
  `symq.experimental.table_xor`. Confirm by reading source, not names.
- Despite being three commits ahead and 108 behind, #135's four modified
  tracked files and tested direct dependencies have identical Git blobs on
  its merge base and main at this audit snapshot. Revalidate before a staged
  integration; do not claim 108 commits represent code conflicts.

Classify the *cause* separately from the *merit*: documented scope exclusion
and incomplete audit gate are facts; presumed intentional long-term abandonment,
redundancy or previously discovered bugs are **not** supported. Do not quietly
merge because the integration appears easy.

**Adversarial regression required before recommending merge:** `os.rename`
can replace a concurrently created empty directory on POSIX after a racy
existence check. This behavior was reproduced independently with temporary
directories (not by executing the actual #135 function). Reproduce at the
actual callsite, propose a cross-platform true no-replace final publication
scheme, test deterministic two-worker races, symlink swaps, preexisting empty
and nonempty directories, and cleanup on refused publication. This is a
new medium-severity *filesystem contract* concern, not a known mathematical
unsoundness or historical reason for non-integration. Other checks in this
audit document remain mandatory.

The updated sequencing is: verify provenance / duplication → adversarial
review and fixes → exact-source qualification → disposable current-main
assembly → new exact-tree CI → maintainer decision about labs/CLI merge →
later, separate opt-in API and README promotion. Treat #135 as **HOLD /
AUDIT_FIRST**, not as already **MERGE_RESEARCH**. No merge authorization.
