# Mathematical and claim review of paper A

Reference manuscript: PR #27 at
`605e3f47e20eb05a34b732d535c3f3dab5c8247a`.
Integrated-code reference supplied and remotely revalidated for this task:
`main@332de59677bd5e21a125c5d6f6f5f43264b4b734`.
This is a paper derivation/review, not a machine-checked proof or a new C audit.

| Statement | Reasoning independent of test success | Scope/remaining assumption |
| --- | --- | --- |
| Boolean-ring canonicity | Subset-lattice Möbius inversion gives a unique square-free ANF for each Boolean truth table | Standard known mathematics, not a SymQ novelty |
| Symbolic circuit soundness/completeness | Evaluation is a ring homomorphism; induction over validated control/target updates; ANF canonicity | Full Boolean input cube, equal physical frames and ordered outputs; unsupported quantum operations excluded |
| Minimum-degree monomial witness | Every proper subset has smaller degree, so exactly the chosen monomial contributes on its support assignment | Constant monomial is covered; concrete replay verifies a difference, not equivalence |
| GF(2) product recursion | Expand `(P0+vP1)(Q0+vQ1)` and use `v^2=v`; terms cancel modulo two | Two-product alternative requires the low `P0Q0` term, missing from old FORMAL_MODEL; repaired |
| Canonical ZDD equality | Fixed order, unique triples, strict child levels and zero suppression | Only within the same manager/generation; cross-owner raw IDs cannot be compared |
| Abort-only budgets | A non-aborted exact transition sequence retains the unbudgeted semantics | Does not prove responsiveness, cache recovery, memory isolation or C safety; late results must be withdrawn |

The old `FORMAL_MODEL.md` alternative recurrence dropped the low term even though
`main.tex` already included it. A counterexample is `P0=Q0=1`, `P1=Q1=0`. The
correct identity and this counterexample now appear in both statements. The old
claim that abstract budget soundness proved mutable-manager recovery was too
strong; recovery/ownership obligations now remain explicit assumptions with
separate tests.

The pure, independent graph check `paper/tools/ofdd_vs_zdd.py` was executed on all
Boolean functions for n=1,2,3,4: 4,16,256,65,536 functions respectively, with equal
canonical positive-Davio and monomial-ZDD graphs under one order/owner. This
supports the known representation relationship on that bounded domain. It proves
neither the general theorem by testing nor the current C implementation.

Accounting regressions for the independent paper generator demonstrate that
repeats do not become extra circuits/families, family weighting differs from
circuit weighting, unsupported/unrun cells remain in denominators, duplicate
trials fail and unestablished export/replay/provenance flags cannot be counted as
successes. Exact execution/CI receipts are attached to the eventual published
paper HEAD, not this document's branch name.

Old C overflow/width behavior, unbounded-cache descriptions, missing SAT evidence
and obsolete HMR prototype descriptions are now separated from current code.
The classical propositions supply no all-coherence HMR theorem: channel,
instrument, preparation and phase claims require their own independent
assumptions and derivations in the installed research documents.

Scientific release remains blocked on broader evidence, independent final
review, author/content approval and license/disclosure decisions. No submission,
new authorship assertion or external publication occurred during this revision.

A second, separately tasked agent reviewed the classical derivations and
implementation-assumption boundary on 30 October 2026, at local paper integration
HEAD `6d3ef38a9d947c68ec166fd864ddcbaa92e3f9f9` and `main.tex` snapshot SHA-256
`a19042221cae4a4427cd9b33ecd080a0d581224a1f507186cef9bc1f8135d85e`.
It found no mathematical blocker within that narrow scope and identified two
measurement-wording corrections: exclusive cleanup is not instrumented, and the
current manifest has four families rather than the historical five. Both were
corrected. This bounded AI-assisted derivation review is not independent
maintainer acceptance, a complete implementation audit or machine verification;
it did not review the final campaign data or prove C correctness. The
scientific-release checklist stays open.
