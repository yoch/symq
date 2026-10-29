# Current native compatibility and historical measurements

PR 26 originally used ABI 4. Its historical source, binaries and sealed results
remain identifiable in Git history and all existing result directories remain
byte-for-byte unchanged. Integrating main at
`332de59677bd5e21a125c5d6f6f5f43264b4b734` supplies ABI 5 and the currently
qualified native algorithms; these are not new timings of the old binary.

The current harness requires ABI 5. It accepts only the exact native result
`(list[int] roots, int | None peak_terms, int products)`, validates width and
nonnegative counters, updates gates/products/peak statistics, and rejects legacy
flat results and incompatible backend/driver combinations. Root IDs remain
manager-local. Counterexamples are replayed concretely within the measured
verification boundary. The smoke oracle uses independent dense truth tables.

`tools/build_native.py` writes an ignored `.so.build.json` receipt after a
successful compile. It binds source and binary SHA-256, compiler version, flags
and Python ABI. A source change during compilation discards the build.
`benchmarks/native_contract.py` rejects a missing/mismatched receipt, incompatible
ABI or an extension imported from another checkout. This is a reproducibility
check, not a cryptographic proof of compilation or mathematical correctness.
Do not rebuild a binary while a worker has it loaded.

Rebuild and test before a campaign:

```sh
python -m pip install -e '.[dev,native,external]'
python tools/build_native.py --require
python -m pytest -q tests/test_harness_smoke.py tests/test_build_native.py
```

All declared matched modes/workloads are smoke-tested, including optional
PolyBoRi, dynamic/static CUDD and QCEC when installed. Missing optional engines
are explicit skips in unit tests; campaign cells must record their refusal.
Pure-Python CI runs the sparse/Python ZDD paths and skips only native cells.
Native node/time limits apply during graph computation; `max_terms` bounds
explicit ANF materialization, not the number represented by a compact graph.

The legacy `matched.one_run` receives precompiled gate arrays. Its old
`end_to_end` key is retained for historical report consumers and is also named
`precompiled_core`; it excludes gate-array compilation. QCEC's old similarly
named field includes conversion and is a different boundary. Neither field
should be used for new cross-tool public-call claims. The successor versioned
qualification protocol separates conversion, computation, comparison, witness,
replay and export, and reports complete public calls separately.

The old blind corpus is explored development evidence. Its sealed results are
not an untouched holdout for a new campaign. Historical binding subtraction
remains a sensitivity analysis, not a demonstrated performance bound.
