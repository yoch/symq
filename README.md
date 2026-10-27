# symq

**Exact symbolic Boolean algebra for reversible-circuit research.**

[![CI](https://github.com/yoch/symq/actions/workflows/ci.yml/badge.svg)](https://github.com/yoch/symq/actions/workflows/ci.yml)

symq is an early-stage research library for exact algebraic normal forms (ANFs) over the Boolean ring GF(2)[x₀,…,xₙ₋₁]/(xᵢ²−xᵢ), together with reference evaluation of classical reversible circuits. It is **not** a general quantum simulator or universal quantum-equivalence checker.

## Quick start

```bash
python -m pip install -e ".[test]"
python -m pytest -q
```

```python
from symq import ANF, Circuit
x, y = ANF.variable(0), ANF.variable(1)
assert (x * (x ^ y)).evaluate(0b11) == 0
c = Circuit(3).x(0).cx(0, 1).ccx(0, 1, 2)
assert c.run(0) == 0b111
assert c.inverse().run(c.run(0)) == 0
```

Symbolic equivalence beyond exhaustive widths, on any registered backend:

```python
from symq import Budget, Circuit, check_equivalence
left = Circuit(40).mcx(*range(30), 39)
right = Circuit(40).mcx(*range(31), 39)
result = check_equivalence(left, right, backend="zdd", budget=Budget(max_seconds=10))
assert not result.equivalent and left.run(result.witness) != right.run(result.witness)
```

Backends (`reference`, `sparse-copy`, `sparse`, `zdd`, `auto-zdd`, `adaptive-wire`, `packed`, `packed-fallback`, `truthtable`) are described in [docs/research/BACKENDS.md](docs/research/BACKENDS.md).

## Scope and correctness

- ANF addition is symmetric difference; multiplication is idempotent monomial union with parity cancellation.
- Bit numbering is LSB-first; monomials are nonnegative integer masks.
- The reversible-circuit subset supports X, CX, CCX and MCX. Exact equivalence is available by exhaustive enumeration with an explicit input-width limit, or symbolically by canonical ANF comparison under an explicit `Budget`.
- `symq.phase` covers one narrow quantum fragment: X/CX/MCX, Z/CZ/MCZ (±1 phases), X-basis measure-and-reset (`hmr`) with Z-type feed-forward, and the clean-ancilla and outcome-independence obligations. See the [specification](docs/research/PHASE_HMR_SPEC.md). Other gates (H outside `hmr`, S, T, rotations, Z measurement) are rejected, and arbitrary quantum states are out of scope. Unsupported operations must never silently pass. The whole instruction list is re-validated at every entry point, so a hand-built `Op` cannot reach the semantics; invalid programs are rejected, never certified. The fragment has no `Algebra` backend, no resource budget and no external corpus yet, so it is not a trusted verifier for arbitrary imported programs ([audit](docs/research/AUDIT_2026-10-27.md)).
- Algorithms here prioritize correctness and inspectability, **not** claims of speed against native optimized libraries.

## Research provenance

The initial research handoff is the `anf_corpus_optimization_2026-10-27` archive (27 Oct 2026), which reports 11 public MQT QCEC circuits, 44 controlled cases and a pathological-case acceleration near 99× using an adaptive ZDD selector. These are **historical, externally produced measurements**. The archive is kept under [research/archive/2026-10-27](research/archive/2026-10-27/ARCHIVE_GUIDE.md), and symq's backends reproduce its engines' output polynomials exactly. The speedups reproduce in direction only, and with smaller magnitude ([findings](docs/research/BENCHMARK_FINDINGS.md)). The pathological speedup is not typical. Against native libraries, it is a representation effect, not a language one: with the optional C core (`zdd-native`) the same diagrams run 11× faster than the pure-Python `zdd` and 4.4× faster than PolyBoRi on this corpus, while CUDD and MQT QCEC remain faster on other axes ([native baselines](docs/research/EXTERNAL_BASELINES.md)). See [research notes](docs/research/ROADMAP.md) and [import status](docs/research/IMPORT_STATUS.md).

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

The native baselines (PolyBoRi, CUDD, MQT QCEC) are optional: `python -m pip install -e ".[dev,external]"` enables `symq.external` and its tests, which are skipped otherwise.

The ZDD backends also have an optional C core (`native` extra, built from `src/symq/backends/_zdd.c`). It is compiled in place when a C compiler and the Python headers are present; `SYMQ_SKIP_NATIVE=1` forces a pure-Python install, where `zdd-native` is simply not registered and everything else works unchanged.

Architecture and contribution rules: [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md). symq is self-contained: it has no dependency on, and no reference to, any other project's private repository.

**Status:** experimental / pre-release. No PyPI publication or stable API guarantee.
