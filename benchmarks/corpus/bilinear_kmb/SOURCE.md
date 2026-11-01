# Public bilinear KMB corpus — provenance

## Source and licence

- **Dataset:** [VQCC bilinear KMB agent evaluation](https://www.kaggle.com/datasets/manwithacat/vqcc-bilinear-agent-evaluation)
  (`manwithacat/vqcc-bilinear-agent-evaluation`), copyright 2026 James Barlow.
- **Licence:** Apache 2.0. The dataset page's licence field reads "Apache 2.0" (checked on
  1 November 2026, dataset version 3, last updated 2026-10-31T23:15Z). The full licence text is
  in [LICENSE_APACHE_2_0.txt](LICENSE_APACHE_2_0.txt) and the attribution in [NOTICE.txt](NOTICE.txt).
  It covers the redistributed manifest and circuit files only, not SymQ.
- **Files redistributed unchanged:** [manifest.json](manifest.json) (SHA-256
  `2f48cb3f16f3f6466b394eaa6524d92a19b171a2e25605fd01257ae763f35c85`) and the 14 circuit files
  `gf16-01..07.kmb` and `gf64-01..07.kmb`, packed losslessly in [starts.zlib.b64](starts.zlib.b64)
  (zlib payload SHA-256 `8adef29e5e875723e14969cd62114156dcdc4dd3332ee4dc6db7ea6a821694ad`). The
  pack is a transport wrapper: each entry is a little-endian 16-bit name length, the ASCII file
  name, a 32-bit byte length and the original bytes. `benchmarks.bilinear_kmb.source_starts()`
  checks every file's SHA-256 against the manifest.
- **Not redistributed:** the dataset's own scripts (`evaluate.py` and others). No code from the
  dataset is used; the reader in `benchmarks/kmb.py` was written from the files themselves.

## What the circuits compute

Each file is a reversible multiplier on three `n`-qubit registers `(a, b, t)`, all of which may be
dirty, computing `(a, b, t) -> (a, b, t XOR a*b mod P)` with `P = 0x13` (x^4 + x + 1) for GF(16)
and `P = 0x49` (x^6 + x^3 + 1) for GF(64). Note that `0x49` is not SymQ's default GF(64) modulus
`0x43`. The files use only CX and CCX.

## How SymQ uses them

`python -m benchmarks.bilinear_kmb` proves each file equal, on every input, to SymQ's tower
multiplier in the same basis (`symq.generators.gf2n.tower_multiplier`: 9 Toffolis for GF(16), 15
for GF(64)), with the exact packed degree-two engine. The proof compares the two circuits directly.
Over the 14 files the Toffoli count goes from 240 to 168 and the CNOT count from 1862 to 784.

The 9- and 15-product targets are published in the dataset, and the tower construction follows
the GF(4)-tower interpolation described by [Polytof](https://github.com/ZIB-IOL/polytof) (MIT,
commit `0dcac107d15adc34dc646242d222f21ae7d32699`); no Polytof code is included. The corpus was
explored during development: these results are a constructive baseline on a public set with
known optima, not a holdout and not a competition score.
