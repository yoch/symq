# SymQ

**Exact Boolean functions and reversible-circuit verification — with explicit quantum research extensions.**

[![CI](https://github.com/yoch/symq/actions/workflows/ci.yml/badge.svg)](https://github.com/yoch/symq/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)
[![MIT license](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

SymQ is a self-contained Python research toolkit for **exact algebraic normal forms (ANFs)**, symbolic simulation and equivalence checking of **X/CX/CCX/MCX reversible Boolean circuits**. It provides pure-Python and optional native C/ZDD backends, a separate SAT decision engine, and opt-in tools for restricted measurement-assisted quantum circuits.

The distinction is intentional: **computing output functions**, **deciding equivalence**, and **comparing quantum channels** are different tasks with different proof obligations. SymQ does not silently switch between them.

> **Status:** experimental, version 0.1.0. No stable API or PyPI release is promised. SymQ is not a universal quantum-circuit verifier, a formally verified C implementation, or a source of independently checkable UNSAT proof certificates.

**Navigate:** [Quick start](#quick-start) · [Choose a verifier](#choose-a-verifier) · [Installation](#installation) · [Research extensions](#opt-in-quantum-and-composition-research) · [Limits](#exactness-and-limits) · [Documentation](#documentation-and-evidence)

## Quick start

This example uses only the pure-Python core; no SAT solver or C compiler is required.

```python
from symq import Budget, Circuit, check_equivalence, make_algebra, simulate

reference = Circuit(3)
candidate = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)

result = check_equivalence(
    reference, candidate, backend="sparse", budget=Budget(max_seconds=5)
)
assert result.equivalent

# A real difference has a concrete, replayable input.
mutant = Circuit(3).ccx(0, 1, 2)
different = check_equivalence(reference, mutant, backend="sparse")
assert not different.equivalent
assert reference.run(different.witness) != mutant.run(different.witness)

# Inspect the exact Boolean output polynomials instead.
algebra = make_algebra("zdd", width=3)
outputs = simulate(mutant, algebra)
assert algebra.to_anf(outputs[2]).degree == 2
```

All wire indices start at zero. Controls precede the target (e.g. `ccx(control1, control2, target)`); integer inputs use least-significant-bit-first indexing.

A circuit is represented as a reversible Boolean function. The output ANFs belong to

$$
\mathbb{F}_2[x_0,\ldots,x_{n-1}]/\langle x_i^2-x_i\rangle .
$$

XOR is addition, AND is multiplication, and each Boolean function has a unique square-free ANF. This makes exact symbolic comparison possible **when the computation fits its declared resource budget**.

## Choose a verifier

Start with the *question you want proved*, not the fastest-looking backend.

| Question | Entry point | What a successful result means |
| --- | --- | --- |
| What does a reversible circuit do on a basis input? | `Circuit.run` / `Circuit.inverse` | Exact classical permutation behavior |
| What are its Boolean output functions? | `make_algebra` + `simulate` + `to_anf` | Exact ANFs for all output wires |
| Are two complete reversible circuits equivalent? | `check_equivalence` | Every output agrees on every Boolean input; a difference has a replayed witness |
| Are selected outputs equal, with explicit input constants and restored wires? | `symq.sat.Contract` + `check_sat_equivalence` | SAT/UNSAT decision for **that declared classical contract**, without exporting ANFs |
| Is a restricted ±1-phase/HMR program a valid clean, outcome-independent rewrite? | `symq.phase.check_phase_equivalence` | A **strict branch/unitary** result under its O1/O2 obligations |
| Do restricted HMR programs implement the same **full or reduced quantum channel**? | `symq.experimental.verify` + `VerificationContract` | Equality on **all coherent input pairs**, under an explicit physical frame |
| Do recorded classical measurement outcomes also agree? | Experimental `instrument` theorem with `hybrid-exact` | Equality of the **observed instrument**, not merely the outcome-forgotten channel |
| Does a local substitution hold within a fully pinned transcript? | `symq.sat.composition` or `symq.experimental.composition` | Only the relevant classical relation or bounded quantum-channel composition theorem |

The first four rows concern reversible **Boolean** circuits. The remaining rows have **distinct** quantum or compositional semantics; they are not interchangeable with ordinary classical equivalence.

### Example: a classical SAT contract

```python
from symq import Budget, Circuit
from symq.sat import Contract, check_sat_equivalence

left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
right = Circuit(3)
contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))

verdict = check_sat_equivalence(left, right, contract, budget=Budget(max_seconds=10))
assert verdict.outcome == "equivalent"
```

SAT decides a Boolean relation; it does **not** produce symbolic ANFs. A restored wire must return to its **own original value**, even if it is borrowed/dirty. An ignored wire is not implicitly restored. The SAT solver may return `inconclusive` when its budget is exhausted, and no independently checked LRAT/DRAT certificate is exported.

## Installation

**Requirements:** Python 3.10 or newer. Install from a source checkout:

```bash
git clone https://github.com/yoch/symq.git
cd symq
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

Optional dependencies are deliberately separate:

| Installation | Adds |
| --- | --- |
| `python -m pip install -e ".[sat]"` | PySAT for the classical SAT decision engine |
| `python -m pip install -e ".[dev]"` | Tests, Ruff and SAT development dependencies |
| `python -m pip install -e ".[dev,external]"` | Optional PolyBoRi, CUDD and MQT QCEC comparison adapters |

The **native C/ZDD extension is optional** and can build during installation when a compiler is available. Diagnose or require it explicitly:

```bash
python tools/build_native.py --diagnose
python tools/build_native.py --require
python -m symq doctor
```

`SYMQ_SKIP_NATIVE=1` opts out of native builds; `SYMQ_REQUIRE_NATIVE=1` demands one. Do not set both. The mandatory environment flag takes precedence over the build CLI's `--optional` flag. Note that `doctor` returns exit code **1** without the native core even if the pure-Python backends are working.

### Classical backends at a glance

| Backend | Best used for | Boundary |
| --- | --- | --- |
| `sparse` / `reference` | Understandable explicit ANFs, independent small checks | Materialization can be exponential |
| `zdd` | Exact compressed monomial families in Python | Maximum 256 Boolean variables |
| `zdd-native` | Optional compiled monomial ZDD and fused reversible gate loop | Maximum **64** Boolean variables |
| `zdd-native-wide` | Explicit native wider mode | Maximum **128** Boolean variables |
| `packed` / `packed-fallback` | Small low-degree ANFs | Packed-only degree ≤ 2; fallback does not truncate |
| `truthtable` | Small independent reference calculations | Default maximum 18 input wires |

Other experimental adaptive backends are listed in [backend design](docs/research/BACKENDS.md). No backend wins on every circuit. Variable order, intermediate nodes, output extraction and manager lifetime can dominate costs; the 128-variable mode does not solve worst-case exponential expansion.

For classically **disconnected** circuits, `check_equivalence_by_blocks` can verify independent components separately. A connected circuit is **not** arbitrarily decomposable without a separate, proved interface contract. Native collection is opt-in and follows an owned-root/one-shot discipline; see [GC limitations](research/symq-v2/GC.md).

## Opt-in quantum and composition research

These capabilities are **installed** under `symq.experimental` but are **not** automatic replacements for the maintained classical facade. A caller chooses a theorem, backend, input domain and observed outputs; unsupported requests fail closed.

### Restricted HMR channels

`symq.phase.PhaseProgram` expresses reversible X-type gates, ±1 Z-type phases, unconditional **X-basis measurement followed by reset** (`hmr`), and sign-phase feed-forward from earlier outcomes. Its strict reference checker additionally requires clean ancillas (**O1**) and phase independence from measurement outcomes (**O2**).

For a different question — equality of the physical **outcome-forgotten channel** — use the experimental API:

```python
from symq.experimental import VerificationContract, verify
from symq.phase import PhaseProgram
from symq.resources import Budget

reference = PhaseProgram(2, 1)
candidate = PhaseProgram(2, 1).ccx(0, 1, 2)
event = candidate.hmr(2)
candidate.cz_if(event, 0, 1)

contract = VerificationContract(theorem="full_channel", backend="zdd")
result = verify(reference, candidate, contract, budget=Budget(max_seconds=10))
assert result.equivalent
```

The quantum input consists of arbitrary coherent **data** and explicitly zero-prepared ancillas. The full-channel theorem retains all quantum outputs; `reduced_channel` additionally specifies ordered retained outputs and traces the others. The `instrument` theorem observes selected classical records through the bounded `hybrid-exact` oracle. Equality after tracing does **not** imply full-output equality, and channel equality does **not** imply equality of observed measurement records.

**Width matters:** the symbolic HMR full-channel comparison uses two Boolean variables per data bit (one for each of `x` and `y` in `|x><y|`). Consequently ordinary `zdd-native` is limited to **32 coherent data bits** for this monolithic theorem, while explicit `zdd-native-wide` extends that representation boundary to **64 data bits**, subject to resource limits. Special common-block composition needs an independently proved partition; it is not an arbitrary fallback.

### Other experimental capabilities

| Capability | Where to start | Scope |
| --- | --- | --- |
| Hybrid CPTP oracle, reset, Z measurement and value feed-forward | [Hybrid reference](research/hybrid_channel/README.md) and [experimental API](docs/experimental.md) | Exact, bounded reference; default six total physical wires and eight events |
| Coherent input domains and prepared references | [Experimental API](docs/experimental.md) | Full cubes, affine/predicate domains, reversible preparation, owned reference handles |
| Exact dyadic phases and cyclotomic channels | [Phase guide](docs/experimental-phases.md) | Restricted exact angles/grammars and bounded HMR reference; no arbitrary rotation solver |
| Classical relational cut proofs | [Composition study](research/symq-v2/RELATIONAL.md) | Explicit relation and four SAT proof obligations |
| Quantum-local rewrites, phase-debt ledger and proof graphs | [Composition guide](docs/experimental-composition.md) | Exact local obligations with complete transcripts and checked clean cuts |
| Source-pinned Qualtran HMR fixtures | [Qualtran provenance](benchmarks/corpus/qualtran/README.md) | Small `m=1/2` examples; **not** evidence of general compiler coverage |

A general Hadamard/rotation/reset program is **not** accepted by the sign-phase symbolic checker. The hybrid and cyclotomic reference engines have different, explicit grammars. See [theorem selection and resource limits](docs/experimental.md), not only a backend name.

### CLI: inspect, verify and replay

The installed `symq` CLI (also `python -m symq`) accepts closed, versioned JSON programs and contracts. Run these from the repository root with the provided examples:

```bash
symq inspect examples/experimental/candidate.json --other examples/experimental/reference.json
symq verify examples/experimental/reference.json examples/experimental/candidate.json \
  --contract examples/experimental/contract.json --report /tmp/symq-result.json
symq replay /tmp/symq-result.json
```

`inspect` checks admissibility **without proving equivalence**. `verify` returns the requested theorem's result; `replay` checks a negative witness or recomputes a positive result. A saved JSON receipt is **not** proof authority on its own. Exit codes and isolation/profiling commands are documented in the [CLI guide](docs/experimental.md).

## Exactness and limits

- **Exact does not mean unbounded.** Unsupported gates, malformed contracts and exceeded resource limits must be refused or return a non-decisive status; an unfinished computation never establishes non-equivalence.
- **Proof boundaries are essential.** Classical output equality is not coherent quantum-channel equality. A channel that forgets outcomes is not an observed classical instrument. A dirty ancilla is never silently initialized to `|0>`.
- **Computational checking is not independent certification.** Symbolic equality relies on the implementation's ring operations; SAT relies on its encoding/solver; experimental channel checks rely on the declared model and oracle. No universal, independently verified proof certificate is claimed.
- **Budgets are engine-specific.** Term/node limits describe different data structures; cooperative deadlines and isolated-process CPU/wall/address-space limits are not equivalent guarantees. See [resource contracts](docs/verification-resources.md).
- **Performance claims require matched tasks.** Decide equivalence versus export ANFs versus observed instruments separately; include setup, conversion, timeouts and unsupported counts. Small synthetic workloads cannot establish universal native superiority.

## Documentation and evidence

| Topic | Document |
| --- | --- |
| Experimental API and CLI | [`docs/experimental.md`](docs/experimental.md) |
| Advanced phases | [`docs/experimental-phases.md`](docs/experimental-phases.md) |
| Hybrid composition and proof DAGs | [`docs/experimental-composition.md`](docs/experimental-composition.md) |
| Implemented roadmap and remaining gates | [`docs/roadmap-status.md`](docs/roadmap-status.md) |
| Source-pinned campaign and performance limitations | [`docs/roadmap-evidence.md`](docs/roadmap-evidence.md) |
| Restricted HMR formal semantics | [`docs/research/PHASE_HMR_SPEC.md`](docs/research/PHASE_HMR_SPEC.md) |
| Backend design and external comparisons | [`docs/research/BACKENDS.md`](docs/research/BACKENDS.md), [`EXTERNAL_BASELINES.md`](docs/research/EXTERNAL_BASELINES.md) |
| Research results, including negative findings | [`research/README.md`](research/README.md) and [historical archive](research/archive/2026-10-27/ARCHIVE_GUIDE.md) |

On `main`, the evidence includes a pinned **classical** QCEC corpus, small authentic Qualtran `m=1/2` fragments and a **synthetic** 210-worker qualification campaign. These have different theorem contracts and do not establish broad HMR coverage or generic speedups. More recent benchmark/manuscript/HMR studies may exist in **unmerged PRs**; a successful PR check is not evidence that its artifacts have been integrated into `main`. Consult the [qualification evidence](docs/roadmap-evidence.md) and the exact SHA before quoting numbers.

## Development and contributing

```bash
python -m pip install -e ".[dev]"
ruff check .
python -m pytest -q
```

Changes should declare their accepted grammar and theorem, include differential/adversarial tests, preserve concrete witnesses, and report negative benchmark results with exact source and environment fingerprints. See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).

**MIT licensed · Research software · No general-purpose quantum certification claim.**
