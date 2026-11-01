# VQCC bilinear KMB agent evaluation — source and qualification

## Attribution and license (source bytes)

- **Original author / copyright:** Copyright 2026 James Barlow.
- **Source:** [VQCC bilinear KMB agent evaluation, Kaggle](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation), owner `manwithacat`.
- **Declared license:** **Apache-2.0**, in the author's dataset `README.md` (full license text: [LICENSE_APACHE_2_0.txt](LICENSE_APACHE_2_0.txt)). This license is **for the original KMB fixtures and original manifest**, not a relicensing of all of SymQ.
- **Original upload:** `archive (4).zip`, supplied by the project user on 2026-11-01. The Kaggle revision number and live page metadata were **not accessible independently**; the attribution and Apache-2.0 license above come from the original archive's `README.md`. Do not invent a Kaggle version number.
- **Uploaded archive SHA-256:** `635f4e9117c012adcf4038e29403373fe2aaf3ef2782e89e796ce1ac96e821dc` (not vendored as a ZIP).
- **Original manifest:** [manifest.json](manifest.json) copied **byte-identically**, SHA-256 `2f48cb3f16f3f6466b394eaa6524d92a19b171a2e25605fd01257ae763f35c85`.
- **Source circuit bytes:** all 14 original `gf16-*.kmb` and `gf64-*.kmb` are packed losslessly in [starts.zlib.b64](starts.zlib.b64); the zlib-compressed payload SHA-256 is `8adef29e5e875723e14969cd62114156dcdc4dd3332ee4dc6db7ea6a821694ad`. `source_starts()` checks every decoded KMB SHA-256 against the original manifest, rejecting any mismatch. The payload is a transport wrapper, **not** transformed circuit data. To avoid path ambiguity, decoded files are addressed by their original basename and source SHA.
- **No code from the original `evaluate.py`, `bilinear_cert.py`, `bilinear_synth.py` or `workbench.py` is vendored.** They can be retrieved from the cited Kaggle dataset. The independent decoder, encoder and algebraic oracles under `benchmarks/kaggle_bilinear*` are authored for SymQ.

## Exact mathematical model

For each `manifest.json` row, the source and candidate are KMB v2 reversible circuits with three `n`-bit registers `(a,b,t)` in that order; every register may be dirty. The accepted transformation is

```text
(a, b, t) -> (a, b, t XOR (a * b mod P))
```

The field polynomial is pinned to **`0x13 = x^4+x+1` for GF(16)** and **`0x49 = x^6+x^3+1` for GF(64)**. In particular, **`0x49 != 0x43`** (the previously used SymQ GF64 field representation). No extra qubits, classical operations, measures, resets or phases occur. The original benchmark's cost is *physical CCX count* under a restricted bilinear model. This is **not** the Kaggle Google Verifiable Quantum Circuit Compilation competition score and does not model DQI/chemistry.

## Candidate method — separate mathematical provenance

The **new candidates** are generated from a **new independent implementation** of GF(4)-tower bilinear interpolation in [kaggle_bilinear_towers.py](../../kaggle_bilinear_towers.py), followed by dirty-target CNOT conjugation in [kaggle_bilinear_kmb.py](../../kaggle_bilinear_kmb.py). The underlying mathematical method is discussed in [Polytof, ZIB-IOL/polytof](https://github.com/ZIB-IOL/polytof), MIT license, pinned commit **`0dcac107d15adc34dc646242d222f21ae7d32699`**, `scripts/make_cpd_gf.py` (especially `scheme_n6`); the 9/15 bilinear targets are also declared in the original Kaggle dataset and discussed in [Ballet et al., finite-field multiplication](https://arxiv.org/abs/1906.07456). This code is not copied from Polytof and does not claim an independent proof of the *lower bounds*. An explicit isomorphism converts tower arithmetic into each dataset's original polynomial basis before emitting any circuit. The GF(16) tower uses GF(4)[z]/(z²+z+omega); GF(64) uses GF(4)[z]/(z³+z+1).

Each rank-one bilinear term is emitted using **exactly one Toffoli and no ancilla** by selecting one existing dirty output bit as temporary pivot. Input parity folds and target fanout are uncomputed; the result is the exact permutation on all input basis states and thus extends to coherent superpositions for these reversible, phase-free gates. It **does not** establish contextual cut-preconditions, relative-phase/measurement behavior or official quantum resource advantage.

## Verified evidence on the uploaded 2026-11-01 archive

| Family | Source circuits | Original CCX | Candidate CCX | Candidate CX | Exact-target hits |
|---|---:|---:|---:|---:|---:|
| GF(16), mod `0x13` | 7 | 85 | 9 per circuit | 62 per circuit | 7/7 |
| GF(64), mod `0x49` | 7 | 155 | 15 per circuit | 174 per circuit | 7/7 |
| **Total** | **14** | **240** | **168** | – | **14/14** |

All 14 candidate KMB files passed the **author's original `evaluate.py` on the exact supplied source manifest** (14/14 `valid`, 14/14 `improved`, 14/14 target reached). Two independently decoded candidates were also checked against direct integer polynomial multiplication on *all* `2^12 = 4096` GF16 and `2^18 = 262144` GF64 complete basis inputs (including every dirty target value). The two algebraic factor lists passed exact multiplication-tensor checks on all n² coefficient pairs; dropped-term and altered-output mutants are rejected. The target counts are public, so this is a **known-optimum constructive baseline, not an agent discovering unseen optimizations**.

The original README describes five deliberately wasteful starts and two independently produced schoolbook multipliers **per field**. All 14 are public *open-set* diagnostics; no previously untouched or sealed holdout exists here. Do not pool these results with the 28-case substitution qualification matrix or claim new compiler generalization. For a blind agent evaluation, freeze the optimizer first and supply a fresh independently synthesized, unopened corpus with disjoint generation recipes.

## Reproduce

```bash
python -m pytest -q tests/test_kaggle_bilinear.py
python -m benchmarks.kaggle_bilinear_eval \
  --output /tmp/kaggle-bilinear.json \
  --candidate-dir /tmp/kaggle-bilinear-candidates
```

The runner validates the byte hashes for all source files, the original and candidate gate counts, and the exact semantics for every operand pair and two dirty-target values. The tests additionally check **all** full-register assignments for both candidates. A JSON report and `.sha256` sidecar are written on every completed campaign; the CI job archives them and the candidate KMB outputs. The optional *external* cross-check with the author's exact `evaluate.py` is reproduced by installing/downloading the source dataset from its Kaggle page alongside a candidate and running `python evaluate.py --id gf64-01 --candidate /tmp/kaggle-bilinear-candidates/gf64-01.kmb`.

The 14-source evaluation is a correctness/regression test of existing public data. **It is not a repeated timed comparative benchmark**; there is no claim of confidence intervals, application-wide speedup or a Kaggle leaderboard improvement.
