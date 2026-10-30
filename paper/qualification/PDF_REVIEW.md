# Final draft PDF inspection — 30 October 2026

- File: `paper/main.pdf`, 10 A4 pages, 394,324 bytes.
- SHA-256: `afb871b2da7a439f92e532a1e777f1c33e2da6e8b2a6af1edfd7458594305f3f`.
- Measured source: `49f5c438fe8916d2d2abf0a1dd137c33fd752184`.
- Raw JSON SHA-256: `20810d3735be03677f5245f695dd01683d483b6be8b0494ec6d42615a2d95573`.
- Gzip artifact SHA-256: `797e79198d67d5a6af5fa66b822d1e6936281765bf5916488763f302b6f298c2`.
- Case-adjudication SHA-256: `2604175d75a3100d420cce3826a6ffdaa850ffa1593d017db27c37a8d9e2b242`.

Built with `latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex`,
pdfTeX 1.40.26 / TeX Live 2025 Debian and BibTeX 0.99d. The final log contains no
undefined citations/references, multiply defined labels or overfull boxes. One
underfull box concerns justified text in the service table; it remains readable.

Every page was rendered separately with `pdftoppm -r 120 -png` and inspected as
a 993×1404 image. After the final denominator-label correction, pages 1–5 and
8–10 were byte-identical PNGs to their individually inspected predecessors;
changed pages 6–7 were rendered and individually inspected again. This binds the
review to the final PDF above rather than an earlier draft.

| Page | Visual finding |
| --- | --- |
| 1 | Title, inherited author metadata, bounded abstract counts and prior-art framing fit; no clipping. |
| 2 | Ring model, induction, minimum-degree witness and corrected product identity are legible; equations fit. |
| 3 | Services table and source/budget/preparation boundaries fit. The benign justified table-cell spacing does not hide text. |
| 4 | Measurement policy, status/evidence counts and absolute-cost/family qualifications are readable. |
| 5 | Full coverage and adverse decision/witness tables retain all rows and legends; no overlap. |
| 6 | Adjudication, per-family ratios, secondary native mode and holdout sensitivity fit. `common/planned`, 5/8 attempted and 4/6 attempted are explicit. |
| 7 | Four coverage panels, axes and complete status legend are legible. Conditional ratios retain their planned-case denominators. |
| 8 | ANF cost/RSS plot and legend fit; historical limitations and experimental HMR boundary remain readable. |
| 9 | Complete source/native/raw/gzip/classification hashes fit; disclosure and references 1–11 are readable. |
| 10 | References 12–24, including Irene/QuPRS/hybrid sources and software attributions, fit without clipping. |

The independent paper script reproduces all 27 preregistered primary comparisons
from raw rows (case counts, paired counts, family ratios and equal-family means;
relative tolerance `1e-12`), without importing the benchmark summary algorithm.
The raw artifact still has 4,320 planned rows, 2,700 attempted trials and 1,620
unrun rows. Its 1,560 successful services include 1,395 exhaustive-oracle flags
and 405 replay flags; the raw 1,440 oracle flags also include 45 unsupported QCEC
witness requests and must not be called successful services.

This is an AI-assisted visual and evidence-accounting review, not author
approval, scientific acceptance, a machine proof or permission to submit. The
remaining publication and broader-corpus gates in `SUBMISSION_CHECKLIST.md`
remain open. Exact published-HEAD CI belongs to the PR checks after publication.
