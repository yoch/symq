# Public HMR qualification data

Measured source is the public protocol commit `b69babec7f0e6456f8358c48b6142788d29ef793`, tree
`d6c7bb6f2e302f8cf9f90dbdafb79b655a1b7a5d`. This directory contains a controlled
ABI-5 build receipt, all 270 fresh-worker records, the exact semantic matrix and
a completion receipt. `SHA256SUMS` seals these files. No scientific data from
the earlier 210-worker synthetic campaign was modified.

This uses previously explored public Qualtran m=1/m=2 fixtures, one family, not
a new blind holdout. Python/native full-call timings are near parity. The
results support the stated tiny-instance semantics and resource-bounded
reproduction, not general native superiority or stable API promotion.

Reproduce at the measured source commit:

```sh
git checkout b69babec7f0e6456f8358c48b6142788d29ef793
python -m venv /tmp/hmr-reproduction
/tmp/hmr-reproduction/bin/pip install -e '.[dev,native]'
PYTHONPATH=src /tmp/hmr-reproduction/bin/python benchmarks/hmr_qualification.py --build-native --out /tmp/hmr-build.json
taskset -c 4 env PYTHONPATH=src /tmp/hmr-reproduction/bin/python benchmarks/hmr_qualification.py --build-receipt /tmp/hmr-build.json --out /tmp/hmr-results.json
```

CPU 4 was available on this host. On another host select an allowed CPU and
retain the resulting recorded affinity; different hardware/toolchains need not
reproduce identical timings or a byte-identical native binary.
