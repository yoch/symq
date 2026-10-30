# Scientific and release checklist — review revision, 30 October 2026

**No submission, arXiv deposit, release, DOI, announcement or main merge is
authorized by this task.** A technically buildable PDF is not scientific acceptance
or author consent. Earlier venue/date advice in Git history is historical, not a
current submission schedule.

## Scientific gates

- [x] Scope is full-input classical reversible X/CX/CCX/MCX verification and ANF
  inspection; no universal quantum theorem or new representation claimed.
- [x] Corrected the missing low term in the alternative product identity of
  `FORMAL_MODEL.md`; known propositions and implementation assumptions separated.
- [x] Replayed differences distinguished from equivalence certificates;
  ownership/manager and budget-abort assumptions are explicit.
- [x] Related-work boundaries include PolyBoRi/BRiAl, Minato/FDDs, CUDD, SAT/AIG,
  QCEC, Irene, QuPRS and phased/hybrid checking; primary-source review scope and
  inaccessible publisher pages are recorded.
- [ ] Independent maintainer review of mathematical statements and final claims.
- [x] Short current protocol qualification results checked against pinned raw data;
  all requested statuses/denominators and negative results retained.
- [ ] Publication-scale coverage on independently gathered compiler outputs, not
  only a new synthetic holdout. A short run does not satisfy this gate.
- [ ] Cross-machine sensitivity and stronger external baselines where useful.

## Reproducibility and presentation

- [x] Final source/manifest/native-binary hashes and tool versions recorded.
- [ ] Exact-head CI complete; native and actual pure-Python paths exercised.
- [x] Current and historical tables/figures regenerated from their separate verified
  raw files; no manual performance numbers or relabeling of the measured revision.
- [x] LaTeX/BibTeX build succeeds; citations/references resolved.
- [x] Every final PDF page visually inspected at readable size; output hash and
  page-specific findings in `qualification/PDF_REVIEW.md`.
- [ ] Release source package rebuilt on the eventual target service's toolchain.
  No unverified statement that it already compiles on arXiv.

## Decisions requiring the real author(s)

- [ ] Reconfirm the inherited author name and affiliation; obtain contribution and
  content consent from all actual authors. This maintenance adds no identity.
- [ ] Reconfirm acknowledgments, funding and competing-interest statements. They
  were inherited from the earlier draft and cannot be inferred anew.
- [ ] Approve accurate AI-assistance disclosure for code, experiments and writing.
- [ ] Confirm rights/provenance of every redistributed circuit and permission for
  relevant prior material; primary-source citation is not a redistribution license.
- [ ] Choose an artifact/manuscript license and target venue; validate its current
  preprint/anonymity rules immediately before a separately authorized submission.
- [ ] Confirm account eligibility/endorsement, final source package and submission
  schedule only when submission is actually authorized.

Current recommendation: retain a **research draft**, with qualified engineering
claims and explicit open gates. Never turn a prototype, green CI or short campaign
into an assertion that scientific release or stable-API promotion is approved.
