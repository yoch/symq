# kickmix test circuits (Qualtran)

Six `.kmx` files copied byte for byte from `kickmix/testdata/` of
[Qualtran](https://github.com/quantumlib/Qualtran) at commit
`638777fac4379bc62e2a1e4a52cf1a1753895d48`, under the Apache License 2.0
(`LICENSE-APACHE-2.0`). `MANIFEST.json` records the upstream path and SHA-256 of each file;
`tests/test_kickmix.py` checks them.

| File | Use in SymQ |
| --- | --- |
| `inc3.kmx` | classical increment modulo 8 |
| `inc8.kmx` | 8-bit increment with HMR-based carry uncomputation; proved equal to the MCX increment |
| `cmul16_mod_21.kmx` | controlled modular permutation on 6 wires (pinned observed behaviour) |
| `iadd8_qc_2clean_6dirty.kmx`, `mul16_mod_21.kmx`, `qft_measurement.kmx` | refused: they use reset, classical bit arithmetic or arbitrary angles |

The large `big_circuit.kmx` and the binary `.kmb` files were not copied.
