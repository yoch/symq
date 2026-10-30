# Reproducing current qualification and historical evidence


## Current revision (30 October 2026)

The revised manuscript separates short current qualification from the October 27
exploration. No historical row is rewritten, relabeled current or substituted into
a new run. The previously explored corpus is not a new holdout.

```bash
# From the reconciled paper branch, with matplotlib installed:
MPLCONFIGDIR=/tmp/symq-paper-mpl python paper/tools/make_tables.py
MPLCONFIGDIR=/tmp/symq-paper-mpl python paper/tools/make_qualification.py \
  --results benchmarks/qualification/classical-20261030/results.json.gz \
  --classification benchmarks/qualification/classical-20261030/case-classification.json
(cd paper && latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex)
```

The first command verifies sealed historical data and labels old tables historical.
The second reads the new artifact, rejects malformed evidence, and independently
recomputes status denominators, common-completion paired effects, equal-family
aggregation, descriptive family resampling and leave-one-family-out sensitivity.
It writes `paper/qualification/derived.json`, TeX and two figures. The artifact's
source commit, loaded binary, manifest and raw-file hashes remain visible; later
paper commits do not become the measured code revision. A generator output is not
an independent implementation certificate.

The committed gzip file preserves the complete original JSON on decompression.
Both the transport artifact SHA-256 and decompressed raw SHA-256 appear in derived
evidence and the PDF; no failure row is removed to reduce publication size.

The separately hashed classification sidecar records the code-inspection finding
that increment does not consume its seed and was already exercised in development.
It must match the measured source, manifest and every planned/recorded case; raw
split labels are checked rather than rewritten. The originally declared
three-small-family aggregate is retained as a descriptive mixed study. A clearly
labeled post-audit holdout-only sensitivity excludes deterministic calibration;
only two small stochastic families then qualify for exhaustive-oracle timing
ratios. No case is replaced or rerun, and no population inference follows.
The independent derivation retains its historical `requested_cases` and
`family_requested_cases` JSON field names for compatibility: their meaning is
planned cases including `not_run`, not attempted cases. Rendered tables and prose
therefore label these denominators `common/planned`; actual attempted counts
remain separate (5/8 overall and 4/6 after calibration exclusion).

The worker explicitly loads actual public functions from the immutable source
snapshot (`snapshot/src` precedes other import locations). Dependencies come from
the recorded virtual environment. The measured boundary is therefore public API
from frozen source, not performance of an installed wheel. The frozen manifest's
older “installed” wording is retained as historical source, with this annotation;
wheel-installation CI supplies separate packaging evidence rather than a timing
result for this campaign.

Classical raw `cpu_seconds` is cumulative CPU from `resource.getrusage` sampled
just before JSON result encoding and process teardown. It is not a complete
reaped-worker CPU measurement; encoding/teardown CPU remains unmeasured, while
parent wall time extends through process reaping. `service_cpu_seconds` covers
input materialization and orchestration through the service checkpoint, a broader
window than public-call-only `service_seconds`; validation CPU is separate.
The separate HMR study measures reaped CPU by a different mechanism. These
boundaries must not be pooled or reconstructed from wall time.

Workers eagerly import all optional tools before their service-ready checkpoint,
using the same common prefix for every backend. Whole-worker RSS therefore
includes that prefix rather than measuring a selected solver's isolated heap.
Import/startup remain outside service time and inside the process envelope.
Parent resource polling is every 10 ms; termination/cleanup latency is disclosed,
and no late result is accepted as a completed proof.
Controlled service timeouts forcibly terminate workers. Zero rows classified
`killed` means no unexplained process kills, not zero SIGKILLs. The native
manager-node cap includes intermediates and nodes no longer reachable from final
roots; final DAG/ANF sizes and the benefit of collection or alternative orders on
these adverse cases are unmeasured.

Coverage uses a joint policy, not a pure CPU/RSS experiment or equal abstract-work
budget. The manifest's `max_terms=200000` and `max_nodes=1000000` have
representation-specific applicability: sparse ANF checks terms and an
input-product-size bound; PolyBoRi checks polynomial terms; Python/native ZDDs
limit retained manager nodes and guard term materialization; CUDD limits its
manager nodes and conversion-to-ANF terms. SAT/QCEC use applicable process and
timeout limits without those ANF/DD caps. All refusals stay in the raw data.

Current campaign reproduction must use the frozen protocol/source named in its
artifact and the declared worker envelope. The commands below describe historical
measurements and must not be run on current sources while claiming to reproduce
the old binary or blind condition. Timing is not byte-reproducible.

PDF validation requires a successful LaTeX/BibTeX build, no unresolved references
or table overflow, and visual inspection of **every page** of the final PDF. The
page-count/hash and inspection record are in `paper/qualification/PDF_REVIEW.md`.
Author/content/license approval and external release are separate open gates.

## Historical record retained from the original draft

The historical files in `paper/tables/`, `paper/figures/` and `paper/tables/numbers.tex` are generated
from sealed result directories by one script. The manuscript never contains a hand-copied
number; prose that interprets blind-corpus results lives in `paper/blind_text.tex` and uses
only generated macros.

## 1. Rebuild the PDF from the committed results (minutes)

```bash
python -m venv .venv && . .venv/bin/activate
python -m pip install -e ".[dev]" matplotlib      # matplotlib only for the figure
python paper/tools/make_tables.py                 # verifies SHA256SUMS, writes tables/figures/macros
cd paper && pdflatex main && bibtex main && pdflatex main && pdflatex main
```

`make_tables.py` refuses to run if any file of a sealed run differs from its `SHA256SUMS`.
The runs it reads are listed at the top of the script (`RUNS`, `ORDER_RUNS`, `BINDING_RUN`,
`FUSED_BLIND_RUNS`). Tested with
TeX Live 2023 (Ubuntu 24.04 packages), pdfTeX and BibTeX, Python 3.12.3, matplotlib 3.11.2.

## 2. Re-run the measurements (hours)

```bash
python -m pip install -e ".[dev,external]"        # passagemath-brial, dd, mqt.qcec
python tools/build_native.py                      # builds src/symq/backends/_zdd*.so in place
python -m pytest -q                               # 2 490 tests at the measured commit
python benchmarks/matched.py --corpus qcec  --pins 2 3 --label matched-qcec     # ≈ 10 min
python benchmarks/matched.py --corpus blind --pins 2 3 --label matched-blind    # ≈ 3 h
PYTHONPATH=src python benchmarks/binding_overhead.py --pin 2
PYTHONPATH=src python benchmarks/variable_order.py --corpus qcec  --pin 2
PYTHONPATH=src python benchmarks/variable_order.py --corpus blind --pin 2 --timeout 30
```

Then point the run names in `paper/tools/make_tables.py` at the new directories. Cells killed
by the operating system (return code −9) are recorded as such; re-run them alone with
`--circuits … --workloads … --modes …` and merge with
`python benchmarks/merge_runs.py --base <run> --label <label> --override <re-run>[@mode@workload] …`,
which writes a sealed derived directory and a `merge.json` listing every substitution.
The blind run of the paper was merged this way; its raw inputs are in
`benchmarks/results-raw/` (see the README there).

Exact versions of the sealed runs: CPython 3.12.3; passagemath-brial 10.8.13; dd 0.6.0
(CUDD 3.0.0); mqt.qcec 3.11.0 and mqt.core 3.11.0; GCC 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1),
`-O3 -std=c11 -fPIC -shared`; Linux 6.12, 4-vCPU Intel Xeon VM. The harness refuses to run on
a modified tree unless `--allow-dirty` is given, in which case it records the patch.

## 3. What is pinned, what is not

| item | pinned by |
|---|---|
| symq sources | commit in each `environment.json` (`2346982`, `9b62a75`, `33515a3`); `src/` identical to `main@234696e` in all three |
| native binary | SHA-256 `2e3f67910a34cfc0c12c855840ec83ff7459a3f10b12d5572f3ef3b18e203f30` in every run record |
| QCEC corpus | `benchmarks/corpus/qcec/MANIFEST.json` (SHA-256 per file; source commit `98d6784` of munich-quantum-toolkit/qcec, MIT, `LICENSE_QCEC.txt`) |
| blind corpus | `benchmarks/corpus/blind/MANIFEST.json`, regenerated byte for byte by `benchmarks/generate_blind.py` (seed `symq-blind-2026-10-27`), checked by `tests/test_blind_corpus.py` |
| results | `SHA256SUMS` in every sealed directory |
| timing | **not reproducible bit for bit**: one shared VM, no frequency control; expect the ratios, not the milliseconds, to reproduce |

The GCC build is not byte-reproducible (rebuilding from the same source in another checkout
gave a different SHA-256); the measured binary is identified by its hash, and E4 copied it
rather than rebuilding.

## 4. Known errata in the run records

- `compiler` in the R-QCEC and R-BLIND `environment.json` reads `Ubuntu clang version
  18.1.3`: it is the output of `cc --version` on the machine, not the compiler of the
  extension, which `tools/build_native.py` builds with `sysconfig.get_config_var("CC")`
  (`x86_64-linux-gnu-gcc`). The `.comment` section of the measured binary reads
  `GCC: (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0`. R-ORDER records that section directly.
- The first QCEC-corpus run (`20261027T150621Z_23469829a0dc_matched-qcec`, one worker on
  CPU 1, 15:06–15:14 UTC) and the blind run (two workers, CPUs 2 and 3, 15:06–17:50 UTC) ran
  concurrently; during the blind run, lighter jobs (test suite, variable-order runs, LaTeX)
  used CPUs 0 and 1. The paper uses the later QCEC-corpus run with the corrected harness
  (`33515a3`, CPUs 2 and 3, from 17:54 UTC), which ran with no other benchmark. Ratios are
  paired within a run, except the fused cells of the blind corpus, which come from separate
  corrected-harness runs (paired with the minimal loop of the same run for H2).
- The blind run recorded workers killed by the memory cgroup as `error` with an empty
  message (it did not record return codes). `merge_runs.py` re-labels such rows `killed`;
  any other error aborts the merge. Kernel records: `paper/evidence/oom_kills.md`.
- 16:51:19–16:51:29 UTC: a git operation in the working copy of the blind run replaced the
  source tree for ten seconds. The 14 cells started in that window and two neighbours were
  re-run (`benchmarks/results-raw/*rerun-merge*`).
- `cudd-bdd/loop` fingerprints of the blind run disagree with all other engines on three
  circuits: a defect of `CuddBDDAlgebra.to_anf` (memo keyed by node id without keeping the
  node alive), fixed on `main` by PR #38. Timings are unaffected (conversion is outside the
  timed phase).

## 5. Data and licences

- symq: MIT. QCEC test circuits: MIT, redistributed with their licence file.
- Blind corpus: generated by our script; no third-party data.
- No private fixture, secret path or personal data is included. Results contain only
  timings, counts and hashes.
