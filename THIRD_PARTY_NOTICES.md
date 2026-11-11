# Third-party notices

SymQ's own source code, tests, tools and documentation are distributed under the
[MIT license](LICENSE). The repository and the source distribution (sdist) also redistribute a small
amount of third-party material, used only as test and benchmark inputs. Each item keeps its own
license, which is reproduced next to it; the MIT license of SymQ does **not** relicense it.

The installed wheel ships `src/symq` only. It contains no third-party source file and none of the
material listed here.

This file is a summary. The file named in the *Provenance record* column is authoritative for each
item: it carries the upstream revision, hashes and the statement of what was changed.

## Redistributed material

| Location | Upstream and copyright | License | Provenance record |
| --- | --- | --- | --- |
| `benchmarks/corpus/qcec/*.qasm` (20 circuits) | [MQT QCEC](https://github.com/munich-quantum-toolkit/qcec) `test/circuits/original`, commit `98d6784176bfeb6ef923d4d0220e8d486dc1982f`. Copyright (c) 2023 - 2025 Chair for Design Automation, TUM; Copyright (c) 2025 Munich Quantum Software Company GmbH. Unmodified copies; upstream derives them from RevLib benchmark realizations | MIT ([text](benchmarks/corpus/qcec/LICENSE_QCEC.txt)) | [README](benchmarks/corpus/qcec/README.md), [manifest](benchmarks/corpus/qcec/MANIFEST.json) |
| `benchmarks/corpus/kickmix/*.kmx` (6 circuits) | [Qualtran](https://github.com/quantumlib/Qualtran) `kickmix/testdata/`, commit `638777fac4379bc62e2a1e4a52cf1a1753895d48`. Byte-for-byte copies | Apache-2.0 ([text](benchmarks/corpus/kickmix/LICENSE-APACHE-2.0)) | [README](benchmarks/corpus/kickmix/README.md), [manifest](benchmarks/corpus/kickmix/MANIFEST.json) |
| `benchmarks/corpus/qualtran/` (two fixtures and the rewrite requests derived from them) | Generated from the Qualtran bloqs `GF2Multiplication` and `GF2MulMBUC` at the same commit. Copyright 2024 Google LLC. Changed by SymQ: normalization, terminal zero-wire embedding, provenance and contract envelope | Apache-2.0 ([text](benchmarks/corpus/qualtran/LICENSE-APACHE-2.0)) | [README](benchmarks/corpus/qualtran/README.md), [rewrite manifest](benchmarks/corpus/qualtran/rewrite/MANIFEST.json) |
| `benchmarks/corpus/bilinear_kmb/` (`manifest.json` and 14 circuits packed in `starts.zlib.b64`, and the rewrite request derived from one of them) | Kaggle dataset [VQCC bilinear KMB agent evaluation](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation). Copyright 2026 James Barlow. Circuit bytes unaltered; the pack is a lossless transport wrapper | Apache-2.0 as declared by the dataset page's license field, checked on 1 November 2026 ([text](benchmarks/corpus/bilinear_kmb/LICENSE_APACHE_2_0.txt)) | [SOURCE](benchmarks/corpus/bilinear_kmb/SOURCE.md), [NOTICE](benchmarks/corpus/bilinear_kmb/NOTICE.txt), [manifest](benchmarks/corpus/bilinear_kmb/manifest.json) |
| QASM text embedded in `tests/test_public_compiler_rewrite.py` (`ab+ac.qasm`) | [DVLab-NTU/qsyn](https://github.com/DVLab-NTU/qsyn) `benchmark/qasm/ab+ac.qasm`, commit `b77187c87f0bddd69bc6c213700642ee6c423159`. Copyright 2023 Design Verification Laboratary, National Taiwan University (upstream spelling). The optimized variants in that test are SymQ changes | Apache-2.0 ([text](benchmarks/corpus/qsyn/LICENSE-APACHE-2.0)) | [NOTICE](benchmarks/corpus/qsyn/NOTICE.txt) |
| Adder generator reproduced and adapted in `tests/test_public_compiler_rewrite.py` | [Veri-Q/Benchmark](https://github.com/Veri-Q/Benchmark) `scripts/combinational/adder.py`, commit `9be108313844e30c5df5780989a68cac4d966cfe`. Copyright (c) 2026 Veri-Q | MIT ([text](benchmarks/corpus/veriq/LICENSE-MIT)) | [NOTICE](benchmarks/corpus/veriq/NOTICE.txt) |
| `tests/fixtures/kmb_v2_*.hex` (two binary examples) | Qualtran `docs/kickmix/kickmix_binary_format.md`, commit `9a0c11a4ee7697c082fbf8f2e1e8bf4a71fcb453`, blob `debcf51c10d4840fc268f5452686976e96699c40`. Google LLC / Qualtran Developers | Apache-2.0 (same text as [the kickmix corpus license](benchmarks/corpus/kickmix/LICENSE-APACHE-2.0)) | Comment header of each file |

## Credited methods, no code included

- The GF(4)-tower interpolation behind `symq.generators.gf2n.tower_multiplier` follows the method
  described by [Polytof](https://github.com/ZIB-IOL/polytof) (MIT, commit
  `0dcac107d15adc34dc646242d222f21ae7d32699`). No Polytof source file is included.

## Optional software that SymQ can call but does not redistribute

PySAT, NumPy, `dd` (CUDD), PolyBoRi (through passagemath), MQT QCEC and Lean 4 are optional
dependencies or development tools installed separately under their own licenses. None of them is
bundled.

## Limits of this summary

Recording an upstream license is not a legal review. The hashes kept in the manifests detect a
changed file; they do not establish permission to redistribute. In particular, the license of the
`bilinear_kmb` dataset rests on the dataset page's declared license field alone, as its
[provenance file](benchmarks/corpus/bilinear_kmb/SOURCE.md) states.
