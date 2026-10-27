# Submission checklist (arXiv, then a venue)

Nothing has been submitted, deposited, released or announced. Every step below that is
public needs the explicit approval of the authors. Rules were read on the official pages
on 27 Oct 2026; URLs are given so they can be re-checked on the day of submission.

## Blocking decisions for the authors

- [ ] **Authors, affiliations, contact.** None is listed in the draft; none may be invented.
      Every author must agree to the content and to the licence (arXiv: by signing, each
      author "individually take[s] full responsibility for all its contents").
- [ ] **Co-author consent and prior material.** Confirm that no private material from earlier
      work is included (the paper uses only this public repository, the MIT-licensed QCEC test
      circuits, and generated circuits) and that every contributor agrees.
- [ ] **AI disclosure.** arXiv requires reporting "significant use of sophisticated tools",
      explicitly including text-to-text generative AI, and forbids listing an AI as author
      (https://info.arxiv.org/help/moderation/index.html). The draft has a TODO in the
      acknowledgements; code, experiments and drafting were AI-assisted.
- [ ] **Licence** (irrevocable per version; https://info.arxiv.org/help/license/index.html):
      CC BY 4.0, CC BY-SA 4.0, CC BY-NC-SA 4.0, CC BY-NC-ND 4.0, arXiv non-exclusive licence
      1.0, or CC0. CC BY-NC is not offered. Check the target venue's copyright policy first
      (CC0 conflicts with many publishers).
- [ ] **Endorsement.** Required for a first submission to a category. Since 21 Jan 2026 an
      institutional e-mail alone no longer qualifies; automatic endorsement needs a claimed
      co-authored paper *and* an institutional address; otherwise ask an established author
      in the category (https://info.arxiv.org/help/endorsement.html,
      https://blog.arxiv.org/2026/01/21/attention-authors-updated-endorsement-policy/).
- [ ] **Rate limit.** Two new submissions per author per calendar month, three active
      (since 1 Oct 2026; rejected submissions count).
- [ ] **Scientific readiness.** The blind-corpus run must be sealed and its paragraph
      written (`paper/blind_text.tex`) — no red PENDING marker may remain; independent review
      findings closed (see the PR).

## Category (our assessment, not an arXiv statement)

- Primary **cs.LO** ("program verification", ACM D.2.4/F.3.1): the paper is about exact
  equivalence checking.
- Cross-list at most one or two ("It is rarely appropriate to add more than one or two
  cross-lists", https://info.arxiv.org/help/cross.html): **cs.SC** (GF(2) polynomial
  manipulation) and/or **quant-ph** (reversible circuits from quantum design automation;
  precedents: Amy 2018 quant-ph+cs.LO, Burgholzer & Wille quant-ph+cs.ET).
- Moderators may reclassify.

## Calendar (times converted to Israel, UTC+2)

| event | official time | Israel time |
|---|---|---|
| next arXiv deadline | Tue 27 Oct 2026, 14:00 EDT (18:00 UTC) | **Tue 27 Oct, 20:00** |
| scheduled maintenance: login, submission and endorsement unavailable | Wed 28 Oct, 07:00–12:00 EDT (11:00–16:00 UTC) | Wed 28 Oct, 13:00–18:00 |
| announcement of everything received Tue 14:00 EDT – Thu 14:00 EDT (no Wednesday announcement) | Thu 29 Oct, 20:00 EDT | Fri 30 Oct, 02:00 |
| following deadline | Thu 29 Oct, 14:00 EDT | Thu 29 Oct, 20:00 |

Sources: https://arxiv.org/localtime, https://info.arxiv.org/help/availability.html,
https://status.arxiv.org/, https://blog.arxiv.org/2026/10/21/scheduled-database-maintenance/.
Recommendation: do **not** aim at tonight's deadline. Endorsement, authorship, AI disclosure
and the blind results are open; a submission received before Thursday 14:00 EDT is announced
at the same time anyway.

Versioning: once announced, a paper cannot be removed; every replacement is a new public
version, and earlier versions stay available (https://info.arxiv.org/help/withdraw.html,
https://info.arxiv.org/help/replace.html).

## Venue constraints on preprints

| venue | deadline | review | preprint rule |
|---|---|---|---|
| DAC 2027 | abstract 11 Nov, manuscript 18 Nov 2026 (6+1 pp) | double-blind | arXiv allowed, keep anonymity "reasonable efforts" |
| CAV 2027 | 20 Jan 2027 | regular double-blind; tool papers single-blind | avoid arXiv within 1 week before to 1 month after the deadline |
| TACAS 2027 | 15 Oct 2026 (passed) | — | — |
| DATE 2027 | 20 Sep 2026 (passed) | double-blind | preprint only after notification |
| RC 2027 | abstract 5 Feb, paper 12 Feb 2027 | not stated | not stated |
| ACM TOQC | rolling | single-blind | arXiv allowed (ACM policy) |

A double-blind submission needs an anonymised version (no repository URL, third-person
self-citations); the arXiv version must not be advertised to reviewers.

## TeX package for arXiv

`paper/tools/make_arxiv.sh` builds `paper/arxiv/symq-paper-arxiv.tar.gz` (not committed) with
`main.tex`, `main.bbl`, `blind_text.tex`, `tables/*.tex`, `figures/*.pdf`. Checked against
https://info.arxiv.org/help/submit_tex.html and https://info.arxiv.org/help/00README.html:

- [x] pdfLaTeX, figures in PDF only, no `\today` in `\date`, `hyperref` loaded by the
      document, file names in `[A-Za-z0-9_+-.,=]`, no hidden files.
- [x] `main.bbl` included and named after `main.tex` (BibTeX, `plain` style).
- [x] No `.aux`, `.log` or `.pdf` outputs in the package.
- [ ] Compiles on arXiv's TeX Live 2025 (tested locally with TeX Live 2023 only).
- [ ] Draft markers removed: red TODO/PENDING, "Draft ... not submitted" date line.

## Artifact

- [ ] Tag the exact commit and, if wanted, archive it (GitHub release, Zenodo DOI) — **only
      with author approval**; nothing has been created.
- [ ] Merge the experiment branch (results, harness) to `main` through its PR, or cite the
      branch commit explicitly. The overflow fix (PR #23) is not in the measured binary.
