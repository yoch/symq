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
- `symq.phase` covers one narrow quantum fragment: X/CX/MCX, Z/CZ/MCZ (±1 phases), X-basis measure-and-reset (`hmr`) with Z-type feed-forward, and the clean-ancilla and outcome-independence obligations. See the [specification](docs/research/PHASE_HMR_SPEC.md). Other gates (H outside `hmr`, S, T, rotations, Z measurement) are rejected, and arbitrary quantum states are out of scope. Unsupported operations must never silently pass.
- Algorithms here prioritize correctness and inspectability, **not** claims of speed against native optimized libraries.

## Research provenance

The initial research handoff is the `anf_corpus_optimization_2026-10-27` archive (27 Oct 2026), which reports 11 public MQT QCEC circuits, 44 controlled cases and a pathological-case acceleration near 99× using an adaptive ZDD selector. These are **historical, externally produced measurements**, not reproduced or independently certified by the present package. The claimed speedup is not typical and does not establish superiority over CUDD, PolyBoRi or MQT QCEC. See [research notes](docs/research/ROADMAP.md) and [import status](docs/research/IMPORT_STATUS.md).

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

Architecture and contribution rules: [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md). This project is independent of [qant](https://github.com/yoch/qant). No automatic writes or imports from qant.

**Status:** experimental / pre-release. No PyPI publication or stable API guarantee.
