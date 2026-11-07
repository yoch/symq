# SAT discovery of classical cut invariants

`symq.labs.cut_invariants` is an opt-in research API. It discovers relations
between the wires at the output of an exact reversible prefix. It supports the
validated X/CX/CCX/MCX `Circuit` grammar and a classical initial-input contract.
It does not infer quantum support, handle measurement histories, or authorize
a rewrite. Nothing changes the stable checker or its default backend.

The practical motivation is local arithmetic structure. A carry chain may have
relations such as `z = a*b`, `w = c*z`, and `v = d*w` that remain quadratic in
cut-wire coordinates, although expansion into the original inputs has higher
degree. The existing contextual substitution checker can use these relations,
but previously required the caller to provide them.

## Learn, then prove the actual substitution

```python
from symq import Circuit
from symq.labs.cut_invariants import discover_cut_invariants, replay_cut_invariants
from symq.labs.contextual_substitution import SubstitutionContract, check_substitution

prefix = Circuit(4).ccx(0, 1, 2)
initial = ((2, 0),)  # The target of this prefix starts at zero. Wire 3 is arbitrary.
learned = discover_cut_invariants(prefix, initial_constants=initial)
assert learned.proved

# The serialized document is untrusted. Replay binds a separately supplied
# prefix and initial contract and runs the exact obligation again.
rechecked = replay_cut_invariants(prefix, learned.to_dict(), initial_constants=initial)
assert rechecked.proved

source = Circuit(4).ccx(0, 1, 2).cx(2, 3)
candidate = Circuit(4).ccx(0, 1, 3)
contract = SubstitutionContract(
    initial_constants=initial,
    cut_assumption=rechecked.cut_assumption(prefix),
)
proof = check_substitution(source, (1, 2), candidate, contract=contract)
assert proof.outcome == "equivalent"
```

The inferred predicate entails `u.2 = u.0 AND u.1`. The original block uses
`u.2` as a control; the replacement uses its two factors. Without that relation,
these blocks disagree on some arbitrary cut assignments. The substitution
checker independently proves the prefix predicate and the local replacement.
Changing the surrounding prefix invalidates the old relation when appropriate.

`cut_assumption(prefix)` checks that its result was issued by a completed check
or fresh replay and that the supplied prefix has the proved digest. Its private
seal guards against accidental Python-side result mutation; it is not a digital
signature. The returned expression is a proof input, never a rewrite permission.
It is a balanced tree, but it must fit the SAT assumption depth bound
(`symq.sat.assumptions.MAX_DEPTH`, 24). Very wide monomials or relation sets
that do not fit raise `ExprError`, a `ValueError`; the proved result stays valid.

## Exact theorem and completeness boundary

Let `F(x)` be the frozen prefix and `P(x)` its initial domain: explicit constant
bits conjoined with the optional closed Boolean `assumption`, whose variables
are named `x.<wire>`. Unspecified bits, including borrowed ancillas, are free.
The procedure first requires a concrete legal input, so an empty domain cannot
produce a vacuous certificate.

A fixed dictionary consists of distinct square-free monomial masks on actual
cut wires. Bit `i` of a mask names wire `i`; mask zero is the constant monomial
one. With no explicit dictionary, all monomials of degree at most two are used.
Masks are canonicalized by `(degree, mask)` before constructing coefficient
vectors. The dictionary cap is checked before combinatorial generation.

For a dictionary of length $N$, let $\phi(F(x))\in\mathbb F_2^N$ be its feature
row. The complete result returns a basis of exactly

$$
\{a\in\mathbb F_2^N:\ \forall x,\ P(x)\Rightarrow
a\cdot\phi(F(x))=0\}.
$$

It says nothing about relations outside the selected dictionary. In particular,
degree two is a search-space restriction, not an assertion that every useful
invariant is quadratic.

### Counterexample-guided discovery

1. An exact SAT query finds one original input satisfying `P`.
2. Execute that input concretely and add its feature row to the sample matrix.
3. Compute a basis `a_j` of the sample matrix's nullspace.
4. Query the exact prefix transition relation together with
   $P(x)\land\bigvee_j(a_j\cdot\phi(F(x))=1)$.
5. SAT yields a legal original-input counterexample. Replay it through
   `Circuit.run`, require an actual violation, and add its feature row.
6. UNSAT proves every candidate relation on the entire domain. If the nullspace
   is empty, there is no nonzero candidate to check.

Every counterexample strictly increases sample rank. Consequently discovery
needs at most $N-\operatorname{rank}(S_0)$ refinements. This bounds refinements,
not the solver's running time.

For completeness, every true relation annihilates every sampled reachable row,
so it lies in the final nullspace. The final UNSAT query proves the converse.
The sample rows and nullspace therefore identify the complete invariant space
within the fixed dictionary.

### What replay proves

A successful receipt includes frozen source/domain/dictionary identities, a
list of legal original-input witnesses, and the canonical nullspace basis.
Replay accepts a separately supplied prefix/domain and then:

- checks exact source, contract and dictionary identity, including strict JSON
  scalar types;
- concretely re-executes the original-input witnesses;
- reconstructs their rank and requires the exact canonical nullspace claimed;
- runs a fresh SAT query for any relation violation.

Completeness is always relative to the dictionary, and every dictionary has a
complete basis: a receipt over a trivial dictionary such as `(1, 2)` replays as
`complete` with no relations. Pass `dictionary=` to `replay_cut_invariants`
when you rely on a particular dictionary; a receipt over any other dictionary
is then refused. The informational fields (`reason`, counters, `seconds`,
`engine`) are type-checked but not reverified.

Deleting a necessary basis vector fails the completeness check. A plausible
nullspace from too few samples is rejected if any candidate is false. Invalid
witnesses, modified source/domain, schema drift, and contradictory theorem or
authorization fields are refused.

This is a **SAT-backed replay receipt**, not a solver-independent UNSAT
certificate such as LRAT. The trusted components include the existing exact
Boolean encoder and interruptible solver. Concrete model replay independently
checks SAT witnesses but cannot by itself validate UNSAT answers.

## Inputs, status and resource behavior

`initial_constants` is an immutable tuple of unique `(wire, 0/1)` pairs. An
optional input `assumption` uses `symq.sat.assumptions`; unknown variables,
malformed nodes, gates outside `Circuit`, bool-valued indices and duplicate
dictionary masks are rejected. The assumption is copied into a bounded frozen
tree. Each source gate is reconstructed through its validated constructor;
mutating frozen gate internals cannot smuggle an unsupported instruction into
the checker, and the result owns its detached source snapshot. No arbitrary
callback is accepted as a domain predicate.

The result is one of:

| Outcome | Meaning | Invariants exposed |
| --- | --- | --- |
| `complete` | Nonempty domain; sound and complete basis in the dictionary | The proved basis, possibly empty |
| `empty_domain` | Initial domain is unsatisfiable | None |
| `inconclusive` | SAT unavailable, a deadline, or a structural cap | None |
| `not_proved` | Replay found a concrete violation of a claimed relation | None; the original-input witness is reported |

Missing invariants on an inconclusive run do not assert independence. A complete
empty basis, in contrast, proves there are no nonzero relations in the selected
dictionary. A failed receipt says nothing by itself about circuit equivalence.

`budget=None` uses a 30-second whole-call deadline. `Budget(max_seconds=...)`
sets another deadline; explicit `Budget()` removes the time deadline. Inherited
absolute deadlines remain in force. SAT uses the existing solver factory and
watchdog; unsupported noninterruptible solvers are not selected. Time checks
cover discovery, encoding, solver setup, model replay, rank work and cleanup.
Outside the solver this is a cooperative deadline, not process termination.

`InvariantLimits` bounds monomials, refinements, clauses, variables, prefix
gates and assumption nodes. A clause/variable cap is per query and does not
claim to bound process RSS. Generic symbolic `Budget.max_terms/max_nodes/
max_bytes` limits are refused rather than silently ignored. Invalid inputs
raise `TypeError`/`ValueError`; valid tasks that exceed resource caps return
`inconclusive`. No partially learned relation is promoted on failure.

`SubstitutionContract.initial_assumption` carries the same general
original-input Boolean assumption used by this learner. Forward it explicitly,
together with the same initial constants, when using the learned predicate:

```python
from symq.sat.assumptions import Eq, Var

prefix = Circuit(4).cx(0, 2)
initial = Eq(Var("x.1"), Var("x.2"))
learned = discover_cut_invariants(prefix, assumption=initial)
rechecked = replay_cut_invariants(
    prefix, learned.to_dict(), assumption=initial, dictionary=learned.dictionary,
)
contract = SubstitutionContract(
    initial_assumption=initial,
    cut_assumption=rechecked.cut_assumption(prefix),
)
source = Circuit(4).cx(0, 2).cx(2, 3)
replacement = Circuit(4).cx(0, 3).cx(1, 3)
assert check_substitution(source, (1, 2), replacement, contract=contract).equivalent
```

Here the input relation `x.1 = x.2` implies `u.2 = u.0 XOR u.1` at the cut.
The target remains arbitrary. Discovery, replay and substitution use the same
declared input domain; the substitution checker still re-proves its prefix
and local obligations. Omitting the original-input predicate does not weaken
that check: it must prove the relation on the larger domain and can correctly
refuse it. An empty combined domain never authorizes a vacuous rewrite.
These are explicit domain restrictions, not proofs that an external circuit
prepared the domain. No invariant result alone authorizes substitution.

## Reproduce the bounded qualification

```bash
python -m pytest -q tests/test_cut_invariants.py
python -m benchmarks.cut_invariants --output /tmp/cut-invariants.json --repetitions 3
```

The test suite includes independent dense elimination over all legal small
inputs, seeded X/CX/CCX/MCX prefixes, clean/dirty inputs, relational and empty
domains, certificate mutations, missing SAT, resource refusals, watchdog and
cleanup deadlines, and one actual contextual substitution.

The public relevance case is the first five CCX gates of the existing exposed
`benchmarks/corpus/kickmix/inc8.kmx` fixture. Its Git blob SHA-1 is
`0604339b577f47d5cc63de0a89088863e1e8a935`; the fixture's existing provenance and
license apply. The five remapped ancillas are explicitly zero initially.

| Public-prefix property | Value |
| --- | ---: |
| Boundary wires | 13 |
| Legal basis inputs | 256 |
| Monomials of degree at most two | 92 |
| Feature-row rank | 57 |
| Independent invariants | 35 |
| Counterexample refinements | 56 |
| Exact SAT queries, including domain and final UNSAT | 58 |
| Expected local carry-product relations recovered | 5 / 5 |

The benchmark also records clean and dirty products, a relational domain, a
seeded nonlinear prefix, an empty domain and an explicit refinement-cap stop.
It records every outcome, source identities, solver version, machine, timings
and cumulative process-peak RSS. Trials are serial, randomized by a fixed seed,
and reuse one process. The independent finite oracle is outside the measured
discovery and replay calls. Raw results belong in CI artifacts.

This is a bounded functional qualification on development cases, not an
untouched holdout, a comparison against external SOTA engines, or a demonstrated
general speedup. A useful next measurement is total discovery-plus-substitution
cost on larger independently selected compiler fragments.

## Prior work and next boundary

The sample/propose/prove pattern and polynomial-recovery problem have clear
precedents, including [Guess and Prove, CP 2025](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.CP.2025.14).
Relations for quantum phase optimization are studied in
[Amy and Lunderville, POPL 2025](https://arxiv.org/abs/2410.23493).
The contribution here is the scoped SymQ integration, exact prefix/domain
binding, finite-dictionary completeness and reproducible bounded qualification.
No worldwide novelty or quantum-channel theorem is claimed.
