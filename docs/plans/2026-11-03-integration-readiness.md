# SymQ integration readiness — 2026-11-03

**Tracking:** #171. **Mode:** planning / audit only; no merge or API change.
**GitHub source of truth at drafting:** `main@7861aa9d4a31791644382df8bdfd5abbcdf4a628`, tree `c0d4fe53811ec12ad030280f1a906e2654dc386b`. Revalidate before acting.

## Open PR inventory and initial disposition

| PR | Exact HEAD at drafting | Code/diff | HEAD-specific checks observed | Recommendation |
| --- | --- | --- | --- | --- |
| #135 | `a5b59fa1b9661aeaf1dd4596d77e157db8e34cba` | 11 files, +744/-1 | CI 41344896507 14/14 | **HOLD pending independent review**; previously excluded from #147 by design; decide merge candidacy only after fresh audit |
| #168 | `148efeba7d28dc8379c1f707b68c1954f327e7d2` | 21 files, +2357 | CI 41543006359 14/14; portable 41543006384 + Lean 41543006457 successful | Audit proof transport/source binding; **KEEP_LABS** initially |
| #169 | `12b5b0e47c18ad98e37585be523608a1fcd0ff4c` | 22 files, +2510 | CI 41606750120 14/14; formal 41606750135 successful | Audit general Lean theorems and Python seam; **DEV_CI_ONLY** |
| #26 | `5cd554c49ec5659b34d0ac48f2d69de89cb851d2` | 189 files, +151516/-7 | historical CI 40983949217 8/8 | Do NOT bulk merge; split useful protocol tools if independently justified |
| #27 | `dfd4dc0503c4514a9f8a6368bbe996855479ca92` | 43 files, +13323 | historical CI + paper job 40986067840 successful | Independent paper track stacked on #26; NOT release ready |

These are successful workflow observations, not independent soundness review. #26 is unmergeable against its target as observed; #27 targets #26's HEAD, not current main.

## Already integrated: do not recreate or double-promote

- #134: contextual rewrite request/replay and exact cut locator. #135 adds one mechanical operation: turn a unique complete local occurrence into a source-bound full-width request; preparation **does not prove** a candidate.
- #158, #165 and #163: integrated broad audited research under `symq.labs`, with explicit scope and without default changes.
- #159, integrated through #165: supported opt-in reversible XOR-table API under `symq.experimental.table_xor`; historical labs aliases preserved. This promotion is already done.
- `symq.labs.anchored_stream`, `affine_table`, `hmr_table_contract`: exact bounded research for HMR/reset/affine targets. The 40-target-bit, rank-35, 89-reset/HMR example is *constructed* public evidence, not certification of a real serialized production loader.
- Phase factored/discovery is labs-only. #168 now explores portable source-bound proofs; #169 proves abstract algorithms in Lean **at development time**, not Python runtime.

## API maturity decisions

| Surface / feature | Decision and why |
| --- | --- |
| `symq` classical ANF/equivalence and `symq.sat` contracts | Preserve; no new default theorem or implicit backend selection |
| `symq.experimental.table_xor` | Already supported, prioritize examples/docs rather than new wrappers |
| `symq.labs.rewrite_prepare` + `symq prepare-rewrite` (#135) | First narrow integration candidate after audit; separate opt-in API milestone, possibly `symq.experimental.rewrites` |
| Classical/contextual/coherent composition | Keep explicit proof contracts; promoting requires moving coherent dependencies out of labs, not a shallow import alias |
| `anchored_stream` / `affine_table` / HMR table verifier | KEEP_LABS until independent real licensed compiler workload, reproducible coherent oracle, caps and source-bound replay |
| Modular phase / factored certificate / cut invariant / ancilla studies | KEEP_LABS; no stable optimization/proof claim from synthetic studies |
| #168 RUP/LRAT/Lean source bundle | KEEP_LABS until independent proof parsing/encoding audit; formula UNSAT is not end-to-end quantum proof |
| #169 universal Lean development theorems | DEV_CI_ONLY; formal Python refinement is not established |
| #26/#27 | Separate historical benchmark/scientific artifacts; the CUDD lifetime fix was already extracted in merged #119 |

**Promotion gate:** precise grammar/theorem/frames and supported budgets; strictly typed and closed versioned data; no outside-labs modules importing labs; source/contract identity and honest proof/replay semantics; negative, mutant, timeout, unavailable-backend and wheel tests; representative independent public workload; exact combined-tree CI and independent review. The already-promoted table-XOR API is the design model. A trivial re-export of deep labs dependencies is not acceptable.

## Safe integration sequence

**A / #135 (P1).** Audit uniqueness, injective maps, source interval authentication, mutated inputs, false cut assumptions, dirty restoration, invalid gates, output races and max bytes. If sound, assemble labs/CLI-only from *current* main and independently run proof/replay. Do not auto-apply on `ready_for_proof`.

**B / #168 (P1).** Audit standalone restricted positive-hint RUP proof checker, source-bound obligation construction, producer independence, tamper/timeout behavior, Lean literal translation and kernel verification. No general LRAT support or formal source-to-CNF reduction is claimed.

**C / #169 (P1).** Audit 54 named Lean theorem *statements* and proof assumptions, physical versus logical graph IDs, signed edges, CNF root/pins, duplicate logical input names and Python bool/int alias history, modular carry and actual Graph conformance. No Lean runtime dependency.

**D / combination.** Revalidate main; stage each audited PR separately on isolated branches; then test eligible combined tree. #168/#169 both append `docs/labs/README.md`. Preserve both entries; evaluate CI and Lean-project coexistence. A green constituent PR is no proof the assembly is correct.

**E / API & README.** Decide promotion only after independent evidence; separately stage a task-first README change with example tests. No package release, default engine change, broad theorem promise or paper submission.

**Paper track.** #26 is 189-file historical data; #27 is stacked on it. Preserve historical archives, avoid conflating benchmark CPU/timeout measurements with production performance, and do not reimport #119's CUDD fix.

## README vNext — scoped refactor, not a blank-slate rewrite

The current README (Git blob `c5828d8cf668b21f56cbea0b5255342a095ca84a`, about 17.8k characters) already had a careful public rewrite. Proposed first-screen structure:
1. What SymQ proves / what it deliberately does not prove; minimal pure-Python example.
2. Question → theorem → API → evidence level map (ANF, reversible equality, SAT contract, coherent channel/instrument, table-XOR).
3. Local rewrite story: `locate` → `prepare-rewrite` (*not proof; only after #135 integration*) → `rewrite` → `replay` → proven candidate.
4. Installation, optional SAT/native, finite width and resource limits.
5. Clear supported `symq` / opt-in `symq.experimental` / noncontractual `symq.labs` / dev-only `formal` layers.
6. Links to the maintained guides, HMR grammar, benchmarking evidence and limitations.

Move large catalog tables and proofs into guides rather than delete them. Current README's warning that SymQ has no independently checked UNSAT proof certificates is accurate for current main; update *only if* #168's limited capability is audited and integrated. Keep executable examples working from an installed wheel without private fixtures. See `docs/audit/integration-wave-20261103.md`.

## Stop rules

No merge, auto-merge, main write, Python/C formal-verification claim, private artifact leakage, default selection change, version bump, PyPI/arXiv publication or API promotion without maintainer authorization. Correct ≠ tested ≠ reviewable ≠ mergeable ≠ authorized to merge.


## #135 provenance correction — verified 2026-11-03

**It was explicitly omitted, not silently integrated or found redundant.**
Issue [#147](https://github.com/yoch/symq/issues/147) told its audit agent **not** to extend
the five-PR integration to #26/#27/**#135** automatically. Its specific integration
assembly [#158](https://github.com/yoch/symq/pull/158) names its constituents;
#135 is not among them. Later [#165](https://github.com/yoch/symq/pull/165)
also has an explicitly limited #159–#162 scope. The #135 PR itself still says
**Draft, no merge authorization, independent audit pending** and has no review,
review thread or PR discussion comment as reread. No rejection for
unsoundness/redundancy was recorded; the historical cause of non-integration is
**scope exclusion + an uncompleted independent-review/authorization gate**.
An unrecorded personal intention cannot be inferred.

**Still novel functionality:** main has no `symq prepare-rewrite` command, and
`src/symq/labs/rewrite_prepare.py` is absent. #134 supplies exact `locate` plus
the proof/replay CLI, but not the local-to-global lowering between these steps.
The reversible XOR-table API is not a substitute for local rewrite preparation.

**Rebase risk:** at this snapshot the #135 branch is 3 commits ahead / 108 behind
current main (merge base `cbb7bd972fa582e3f087be1213c42e0b97ea0d9e`).
For *all four paths modified* by #135 — `.github/workflows/ci.yml`,
`docs/guide/rewrite.md`, `src/symq/__main__.py`, `tests/test_public_api.py` —
the Git blob SHA is **identical** on that base and current main. The checked
dependency files (`rewrite_request.py`, `rewrite_locator.py`,
`contextual_substitution.py`, `classical_transcript.py`, `Circuit` and
`experimental.serialization`) are also identical. There is therefore **no
observed source-file edit conflict on those paths**; final integration still
requires fresh isolated assembly and exact-tree tests, not assuming correctness
from matching blobs.

**New audit finding, not historical reason:** in #135's
`write_prepared_rewrite`, `if root.exists() or root.is_symlink()` followed by
`os.rename(tmp, root)` is a TOCTOU pattern. An independent POSIX filesystem
experiment confirmed `os.rename` can silently replace an empty directory created
between the check and rename. This violates the stated *never replace destination*
guarantee under concurrency. It is not evidence of unsound symbolic proof and
was **not** a historical reason for leaving #135 open. Require an exclusive
no-replace publication mechanism or a clearly scoped behavior plus adversarial
regression. Check cross-platform semantics, symlinks and error cleanup.

**Decision after correction:** audit #135 as potentially useful,
do not merge until the new finding and other adversarial risks are resolved,
then evaluate a combined-tree labs/CLI integration. Treat API promotion as a
separate decision after this gate, not part of #135's current review.
