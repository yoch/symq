# SymQ

**Exact verification of reversible Boolean circuits, with opt-in, explicitly scoped quantum research extensions.**

[![CI](https://github.com/yoch/symq/actions/workflows/ci.yml/badge.svg)](https://github.com/yoch/symq/actions/workflows/ci.yml)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue)
[![MIT license](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

SymQ computes exact **algebraic normal forms (ANFs)** of X/CX/CCX/MCX reversible circuits and decides their **equivalence**. It has pure-Python and optional native C/ZDD backends and a separate SAT engine. It also offers opt-in checkers for restricted measurement-assisted quantum programs. Each checker proves **one named theorem**. SymQ never switches silently between computing output functions, deciding classical equivalence and comparing quantum channels.

> **Status:** experimental research software. The first release is 0.2.0; from it on, the classical core is kept compatible as the [stability policy](docs/stability.md) states, and the experimental and research layers carry no promise. SymQ is not a universal quantum-circuit verifier and not a formally verified implementation. Its verification paths do not export independently checkable certificates, except one opt-in research path for a narrow class of phase obligations ([proof levels](#proof-levels-and-replay)).

**Navigate:** [Quick start](#quick-start) · [Question → theorem → API](#question--theorem--api--limits) · [Contextual substitution](#contextual-substitution) · [Experimental APIs](#experimental-apis) · [Proof levels and replay](#proof-levels-and-replay) · [Installation](#installation) · [Limits](#limits) · [References](#references)

## Quick start

This example needs only the pure-Python core: no SAT solver and no C compiler.

```python
from symq import Budget, Circuit, check_equivalence

reference = Circuit(3)
candidate = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)   # two Toffolis cancel
result = check_equivalence(reference, candidate, backend="sparse", budget=Budget(max_seconds=5))
assert result.equivalent

mutant = Circuit(3).ccx(0, 1, 2)                     # a real difference has a replayable input
different = check_equivalence(reference, mutant, backend="sparse")
assert not different.equivalent
assert reference.run(different.witness) != mutant.run(different.witness)
```

Wire indices start at zero, and controls come before the target (`ccx(c1, c2, target)`). Integer inputs are read least-significant bit first. From the command line, `symq check left.qasm right.qasm` decides the same question and `symq anf circuit.qasm` prints the exact output polynomials. Importers accept only strict subsets: `symq.qasm.parse_qasm` takes reversible OpenQASM 2/3 and rejects measurements and classical control; `symq.kickmix.load_kmx` takes Qualtran kickmix text, including HMR programs.

## Question → theorem → API → limits

Start from the *statement you want proved*, not from the fastest-looking backend.

| Question | Theorem proved on success | Entry point | Main limits |
| --- | --- | --- | --- |
| What are the exact output functions? | Exact ANF of every output wire | `make_algebra` + `simulate` + `to_anf` | ANF size can be exponential; backend width caps ([backends](docs/guide/backends.md)) |
| Are two complete reversible circuits equal? | Every output agrees on every Boolean input; a difference carries a replayed witness | `check_equivalence`, `symq check` | Classical permutations only |
| Are selected outputs equal under constants, restored wires or input assumptions? | SAT/UNSAT of **that declared classical contract** | `symq.sat.Contract` + `check_sat_equivalence` | Budget may end `inconclusive`; no ANFs, no exported UNSAT certificate |
| Is a replacement valid **at one site** of a larger circuit? | Contextual classical substitution: domain, prefix, interface and suffix obligations | `symq.labs.contextual_substitution.check_substitution`, `symq rewrite` | Sufficient, not complete; says nothing about quantum behaviour |
| Is a ±1-phase/HMR program a clean, outcome-independent rewrite? | Strict branch equality under O1/O2 | `symq.phase.check_phase_equivalence` | Restricted grammar; O1/O2 must hold |
| Do two restricted HMR programs implement the same **full or reduced channel**? | Equality on **all coherent input pairs** under an explicit physical frame | `symq.experimental.verify` + `VerificationContract` | Two Boolean variables per data bit; width caps |
| Do recorded measurement outcomes also agree? | Equality of the **observed instrument** | Experimental `instrument` theorem, `hybrid-exact` | Bounded oracle; small programs |
| Does a reversible loader XOR an exact lookup table into its targets? | For every legal address and target, on the coherent span: output = input ⊕ `T[address]` | `symq.experimental.check_table_xor` | X/CX/CCX/MCX only; ≤ 16 address and target bits |

The first four rows are statements about **classical Boolean functions**. The table-XOR contract proves a basis permutation, which extends to the coherent span because the accepted gates have no phases. The three HMR rows have quantum semantics and are **not** interchangeable with classical equivalence. Channel equality does not imply equal measurement records, and equality after tracing does not imply full-output equality.

`symq.verify(left, right, theorem=..., engine=...)` routes each theorem to its owning engine. It never chooses a theorem or an engine for you. The result has `outcome`, `reason`, `witness` and `certified`. `equivalent` and `different` are true only for a **proved** equivalence or difference; both are false for `inconclusive` and `unsupported`.

### A classical SAT contract

```python
from symq import Budget, Circuit
from symq.sat import Contract, check_sat_equivalence

left = Circuit(3).ccx(0, 1, 2).ccx(0, 1, 2)
right = Circuit(3)
contract = Contract(observed_outputs=(0, 1), restored_wires=(2,))
verdict = check_sat_equivalence(left, right, contract, budget=Budget(max_seconds=10))
assert verdict.outcome == "equivalent"
```

A restored wire must return to **its own original value**, even when it is borrowed or dirty. An ignored wire is not implicitly restored.

## Contextual substitution

A contextual rewrite replaces the gates in `[start, stop)` and asks whether the replacement is valid **at that site**. The prefix may establish facts, such as a clean scratch wire, that make the replacement valid there but not elsewhere.

```python
from symq import Circuit
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution
from symq.labs.rewrite import Weights

# Given the declared input q2 = 0, the first two gates leave q2 clean,
# so CX(q2, q0) at position 2 is the identity there.
source = Circuit(3).cx(0, 2).cx(0, 2).cx(2, 0).cx(0, 1)
contract = SubstitutionContract(initial_constants=((2, 0),), clean_at_cut=(2,))
result = check_substitution(source, (2, 3), Circuit(3), contract=contract,
                            weights=Weights.from_mapping({"cx": 3}))
assert result.equivalent and result.cost.weighted_delta == -3

# Without the declared input, the clean cut cannot be established: refused, never trusted.
refused = check_substitution(source, (2, 3), Circuit(3),
                             contract=SubstitutionContract(clean_at_cut=(2,)))
assert refused.outcome == "precondition_failed" and refused.candidate is None
```

From the command line, the same work is a four-step workflow, run here from a checkout with the provided examples:

```bash
symq locate examples/locate/source.json examples/locate/reference.json --theorem classical
symq prepare-rewrite examples/prepare/source.json examples/prepare/original.json \
  examples/prepare/candidate.json --contract examples/prepare/contract.json \
  --weights examples/prepare/weights.json --output-dir prepared
symq rewrite prepared/request.json --report prepared/proof.json
symq replay prepared/proof.json
```

1. `locate` finds the unique exact occurrence of a small block and its wire map. It proves nothing.
2. `prepare-rewrite` turns a small original/replacement pair into a full-width request in a **new** directory. It is strictly preparatory: its output says `ready_for_proof`, `proved=false`, `candidate_authorized=false`. It never replaces an existing path, and `preparation.json` is an advisory record of the emitted file hashes.
3. `rewrite` proves (or refuses) the substitution and writes a report.
4. `replay` recomputes the proof from the embedded request and refuses an edited report.

The cut predicate contains only what the contract declares. The theorem is therefore sufficient but not complete: a valid rewrite can be `not_proved` when its justification was not declared. A rewrite checker never reports a proved difference, because a local counterexample need not be reachable from the global input. These checkers live in `symq.labs`, which carries no API promise. See the [rewrite guide](docs/guide/rewrite.md).

## Experimental APIs

SymQ has three installed layers and one development-only layer. None of them silently replaces another.

| Layer | Contents | Promise |
| --- | --- | --- |
| `symq` | Circuits, algebras, classical equivalence, SAT contracts, `verify` facade, CLI | Kept compatible as the [stability policy](docs/stability.md) states, from the first release; changes are recorded in the [changelog](CHANGELOG.md) |
| `symq.experimental` | Restricted HMR channels and instruments, coherent domains, prepared references, serialization | Installed, opt-in; explicit theorem, frame and backend required. **No API promise** |
| `symq.labs` | Contextual rewrites and their preparation, phase certificates, the LRAT proof path, research prototypes ([index](docs/labs/README.md)) | **No API promise**; may change or disappear |
| `formal/` | Lean 4 projects checked in development CI ([formal runtime model](docs/labs/formal-runtime-soundness.md), [LRAT gate lemmas](docs/labs/lean-kernel-proofs.md)) | Not installed, never imported by SymQ; Lean is not a runtime dependency |

A restricted HMR channel check:

```python
from symq.experimental import VerificationContract, verify
from symq.phase import PhaseProgram
from symq.resources import Budget

reference = PhaseProgram(2, 1)
candidate = PhaseProgram(2, 1).ccx(0, 1, 2)
event = candidate.hmr(2)
candidate.cz_if(event, 0, 1)
contract = VerificationContract(theorem="full_channel", backend="zdd")
assert verify(reference, candidate, contract, budget=Budget(max_seconds=10)).equivalent
```

A table-XOR loader check, from the opt-in experimental API:

```python
from symq import Circuit
from symq.experimental import TableXorContract, check_table_xor

loader = Circuit(6).cx(0, 2).cx(1, 2).cx(1, 3)
contract = TableXorContract(
    width=6, address_wires=(0, 1), target_wires=(2, 3), clean_wires=(4,),
    borrowed_wires=(5,), table=(0, 1, 3, 2), legal_addresses=(0, 1, 2),
    target_values=None, table_id="t0", slot_id="s1", theorem="coherent",
)
assert check_table_xor(loader, contract, backend="exhaustive").equivalent
faulty = check_table_xor(Circuit(6).cx(0, 2).cx(1, 3), contract, backend="exhaustive")
assert faulty.status == "different" and faulty.witness is not None
```

See the [table-XOR API guide](docs/guide/table-xor-public-api.md) for receipts and replay.

The HMR channel quantum input is arbitrary coherent **data** plus explicitly zero-prepared ancillas. A general Hadamard, rotation or reset program is **not** accepted by this sign-phase checker. The hybrid and cyclotomic reference engines have their own grammars. See the [experimental guide](docs/guide/experimental.md), [phases](docs/guide/experimental-phases.md) and [composition](docs/guide/experimental-composition.md).

## Proof levels and replay

A positive answer is only as strong as the step that produced it. SymQ keeps these levels apart:

| Level | What it establishes | Where |
| --- | --- | --- |
| Engine decision | SymQ computed `equivalent` for the declared theorem; trust rests on the engine (and on the SAT solver for SAT routes) | Every checker |
| Replayed witness | A claimed difference reproduces on concrete inputs, outside the symbolic engine | Classical, table-XOR and channel differences |
| Replayed report | A stored JSON report is recomputed from its embedded request; stored and fresh decisive results must match exactly | `symq replay`, `replay_table_xor` |
| Independently checked formula proof | For one opt-in research path (factored phase certificates), the obligation is encoded as a CNF and its UNSAT proof is exported as LRAT. A small standalone checker verifies it against a pinned CNF without a SAT solver, and a consumer rebuilds that CNF from the sources. In development CI, Lean's verified LRAT checker also proves selected instances. This certifies **that CNF**, not the source-to-CNF encoding or the quantum semantics | `symq.labs.lrat_rup`, `phase_proof_bundle`, `lrat_lean` ([details](docs/labs/portable-phase-proofs.md)) |
| Lean theorems about an abstract model | General theorems on Tseitin clauses, acyclic DAG evaluation, UNSAT soundness of the solver query shape and ripple-carry addition. Their statements and the model definitions are restated in checked contract files, so a weakened statement fails the build. They describe a model, which tests compare with the Python code | `formal/`, development CI only ([details](docs/labs/formal-runtime-soundness.md)) |
| Formal proof of SymQ itself | Machine-checked correctness of the Python/C runtime or of its quantum semantics | **No** |

Passing tests, a green CI run or an agreeing second engine are evidence, not formal proof. A JSON receipt authorizes nothing until it is replayed. Its provenance (input-file digests, execution data) stays historical metadata that replay cannot authenticate.

## Installation

Python 3.10 or newer. A released version installs from PyPI:

```bash
python -m pip install symq          # add "symq[sat]" for the SAT engine
```

CPython 3.10 to 3.14 on Linux (x86-64 and arm64, glibc and musl) and on macOS (Intel and Apple
silicon) get a wheel with the native C core. Everything else, Windows and free-threaded CPython
included, gets the pure-Python package: the verdicts are the same, but the native engines are
absent (`--engine native` is refused, `auto` uses the pure-Python `zdd`), so a budget can run
out where the native core would have concluded. `python -m symq doctor` says which one is
installed.
For development, install from a source checkout:

```bash
git clone https://github.com/yoch/symq.git
cd symq
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

| Installation | Adds |
| --- | --- |
| `python -m pip install -e ".[sat]"` | PySAT, for SAT contracts and contextual rewrites |
| `python -m pip install -e ".[dev]"` | Tests, Ruff, mypy and the SAT development dependencies |
| `python -m pip install -e ".[dev,external]"` | Optional PolyBoRi, CUDD and MQT QCEC comparison adapters |
| `python -m pip install -e ".[test,crosscheck]"` | MQT QCEC alone, at the version the required cross-check job uses |

| Platform | Native C core | What CI runs on every change |
| --- | --- | --- |
| Linux (x86-64) | yes | Whole suite on CPython 3.10 to 3.14; sanitizers; the cross-check against MQT QCEC |
| macOS (Apple silicon runner) | yes | Core tier on CPython 3.12 |
| Windows (x86-64) | no: pure Python only | Core tier without the native tests on CPython 3.12 |

The core tier is the tests of `symq`, `symq.sat`, `symq.backends`, the repository guards and the
runnable examples of the documentation; the tests of the experimental and research layers run
on Linux only.

The native C/ZDD extension is optional. From a checkout or a source distribution it builds at install time when a compiler and the Python headers are present; a wheel from PyPI either contains it or does not. `python -m symq doctor` reports whether it loaded and why not. See [getting started](docs/getting-started.md).

## Limits

- **Exact does not mean unbounded.** Unsupported gates, malformed contracts and exhausted budgets are refused or end `inconclusive`. An unfinished computation never establishes a difference, and `inconclusive` or `unsupported` is never turned into a proof.
- **Proof boundaries matter.** Classical output equality is not channel equality. A channel that forgets outcomes is not an observed instrument. A dirty ancilla is never silently initialized to `|0>`.
- **Decomposition needs a proof.** `check_equivalence_by_blocks` splits only classically disconnected circuits; a connected circuit is not decomposed without a separately proved interface contract.
- **Budgets are engine-specific.** Term and node limits measure different data structures. A cooperative deadline is not an isolated-process limit, and `max_bytes` is not a process memory cap. See [resource contracts](docs/guide/resources.md).
- **Performance claims need matched tasks.** Deciding equivalence, exporting ANFs and checking instruments are different jobs. No backend wins on every circuit; recorded measurements describe specific commits and workloads ([evidence](docs/index.md#evidence)).

## Documentation

| Topic | Document |
| --- | --- |
| First steps, native core | [Getting started](docs/getting-started.md), [glossary](docs/glossary.md), [index](docs/index.md) |
| Backends, orders, blocks | [Backend guide](docs/guide/backends.md) |
| SAT contracts and relational cuts | [SAT guide](docs/guide/sat.md) |
| Contextual rewrites, preparation and replay | [Rewrite guide](docs/guide/rewrite.md) |
| Table-XOR loader contracts | [Public API](docs/guide/table-xor-public-api.md), [contract guide](docs/guide/table-xor-contract.md) |
| Research modules, LRAT proofs, Lean model | [Labs index](docs/labs/README.md) |
| HMR semantics | [HMR specification](docs/reference/phase-hmr-spec.md) |
| Runnable scripts and CLI inputs | [`examples/`](examples/README.md) (the Python scripts run in the test suite; the JSON inputs are exercised by CI), [demo](docs/demo.md) |
| Architecture, archive, history | [Architecture](docs/architecture.md), [archive index](docs/archive-index.md), [changelog](CHANGELOG.md) |
| Contributing and security | [CONTRIBUTING.md](CONTRIBUTING.md), [code of conduct](CODE_OF_CONDUCT.md), [AGENTS.md](AGENTS.md), [SECURITY.md](SECURITY.md) |
| Licenses of redistributed test and benchmark inputs | [Third-party notices](THIRD_PARTY_NOTICES.md) |

## References

- S. Minato, *Zero-suppressed BDDs for set manipulation in combinatorial problems*, DAC 1993: the monomial-set representation behind the ZDD backends.
- A. Ignatiev, A. Morgado, J. Marques-Silva, *PySAT: A Python toolkit for prototyping with SAT oracles*, SAT 2018 ([PySAT](https://pysathq.github.io/)): the SAT engine.
- L. Burgholzer, R. Wille, *Advanced equivalence checking for quantum circuits*, IEEE TCAD 2021 ([MQT QCEC](https://github.com/cda-tum/mqt-qcec)): the optional comparison adapter.
- [Qualtran](https://github.com/quantumlib/Qualtran) (Apache-2.0): source of the pinned kickmix fixtures ([provenance](benchmarks/corpus/qualtran/README.md)).
- L. Cruz-Filipe, M. Heule, W. Hunt, M. Kaufmann, P. Schneider-Kamp, *Efficient certified RAT verification*, CADE 2017: the LRAT proof format.
- L. de Moura, S. Ullrich, *The Lean 4 theorem prover and programming language*, CADE 2021: the proof assistant used in `formal/`.

## Development

```bash
python -m pip install -e ".[dev]"
ruff check .
mypy
python -m pytest -q
```

`SYMQ_TEST_REQUIRE=native,sat` turns the skips of `native`- and `sat`-marked tests into errors. Changes should state their accepted grammar and theorem, add differential and adversarial tests, keep concrete witnesses, and report negative results with exact source and environment fingerprints.

**MIT licensed · Research software · No general-purpose quantum certification claim.**
