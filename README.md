# SymQ

**Exact Boolean algebra, symbolic simulation, and equivalence checking for reversible circuits.**

[![CI](https://github.com/yoch/symq/actions/workflows/ci.yml/badge.svg)](https://github.com/yoch/symq/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

SymQ is an **experimental, self-contained research toolkit** for reasoning about Boolean functions and circuits built from **X, CX, CCX, and MCX** gates. It offers exact algebraic normal forms (ANFs), interchangeable symbolic backends (including an optional native C/ZDD engine), a separate SAT decision engine, and a small, checked **assume/guarantee composition** prototype.

The core distinction: symbolic backends **compute output polynomials**; the SAT engine **decides an equivalence question** without exporting those polynomials. Neither is a general-purpose quantum-circuit verifier.

## At a glance

| You need to… | Use | What it establishes |
| --- | --- | --- |
| Evaluate or invert a classical reversible circuit | `Circuit.run` / `Circuit.inverse` | Exact basis-state behavior |
| Inspect exact Boolean output functions | `ANF`, `simulate` | One canonical Boolean polynomial per output wire |
| Compare full reversible functions | `check_equivalence` | Exact symbolic equality; checked counterexample on disagreement |
| Check only selected outputs or restored wires | `symq.sat.check_sat_equivalence` + `Contract` | SAT decision under an explicit observation/cleanup contract |
| Prove a substitution across a circuit cut | `symq.sat.composition.check_composition` | Four SAT obligations, including a universal local suffix lemma |
| Study sign phases and measurement-based uncomputation | `symq.phase` | Reference semantics for a **restricted** ±1-phase/HMR fragment |

Every supported reversible gate has controls first and target last. Wires and integer input assignments are **zero-indexed, least-significant-bit first**.

### The algebra behind SymQ

Output functions live in the Boolean ring

$$
\mathbb{F}_2[x_0,\ldots,x_{n-1}]\big/\langle x_i^2-x_i \mid 0\le i<n\rangle
$$

Addition is XOR; multiplication is AND with idempotence ($x_i^2=x_i$). A monomial $\prod_{i\in S}x_i$ is represented by the bitmask of $S$, and coefficients cancel modulo two. Canonical ANFs let symbolic checkers decide equality by comparing output functions exactly, subject to their resource limits.

## Install

**Requirements:** Python 3.10+. SymQ is currently developed from source; there is **no stable PyPI release or API compatibility guarantee**.

```bash
git clone https://github.com/yoch/symq.git
cd symq
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

For the optional SAT solver or for development/tests:

```bash
python -m pip install -e ".[sat]"  # PySAT-backed decision engine
python -m pip install -e ".[dev]"  # tests, lint and SAT dependencies
```

The C/ZDD extension is **optional**. It is built when a suitable toolchain is available; otherwise pure-Python backends remain usable. In a source checkout:

```bash
python tools/build_native.py --diagnose
python tools/build_native.py --require
python -m symq doctor
```

`doctor` reports registered backends and returns exit code **1** when the native core is unavailable (even when pure-Python mode is functioning normally). To explicitly opt out of native compilation set `SYMQ_SKIP_NATIVE=1`; to make native support mandatory set `SYMQ_REQUIRE_NATIVE=1`.

## Quick start: prove two circuits equivalent

```python
from symq import ANF, Budget, Circuit, check_equivalence

# Boolean-ring identities are exact.
x = ANF.variable(0)
assert x * x == x
assert x ^ x == ANF.constant(0)

# Every CCX is its own inverse.
reference = Circuit(3)
candidate = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)

proof = check_equivalence(
    reference, candidate, backend="sparse",
    budget=Budget(max_seconds=5),
)
assert proof.equivalent

# A genuinely different circuit produces a concrete counterexample.
mutant = Circuit(3).ccx(0, 1, 2)
result = check_equivalence(reference, mutant, backend="sparse")
assert not result.equivalent
assert reference.run(result.witness) != mutant.run(result.witness)
```

`check_equivalence` computes both output-function tuples and compares them. A non-equivalence witness is checked again by `Circuit.run`. For very small circuits, `Circuit.equivalent(other, max_width=16)` also offers exhaustive enumeration; it refuses larger widths rather than silently sampling.

### Choose an exact symbolic backend

```python
from symq import Circuit, make_algebra, simulate

circuit = Circuit(3).ccx(0, 1, 2)
algebra = make_algebra("zdd", width=circuit.width)  # pure Python
outputs = simulate(circuit, algebra)
assert algebra.to_anf(outputs[2]).degree == 2
```

| Backend(s) | Primary purpose | Notes |
| --- | --- | --- |
| `reference`, `sparse`, `sparse-copy` | Explicit ANF monomial sets | Transparent reference and differential/ablation backends |
| `zdd` | Compressed monomial families | Pure Python; **256-wire maximum** |
| `zdd-native` | C/ZDD with a fused gate loop | Optional compiled extension; **64-wire limit** |
| `auto-zdd`, `adaptive-wire` | Mixed or adaptive sparse/ZDD evaluation | Experimental representation policies |
| `packed`, `packed-fallback` | Compact low-degree ANFs | Packed-only refuses degree above 2; fallback remains exact |
| `truthtable` | Dense independent oracle | Intended for small widths; refuses width above 18 by default |

No single backend wins on every circuit. The native ZDD representation can avoid materializing huge monomial sets, but variable order and caching matter. See [backend contracts](docs/research/BACKENDS.md) and the [matched external comparisons](docs/research/EXTERNAL_BASELINES.md).

**Native width and memory:** if a circuit exceeds 64 wires but decomposes into independent interaction components, `check_equivalence_by_blocks` can verify them separately. Larger components use the configured fallback (default `zdd`, **up to 256 wires**); choose an appropriate other backend for still wider components. Native ZDD collection is **opt-in** (via `backend_options={"collect_every": ...}`); collection remaps internal node IDs and can increase runtime. Use it only with the documented one-shot/pinned-root discipline ([details](research/symq-v2/GC.md)).

## Optional SAT engine: equivalence under a contract

Install `.[sat]` and import from `symq.sat`:

```python
from symq import Budget, Circuit
from symq.sat import Contract, check_sat_equivalence

left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
right = Circuit(3)
contract = Contract(
    observed_outputs=(0, 1),
    restored_wires=(2,),
)
verdict = check_sat_equivalence(
    left, right, contract, budget=Budget(max_seconds=10),
)
assert verdict.outcome == "equivalent"
```

`Contract` supports input-bit constants, selected outputs, injective output maps, and wires that must return to their original values. Restored wires are checked **on both circuits**; a borrowed/dirty wire is not implicitly initialized to zero.

SAT outcomes are `equivalent`, `different` (with a concretely replayed witness), or `inconclusive`. Equivalence means the **encoded miter is UNSAT**; SymQ does not currently export an independently checked LRAT/DRAT proof. SAT uses cooperative elapsed-time limits, not process-kill deadlines; symbolic node/term limits do not apply to the SAT engine.

Unlike an `Algebra` backend, SAT produces a **decision**, not output ANFs. Installing it does not change the default symbolic checker.

### Research API: local relational composition

SymQ includes a bounded, experimental way to prove a two-block substitution via a **relation between independent cut states**. It checks four separate obligations: satisfiable input domain, prefix establishment of the relation, implication of the next block's precondition, and a **universal suffix lemma** over all cut states allowed by that relation.

For prefixes $A,A'$ and suffixes $B,B'$, the SAT queries are:

$$
\begin{aligned}
P(x) & &&\text{SAT (nonempty domain)},\\
P(x)\land\neg R(A(x),A'(x)) & &&\text{UNSAT},\\
R(u,v)\land\neg\operatorname{Pre}_B(u) & &&\text{UNSAT},\\
R(u,v)\land\operatorname{Pre}_B(u)\land\neg\operatorname{post}(B(u),B'(v)) & &&\text{UNSAT}.
\end{aligned}
$$

The cut states $u$ and $v$ are independent symbolic inputs in the last two queries; only $R(u,v)$ relates them.

```python
from symq import Circuit, Budget
from symq.sat.assumptions import And, Const, Eq, Var
from symq.sat.composition import Interface, Guarantee, check_composition

def same_three(a, b):
    return And(
        And(Eq(Var(f"{a}.0"), Var(f"{b}.0")),
            Eq(Var(f"{a}.1"), Var(f"{b}.1"))),
        Eq(Var(f"{a}.2"), Var(f"{b}.2")),
    )

a = Circuit(4).ccx(0, 1, 2)
a_prime = Circuit(4).ccx(0, 1, 2).x(3)
b = Circuit(4).cx(2, 0)

result = check_composition(
    prefix_left=a, prefix_right=a_prime,
    suffix_left=b, suffix_right=b,
    interface=Interface(4, Const(True), same_three("u", "v")),
    guarantee=Guarantee(4, Const(True), same_three("s", "t")),
    budget=Budget(max_seconds=10),
)
assert result.accepted
```

Here $R(u,v)$ equates observed wires $0,1,2$ while allowing wire $3$ to differ. Wire 3 is deliberately **ignored garbage**, not a certified restored ancilla. The example proves equality of the observed outputs 0, 1, and 2 even though the prefixes differ on wire 3. The tool rejects unsatisfiable input assumptions and replays cut-state counterexamples independently.

**Important:** this is a proof-expression capability, **not** an observed speedup. The initial small pilot costs more than a monolithic miter; see the [composition study](research/symq-v2/RELATIONAL.md).

## Import a strict OpenQASM subset

```python
from symq import Circuit
from symq.qasm import parse_qasm

circuit = parse_qasm(
    "OPENQASM 3.0; qubit[3] q; ccx q[0], q[1], q[2];"
)
assert circuit == Circuit(3).ccx(0, 1, 2)
```

The parser accepts one register and the supported controlled-X family in OpenQASM 2/3. It **rejects** unsupported gates, measurements, classical control, arbitrary definitions, and non-identity input/output permutation annotations rather than approximating them.

## A separate, restricted phase/HMR reference model

`symq.phase` handles a deliberately narrow fragment: X/CX/MCX, Z/CZ/MCZ with **±1 phases**, X-basis measure-and-reset (`hmr`), and Z-type classical feed-forward. It checks clean-ancilla and outcome-independence obligations.

```python
from symq.phase import PhaseProgram, check_phase_equivalence

program = PhaseProgram(3, 1).ccx(0, 1, 3).cx(3, 2)
outcome = program.hmr(3)
program.cz_if(outcome, 0, 1)

specification = PhaseProgram(3).ccx(0, 1, 2)
assert check_phase_equivalence(program, specification).equivalent
```

This is **not** general quantum equivalence or a general channel checker. Arbitrary H gates, S/T, complex rotations, and unsupported measurements are outside this grammar. Phase/HMR uses its own pure-Python reference semantics, not the Boolean backends or native ZDD core. See the [phase specification](docs/research/PHASE_HMR_SPEC.md) and [semantic audit](docs/research/AUDIT_2026-10-27.md).

## Correctness, budgets, and limitations

- **Exactness is conditional on supported semantics.** Invalid gates or malformed circuit IR are rejected. An exceeded symbolic budget raises `ResourceLimitExceeded`; no approximate result is returned.
- **Resource guards differ by engine.** `Budget(max_terms=…, max_nodes=…, max_seconds=…)` controls symbolic computations. SAT and composition use cooperative time budgets and distinguish undecided results from proofs.
- **Proof claims have a boundary.** A SAT `equivalent` verdict rests on the correctness of its encoding and solver; a symbolic verdict rests on canonical ANF operations. Neither constitutes an independently checkable proof certificate for arbitrary quantum programs.
- **Output contracts matter.** Ignored wires are not magically restored; an observed-output equivalence is not full-state equivalence. If scratch cleanup matters, it must be part of the contract.
- **Development status:** version 0.1.0, pre-release. No PyPI publication, no frozen public API, and no general cross-library performance guarantee.

## Research and reproducibility

SymQ keeps exploratory work separate from the maintained implementation:

- [Backend design and constraints](docs/research/BACKENDS.md) · [external baselines](docs/research/EXTERNAL_BASELINES.md) · [benchmark findings](docs/research/BENCHMARK_FINDINGS.md).
- [V2 SAT and strategy decisions](research/symq-v2/README.md) · [relational proof pilot](research/symq-v2/RELATIONAL.md).
- [Negative XAG-to-CNF pilot](research/symq-v2/XAG.md) and [COI feasibility study](research/symq-v2/ISSUE70_DIAGNOSTIC.md): these do **not** justify replacing the default engine.
- [Finite-field bilinear incidence research](research/xag-synthesis/REPORT.md): a lower bound on **rank-one term incidences**, **not** on CCX/CX/T gate counts or reversible-circuit optimality.
- [Historical research archive](research/archive/2026-10-27/ARCHIVE_GUIDE.md) and [research manifest policy](research/README.md).

Historical and exploratory timings are not universal benchmarks; compare algorithms on matched predicates, exact commits, environments, and held-out workloads. Experimental engine-choice heuristics (`symq.strategy.choose`) only **recommend** an option; they do not dispatch or modify defaults.

## Development and contributing

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

For optional native baseline comparisons use `.[dev,external]`; these integrations are not required for core SymQ and have their own external dependencies and licensing considerations.

Contributions should specify the semantic contract, include differential and adversarial tests, preserve valid witnesses, and record benchmarks with exact source/tool versions. See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).

MIT-licensed. **Research software; not a certified general-purpose quantum verifier.**
