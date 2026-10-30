# Paper A — exact ANF inspection and reversible verification

Research revision for review, **not submitted and not publication-authorized**.
The author identity is inherited from the existing draft; final consent, disclosure
and licensing remain gates, not assumptions made by this maintenance.

The manuscript presents a specialized engineering contribution under explicit
classical contracts. It separates current short qualification, verdict-only
baselines, ANF export and historical exploration. `CLAIMS.md` records falsifiable
claims/nonclaims; `FORMAL_MODEL.md` contains the paper proofs and assumptions;
`RELATED_WORK.md` records primary-source scope and search limits.

Build from the reconciled branch:

```bash
MPLCONFIGDIR=/tmp/symq-paper-mpl python paper/tools/make_tables.py
MPLCONFIGDIR=/tmp/symq-paper-mpl python paper/tools/make_qualification.py \
  --results benchmarks/qualification/classical-20261030/results.json.gz \
  --classification benchmarks/qualification/classical-20261030/case-classification.json
(cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex)
```

`make_tables.py` verifies and labels historical October 27 tables/figures. It does
not make them current results. `make_qualification.py` reads only the new raw
artifact, independently derives its summaries and records its SHA-256. No result
is invented when an artifact or optional backend is missing: generation fails or
the original explicit raw status is shown. `main.pdf` is the latest built draft;
`qualification/PDF_REVIEW.md` records inspection of that exact PDF.

The gzip artifact decodes to the unmodified raw JSON bytes. The generated evidence
records both its published compressed hash and the decompressed raw-data hash;
compression does not relabel, filter or replace any trial.

The required case-classification sidecar is bound to the measured source, manifest
and complete case set. It corrects the interpretation of the deterministic
increment case without changing raw `new_holdout` labels. Original mixed-study
summaries remain intact; a separate post-audit holdout-only sensitivity excludes
calibration. Without a matching sidecar, current table generation fails.

Raw measurements and manifests remain under `benchmarks/`. `EXPERIMENTS.md` and the
historical section of `REPRODUCIBILITY.md` preserve the earlier protocol and
incidents. The original complete manuscript is recoverable at
`605e3f47e20eb05a34b732d535c3f3dab5c8247a` without overwriting its scientific history.
The phase/HMR engines are installed experimental work with separate theorems,
not a claim of this classical paper. No stable API guarantee changes here.

The independent public Qualtran qualification is reviewed separately in
[PR #115](https://github.com/yoch/symq/pull/115), data commit
`07f0324c3d9d1cc2df85ea776f22601ccab87679`, measured source
`b69babec7f0e6456f8358c48b6142788d29ef793`. Its tiny, previously explored
GF2MulMBUC fixtures do not make this classical corpus external, establish a
large-multiplier result, or justify stable-API promotion.
