# Paper A: exact equivalence checking of reversible circuits with a native monomial ZDD

Draft manuscript and its evidence. **Status: draft for author review; not submitted.** No
author is listed yet, and every public step (arXiv, release, DOI) needs the authors' approval.

| file | content |
|---|---|
| `main.tex`, `main.pdf` | manuscript (pdfLaTeX + BibTeX) and its last compiled PDF |
| `references.bib` | bibliography; every entry checked against its primary source |
| `blind_text.tex` | prose about the blind corpus, written from generated macros only; prints a red PENDING marker until the blind run is sealed |
| `tables/`, `figures/` | **generated** by `tools/make_tables.py`; do not edit |
| `CLAIMS.md` | thesis, claims C1–C5 with prior art, evidence and refuting experiments; contribution statement |
| `RELATED_WORK.md` | verified related work and positioning |
| `FORMAL_MODEL.md` | semantics, propositions and proofs on paper, and what is only tested |
| `EXPERIMENTS.md` | E1–E5: protocol, runs, results, pending items |
| `REPRODUCIBILITY.md` | commands, pinned versions, errata of the run records |
| `SUBMISSION_CHECKLIST.md` | arXiv rules, calendar, venue preprint policies, open decisions |
| `tools/make_tables.py` | sealed results → tables, figure, `tables/numbers.tex` |
| `tools/make_arxiv.sh` | builds the arXiv source package in `arxiv/` (not committed) |

Build:

```bash
python paper/tools/make_tables.py
cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

The phase/HMR line of work (`src/symq/phase.py`) is deliberately **not** part of this paper.
