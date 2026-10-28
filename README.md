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

### Native Quickstart (`zdd-native`)

Simulate reversible circuits using the fused C engine:

```python
from symq import Circuit, make_algebra, simulate

circuit = Circuit(4).x(0).cx(0, 1).mcx(0, 1, 2).mcx(0, 1, 2, 3)

# The native ZDD backend (optional C core; use "zdd" when it is not built)
algebra = make_algebra("zdd-native", width=circuit.width)
outputs = simulate(circuit, algebra)

print("Outputs:", [algebra.to_anf(v) for v in outputs])
print(f"Stats: {algebra.stats.gates} gates, peak {algebra.stats.peak_terms} terms in {algebra.stats.seconds*1000:.3f} ms")
```

Report the installed backends and whether the native core is loaded (exit status 1 if it is not):
```bash
python -m symq doctor
```

### Symbolic Equivalence

Symbolic equivalence beyond exhaustive widths, on any registered backend:

```python
from symq import Budget, Circuit, check_equivalence
left = Circuit(40).mcx(*range(30), 39)
right = Circuit(40).mcx(*range(31), 39)
result = check_equivalence(left, right, backend="zdd", budget=Budget(max_seconds=10))
assert not result.equivalent and left.run(result.witness) != right.run(result.witness)
```

The optional native ZDD collector reduces memory on certain long circuits. It is **opt-in**
and may slow down some workloads. Set it on the public equivalence checker, so the
first circuit's output roots remain pinned while the second circuit is evaluated:

```python
result = check_equivalence(
    left, right, backend="zdd-native", budget=Budget(max_nodes=1_000_000),
    backend_options={"collect_every": 400_000},
)
```

A collecting `NativeZDDAlgebra` also supports a **single standalone simulation**.
It must start with a pristine manager and cannot be used to simulate another
circuit after returning node identifiers: collection remaps plain integer IDs.
Reuse without pinning could silently compare stale handles. The checker above
uses an internally owned pair and preserves both sets of roots. The node budget
applies to the active manager after each rebuild, not cumulative historical allocations.

For circuits wider than the 64-wire native limit, `check_equivalence_by_blocks` splits the wires into the blocks that neither circuit couples and checks each block separately: `zdd-native` (or `zdd` when the core is not built) up to `max_block_width` wires, and the `fallback` backend (`zdd` by default) for wider blocks. The result's `backend` names every backend used.

Backends (`reference`, `sparse-copy`, `sparse`, `zdd`, `auto-zdd`, `adaptive-wire`, `packed`, `packed-fallback`, `truthtable`) are described in [docs/research/BACKENDS.md](docs/research/BACKENDS.md).

### Optional SAT decision engine (classical X/CX/CCX/MCX only)

SAT decides **functional** equivalence without exporting output ANFs. It is an optional
decision engine, **not** an `Algebra` backend and not a general quantum-equivalence checker.

```bash
python -m pip install -e ".[sat]"
```

```python
from symq import Budget, Circuit
from symq.sat import Contract, check_sat_equivalence

left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
right = Circuit(3)
contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))
result = check_sat_equivalence(left, right, contract, budget=Budget(max_seconds=10))
assert result.outcome == "equivalent"
```

Possible outcomes: `equivalent`, `different` (with a concretely checked witness) or
`inconclusive`. Invalid inputs and missing solver dependencies raise exceptions. Time
budgets are **cooperative**, not strict process-kill deadlines; SAT does not enforce
the symbolic `max_nodes`/`max_terms` limits.

The optional `symq.strategy.choose()` suggests a variable order and an engine; it
**does not dispatch** or change defaults. Its engine rule is experimental and has not
demonstrated a gain over always-SAT. See [the V2 integration notes](research/symq-v2/README.md).


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

The ZDD backends also have an optional C core (built from `src/symq/backends/_zdd.c`).
- **Explicit compilation & diagnosis:** run `python tools/build_native.py` to compile in place. Run `python tools/build_native.py --diagnose` to inspect the detected compiler candidates (`$CC`, Python's `sysconfig CC`, or system fallbacks `cc`, `gcc`, `clang`) and Python development headers.
- **Mandatory native mode:** set `SYMQ_REQUIRE_NATIVE=1` (or pass `--require` to `build_native.py`) to strictly require the native backend; installation or compilation fails with a clear diagnostic and non-zero exit code if a compiler or headers are missing.
- **Pure-Python opt-out:** `SYMQ_SKIP_NATIVE=1` skips native compilation entirely and installs only the pure-Python backends (where `zdd-native` is simply not registered and everything else works unchanged).

Architecture and contribution rules: [AGENTS.md](AGENTS.md), [CONTRIBUTING.md](CONTRIBUTING.md). symq is self-contained: it has no dependency on, and no reference to, any other project's private repository.

**Status:** experimental / pre-release. No PyPI publication or stable API guarantee.
