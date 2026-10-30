# SymQ

The opt-in, installed [`symq.experimental` API](docs/experimental.md) now provides
explicit full/reduced HMR channels, coherent input domains, reusable references,
capability diagnostics, profiling and replay. Specialized dyadic-phase, hybrid
and local-composition APIs retain their own declared limits. The stable facade's
theorems are unchanged. See the [qualification evidence](docs/roadmap-evidence.md)
and [roadmap status](docs/roadmap-status.md) for scope, reproducible checks and
remaining adoption gates.

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
| Compare small hybrid quantum channels and observed classical instruments | `research/hybrid_channel/oracle.py` | Exact CPTP equality on all input coherences, with explicit trace / instrument contracts (bounded reference) |
| Audit restricted HMR full-channel equivalence | `research/hmr_native_channel/` | Outcome-factored channel theorem in Python ZDD or **opt-in** native C/ZDD, with explicit width limits |
| Record evidence and safely forget observations | `research/verification_api/contracts.py` | Experimental physical proof frames and verdict-sensitive implications; **not** a production certificate service |

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

1. **Nonempty domain:** $P(x)$ must be satisfiable (SAT).
2. **Prefix:** $P(x)\land\neg R(A(x),A'(x))$ must be unsatisfiable (UNSAT).
3. **Interface:** $R(u,v)\land\neg \mathrm{Pre}_B(u)$ must be UNSAT.
4. **Suffix:** $R(u,v)\land \mathrm{Pre}_B(u)\land\neg \mathrm{post}(B(u),B'(v))$ must be UNSAT.

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

This `symq.phase` entry point is **not** a general quantum equivalence checker. Arbitrary H gates, S/T, complex rotations, and unsupported measurements are outside this grammar. Its phase semantics remain pure Python; an **additional, opt-in research verifier** for full channels in a narrower sign/HMR grammar is described below. See the [phase specification](docs/research/PHASE_HMR_SPEC.md) and [semantic audit](docs/research/AUDIT_2026-10-27.md).

## Audited research extensions (explicitly opt-in)

These modules are versioned with the source repository, **not** part of a stable public API. They were admitted into `main` as research with independent tests and specific theorem domains; none changes the default classical equivalence or SAT dispatch.

| Research module | What it establishes | Boundary / next gate |
| --- | --- | --- |
| [Exact hybrid CPTP oracle](research/hybrid_channel/README.md) (#90) | Full-channel or observed-classical-instrument equality on **every** matrix unit `|x><y|`, including optional trace of clean-prepared ancillas | Exponential reference: default width cap **6 total quantum wires**, event/branch budgets; restricted real/±1 gate set, no general complex quantum circuits |
| [Temporal substitution](research/temporal_substitution/README.md) (#92) | Exact transcripts for substitutions of **total classical reversible permutations** | Not a theorem for general quantum, HMR or partial/dirty-ancilla semantics without a separate proven contract |
| [Bounded-degree ANF and finite domains](research/bitset_degree3/README.md) (#93) | Colex bitset ANF, finite-domain checks and GF(2) dual certificates | Intermediate degree overflow **fails closed** even if later cancellation might have reduced the result; finite classical domain is not a coherent quantum-subspace certificate |
| [HMR phase-debt feedback](research/hmr_feedback/README.md) (#94) | Explicit conditional phase correction for the supported sign/HMR fragment, including GF(4)/GF(8) multi-output research gadgets | Not a generic measurement-reset or gate-count-optimal synthesizer |
| [Outcome-factored HMR channel checker](research/hmr_native_channel/README.md) (#95, #103) | Exact **full coherent-channel** comparison for the narrow `PhaseProgram` grammar, including output map, dephasing kernel and relative phases; Python ZDD or optional native C/ZDD | Native monolithic supports **at most 32 data wires** (`2*n_data <= 64` paired variables); refuses unsupported operations, does not check observed classical instruments |
| [Typed physical proof contracts](research/verification_api/RAPPORT.md) (#102) | Experimental `PhysicalFrame`, theorem classes and separate `EQUIVALENT`, `DIFFERENT`, `INCONCLUSIVE`, `UNSUPPORTED`, `INTERNAL_ERROR` states | No stable adapter/production API; `restate` and `forget_instrument` are **EQUIVALENT-only logical consequences**, not fresh density-matrix or Kraus-sum computations |

### Small exact hybrid-channel example

The bounded CPTP oracle compares the entire input-coherence basis, not only classical truth tables. In this example a conditioned CZ cancels the phase from measurement-assisted erasure:

```python
from research.hybrid_channel.oracle import HybridProgram, same_channel

reference = HybridProgram(3, 1).ccx(0, 1, 2)
repaired = (
    HybridProgram(3, 1)
    .ccx(0, 1, 3).cx(3, 2)
    .hmr(3, "b0").cz(0, 1, condition="b0")
)
assert same_channel(repaired, reference).equivalent
assert same_channel(repaired, reference, trace_ancillas=True).equivalent
```

`same_instrument(..., observed_slots=("b0",))` is a **different question**: equality of unconditional channels does not imply equality of recorded classical outcomes. Exact counterexamples, independent conditioned-map summation and partial-trace tests live in [the public qualification kit](research/public_qualification/forgetful_maps.md) and [its tests](tests/test_forgetful_channel_maps_research.py) (#101).

### Native channel width, factorization and budgets

- **Classical** `check_equivalence(Circuit, Circuit, backend="zdd-native")` uses **one ZDD variable per circuit wire**, with a native limit of **64 wires**.
- **Quantum HMR** `research.hmr_native_channel.native_channel.check_full_channel(..., backend="zdd-native")` uses **two copies of each data input** to retain every coherence `|x><y|`; hence it requires `2*n_data <= 64`, or **32 data wires**. Its explicit `backend="zdd"` pure-Python path can decide wider cases within budgets.
- The optional [block-decomposition pilot](research/hmr_native_channel/blocks.py) can compare **wider full channels** when the **joint interaction/measurement-dependency partition** of both programs has blocks of at most 32 data wires. It checks ancilla-only factors, locally reindexes HMR outcomes and replays witnesses in the original global coordinates. If a block is still too large, it refuses rather than silently ignoring it. This does **not** remove the general native 32-data-wire limit.
- The optional [`rename` research acceleration](research/hmr_native_channel/rename_reuse.py) reuses the coherent `y` half by exact native ZDD Boolean-variable substitution. The compiled primitive lives in `src/symq/backends/_zdd.c`, but **no default checker calls it**. Its admissible maps, node budgets and canonicalization are tested independently.
- A budget exhaustion is **not** `DIFFERENT`; `ResourceLimitExceeded`, unsupported input and missing optional native extension are distinct outcomes. The experimental certificate frame pins input domain, program SHA-256s, ancilla preparation, retained/traced outputs and observed slots. A reduced instrument must **never** be relabeled a full retained-ancilla channel.

### Evidence and reproducibility

The existing [MIT-licensed QCEC corpus](benchmarks/corpus/qcec/MANIFEST.json) is pinned to upstream `98d6784176bfeb6ef923d4d0220e8d486dc1982f`; **19 of its 20 circuits** are within the supported **classical reversible** grammar. Its measurements compare equivalent rewrites and deliberately mutated circuits using `check_equivalence`. Reported speedups are for that **classical** task, not HMR channel checking; its original holdout was inspected and is not untouched for future tuning.

The [HMR cost report](research/hmr_native_channel/COST_REPORT.md) separately documents **synthetic** channel cases: most cost in the tested nonlinear family comes from symbolic output construction; native `rename` gave an exploratory **1.20× median** across 49 paired comparisons (with some regressions), and component factorization handled selected 36/40-data-wire examples. These are **not** production promises or evidence on a redistributable real compiler-generated HMR corpus.

For direct regression checks in a source checkout:

```bash
python -m pytest -q tests/test_forgetful_channel_maps_research.py
python -m pytest -q tests/test_verification_contracts.py
python -m pytest -q tests/test_hmr_block_soundness.py tests/test_hmr_channel_cost.py
```

The native-specific tests require the optional extension and otherwise report skips; `ruff check .` and the full CI matrix include a pure-Python job and C sanitizers. For exact source, scopes and known limits see the [independent audit](research/audit_crossrepo_20261029/README.md), the [verification qualification](research/verification_api/RAPPORT.md), and [HMR cost study](research/hmr_native_channel/COST_REPORT.md).

## Installed experimental verification (research-only)

The **opt-in** `symq.experimental` package is available from a source checkout or installed wheel.
It does **not** replace the stable `symq.verification` API, change the default backend,
automatically select a theorem, or turn computation results into independently checked
proof certificates. Each request declares its physical input domain, observed outputs,
classical records, theorem and engine explicitly.

| Capability | Entry point or documentation | Scope and limits |
| --- | --- | --- |
| Typed channel/instrument queries and diagnostics | [Experimental API](docs/experimental.md), `symq.experimental.verify` / `inspect` | Exact full/reduced channels or observed classical instruments under explicit frames; unsupported grammars or backend absence fail closed |
| Coherent legal domains | [Domain and API guide](docs/experimental.md) | Full cubes, affine spaces, injective reversible preparation and Boolean predicates; **all** admitted input coherences are compared |
| Wider native ZDD | `zdd-native-wide`, [roadmap status](docs/roadmap-status.md) | Explicit 128-variable native engine (**up to 64 paired coherent data inputs** for a monolithic HMR check); historical `zdd-native` remains 64-variable, and C extension is optional |
| Shared symbolic work | `rename_many`, owner-local DAG transfer, `prepare_reference` | Exact Boolean substitution and reference reuse; manager-owned handles, no foreign-ID cache reuse, no demonstrated workload-wide speedup |
| Reduced quantum channels and HMR coefficients | [Experimental API](docs/experimental.md) | Ordered retained outputs, explicit trace of discarded outputs, outcome-forgotten sign/HMR kernel; not an observed classical instrument |
| Hybrid Kraus oracle and strict imports | [Qualtran GF2MulMBUC fixtures](benchmarks/corpus/qualtran/README.md), [experimental guide](docs/experimental.md) | Bounded exact hybrid reference: default **six physical wires**, **eight events**; source-pinned Qualtran m=1/m=2 are *small* exhaustive examples, not large benchmark evidence |
| Dyadic and cyclotomic phases | [Exact phase semantics](docs/experimental-phases.md) | Integer phase polynomials modulo powers of two and a bounded cyclotomic channel reference; no generic continuous-angle or dynamic-HMR symbolic solver |
| Local channel composition and reusable obligations | [Quantum composition](docs/experimental-composition.md) | Exact bounded local matrix-unit checks, complete transcripts, proved clean cuts, retained classical records, phase ledgers and replaying obligation DAG; receipts alone are never proof |
| CLI, result replay and profiling | [Experimental CLI](docs/experimental.md), [evidence](docs/roadmap-evidence.md) | Closed versioned JSON input, witness replay, exclusive stage profiling and optional subprocess isolation; no automatic fallbacks |

From a source checkout with development dependencies installed:

```bash
python -m symq inspect examples/experimental/candidate.json --other examples/experimental/reference.json
python -m symq verify examples/experimental/reference.json examples/experimental/candidate.json --contract examples/experimental/contract.json --report /tmp/symq-proof.json
python -m pytest -q tests/test_stack106_112_adversarial.py
```

**Budget semantics:** nested checks inherit an absolute same-process deadline;
spawned workers receive a bounded duration, return a **typed, size-limited JSON**
result and do not unpickle arbitrary output objects in the parent.
Operating-system cleanup has a separately documented grace period. Hard process limits
and cooperative verifier budgets are not interchangeable.

**Evidence:** the [fixed synthetic campaign](docs/roadmap-evidence.md) archives 210
source-pinned worker records (180 expected decisions, 30 expected refusals), with
end-to-end Python/native ratios generally near parity. Positive microbenchmarks for
renaming and DAG reuse do **not** establish a general performance advantage. The
small public Qualtran cases establish authentic import and bounded channel correctness
only. Check the recorded SHA and accepted/unsupported denominators before quoting a
measurement. The [roadmap-status matrix](docs/roadmap-status.md) lists additional
per-feature adoption gates, and [integration audit](docs/integration-audit.md) records
the repaired deadline, IPC, modular-zero and capability-inspection regressions.

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
- [Hybrid/CPTP research and independent audit](research/audit_crossrepo_20261029/README.md) · [typed proof-frame qualification](research/verification_api/RAPPORT.md) · [native HMR cost report](research/hmr_native_channel/COST_REPORT.md).
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
