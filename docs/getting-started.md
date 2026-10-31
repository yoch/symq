# Getting started

## Install

SymQ needs Python 3.10 or newer. Install it from a source checkout:

```bash
git clone https://github.com/yoch/symq.git
cd symq
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Optional extras are deliberately separate:

| Installation | Adds |
| --- | --- |
| `python -m pip install -e ".[sat]"` | PySAT for the [SAT decision engine](guide/sat.md) |
| `python -m pip install -e ".[dev]"` | Tests, Ruff and the SAT engine |
| `python -m pip install -e ".[dev,external]"` | Optional PolyBoRi, CUDD and MQT QCEC comparison adapters |

## The optional native core

`zdd-native` and `zdd-native-wide` are backed by a C extension that is compiled during
installation when a C compiler and the Python headers are available. Without them the
installation still succeeds and every pure-Python backend works.

| Environment variable | Effect |
| --- | --- |
| `SYMQ_SKIP_NATIVE=1` | never build the native core |
| `SYMQ_REQUIRE_NATIVE=1` | fail the installation if the native core cannot be built |

Setting both is an error; the mandatory flag takes precedence over the build script's
`--optional` flag. To diagnose a build from a checkout:

```bash
python tools/build_native.py --diagnose
python tools/build_native.py --require
```

## Check the installation

```bash
python -m symq doctor
```

`doctor` reports the interpreter, the native core, the registered backends and the optional
external baselines. It exits with code 0 in pure-Python mode and prints why the native core could
not be loaded (not compiled, or compiled for another ABI version). Use
`python -m symq doctor --require-native` to make a missing native core an error, for example in CI.

## A first verification

```python
from symq import Budget, Circuit, check_equivalence

reference = Circuit(3)
candidate = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
assert check_equivalence(reference, candidate, budget=Budget(max_seconds=5)).equivalent

mutant = Circuit(3).ccx(0, 1, 2)
result = check_equivalence(reference, mutant)
assert not result.equivalent
assert reference.run(result.witness) != mutant.run(result.witness)
```

Wire indices start at zero, controls precede the target, and integer inputs are LSB-first. Next:
[choose a backend](guide/backends.md), [decide with SAT contracts](guide/sat.md), or read the
[glossary](glossary.md).

## Running the tests

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

Tests that need the native core or the SAT solver carry the `native` or `sat` marker and are
skipped with the precise reason when the capability is missing. Set
`SYMQ_TEST_REQUIRE=native,sat` to turn those skips into errors, as CI does.
