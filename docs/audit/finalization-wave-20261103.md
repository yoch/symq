# SymQ finalization gate — 2026-11-03

This is a **non-merging handoff** for the independently staged review wave tracked by [#171](https://github.com/yoch/symq/issues/171). It is not an approval to integrate or release. Re-read all live GitHub refs, reviews, threads, diff and checks before acting.

## Current exact refs inspected

Current main: `7861aa9d4a31791644382df8bdfd5abbcdf4a628`.

| PR | Role | HEAD | Exact-head CI observed | Notes |
| --- | --- | --- | --- | --- |
| [#173](https://github.com/yoch/symq/pull/173) | #135 + exclusive directory claim | `cc5a355c696cb639d192371fc9009451c0369ce0` | 14/14 general + 4 specialized success | HEAD is one test-only commit newer than PR description's `1e56a54` |
| [#174](https://github.com/yoch/symq/pull/174) | #168 LRAT and Lean hardening | `fcd95b03b3ba37864bcb6e26e0cb04ec314ff65f` | 14/14 general + 7 specialized success | Research only |
| [#175](https://github.com/yoch/symq/pull/175) | #169 axioms/theorem build fixes | `9ae758af9487e1429d8145c62f9de1cc546f171f` | 14/14 general + 1 specialized success | Development/CI-only |
| [#176](https://github.com/yoch/symq/pull/176) | README proposal | `48b67a32ffc33e32077a3b0aa97857beb372be1b` | 14/14 general success | Based on old main, needs post-integration wording |
| [#177](https://github.com/yoch/symq/pull/177) | combined #174 + #175 | `3652bf28cd183bee8b3ced295341de29dc7750e3` | 14/14 general + 8 specialized success | **Excludes #173 and #176**; local 6201 pass, 210 optional skips reported, not independently rerun here |

All above PRs were Draft/open; there were **zero GitHub review submissions and zero review threads** when inspected. Their own PR descriptions still contain some earlier "CI pending" claims. [#171](https://github.com/yoch/symq/issues/171) had not yet received the promised comprehensive post-CI synthesis; it contained the historical #135 report only.

## Gate 1 — close open technical and documentary questions before an integration decision

**#173 publication semantics.** The original racy `os.rename` empty-directory overwrite is fixed by exclusive `os.mkdir` and `open('xb')`, with deterministic tests. However `_publish_exclusive` creates the final directory **before** writing files, then writes `preparation.json` last. That is no-replacement and a completion *convention*, not atomic directory visibility. In current main, `rewrite_request.load_request_files` reads `request.json`, `source.json` and `replacement.json` without requiring `preparation.json`, so the guide's instruction "a directory without [marker] is incomplete and must not be used" is not mechanically enforced by that proof CLI. This is a **contract/ergonomics gap to verify**, not demonstrated false mathematical verification, because the actual verifier parses and checks its bytes. Select one defensible policy: enforce a marker for *recognizably prepared* directories while preserving backward compatibility of ordinary rewrite requests, or state explicitly that the marker is advisory to an external workflow and prove the proof CLI is safe on any partially published combination. Add a deterministic barrier/failure regression. Define trusted vs hostile concurrent filesystem actors, no-replace guarantees and cleanup/durability separately; do not promise portable atomic visibility that `mkdir` + individual file writes cannot deliver.

**#174 and #175 Lean proof claims.** The CI report-parser bypasses were corrected, but the allowlist of 54 **theorem names does not pin theorem statements**. A named declaration could be weakened while still compiling and emitting an admissible axiom report. Do not claim a general theorem merely from its name. Independently compare statement types/assumptions against the documented specification, preserve exact source hashes, show no unexpected semantic changes in the audit-fix diffs, and decide whether an independently maintained statement-contract list or stronger theorem-type check is needed. Keep the trust distinction: independently checked *formula* UNSAT ≠ verified source-to-CNF refinement ≠ fully verified SymQ Python; formal abstract model ≠ formally proved runtime. The Lean checker is a targeted CI hardening gate, not a universal malicious-source sandbox.

**#176 README after integration.** README currently says "independently checked certificate: No" and omits the already promoted `symq.experimental.table_xor` from its task chooser. If #174 integrates, the blanket "No" becomes misleading for the *narrow optional labs LRAT proof path*. Amend with three precise evidence tiers (trusted solver decision, optional independently checked restricted CNF/formula witness, development-time Lean abstract theorems) and explicitly say no end-to-end Python quantum certification. Include already-supported table-XOR API, and `symq prepare-rewrite` *only if #173 integrates*, always distinguished from proof. Verify runnable examples and links after combining code.

**Documentation hygiene.** Ensure public `docs/index.md`, `docs/labs/README.md`, `CHANGELOG.md`, guides, limitations, theorem names and optional dependencies align with the final merged tree; no premature stable API promises. Report negative benchmark cases, not just positives. #26/#27 stay independent research/paper Drafts.

## Gate 2 — choose one final integration unit, not duplicated merges

Do **not** merge #177 plus #174/#175, as #177 already contains their changes; do **not** blindly merge four staging PRs in the suggested sequence, since the #174/#175 overlap in `docs/labs/README.md` was reconciled only in #177's tested combined tree.

Preferred preparation: a **new single Draft integration assembly** from freshly revalidated `main`, merging exact audited #173 and #177 (which contains #174 + #175), and the revised #176 content, preserving full ancestry when possible and clearly handling only justified documentation conflict. Keep the source PRs as immutable review evidence. Do not rewrite their branches. Audit final combined diff/tree and ensure that only intended files and fixes appear. The eventual single merge, if separately authorized, should preserve provenance and avoid double-applying source contributions; after merge, verify source ancestry/contents and only then mark constituent PRs integrated or close with explanation.

Alternatives: if the maintainer prefers separate merge operations, rebuild an *incrementally validated* integration chain with exact tree + checks at **each** step and explicitly re-resolve overlapping index entries. Do not reuse #177's original CI to certify a different post-#173 tree.

## Gate 3 — qualification of the actual intended final source

Run full source tests and required targeted tests for #173 (including race tests), #174 (`lrat_rup`, `phase_proof_bundle`, Lean kernel source checker) and #175 (formal CNF, DAG, phase), and every README Python/Bash example/link test against an installed wheel/sdist and checkout. Matrix should cover Python 3.10–3.14, macOS, native/pure, SAT with/without PySAT, relevant sanitizers and Lean 4.19 pinned workflows. Treat all 210 optional skips transparently by marker and installed environments; fail if any mandatory SAT/formal/Lean regression is skipped.

Record **complete exact commit SHA, Git tree SHA, source→CI link and statuses** on the combined PR, plus the successful synthetic merge's parent refs and tree identity. Make test assertions for accepted positive/refused negative, tampered source/proof and timeout behavior.

## Gate 4 — documented final signoff

Post an updated synthesis to [#171](https://github.com/yoch/symq/issues/171) with the *current* heads, corrections, CI run IDs, findings, full test commands, exact combined tree, review/thread state, and a matrix `ACCEPTABLE_LABS` / `DEV_CI_ONLY` / `NEEDS_FIX` / `DOCS_PROPOSAL`. Clarify any actual blockers; no rhetorical "ready" if the required review is absent. Update stale PR descriptions/checklist.

Do not mark PRs ready for review, approve, merge, close source PRs, publish packages/papers or alter main without **separate explicit maintainer permission**. No default engine change or general-purpose quantum certification claim. Use read → conditional write with expected SHA → read verification for any staged changes.
