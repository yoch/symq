# Phase certificates under proven prefix invariants

`symq.labs.phase_quotient` is an opt-in research module. It checks explicit
dyadic phase identities and can prove their Boolean assumptions on the image
of a reversible circuit prefix. It does not discover multipliers or expose a
stable API.

The result is a statement about the **supplied phase polynomial**. It does
not compare unspecified circuits, prove their output permutations or ancilla
restoration, or authorize a rewrite. A caller connecting the phase polynomial
to a pair of programs must separately establish that connection and the other
obligations. A nonzero constant phase can become relative under quantum
control; this API does not authorize a controlled replacement.

## Exact theorem

Let the prefix be a reversible X/CX/CCX/MCX circuit $F$ on $n$ wires. Its input
contract fixes distinct wires to zero or one and leaves every other input
arbitrary, including borrowed ancillas. This defines a nonempty computational
basis support $D$ and its coherent span.

An invariant $b_j(w)$ is a Boolean ANF required to equal zero at the cut. Its
exact lift $\widetilde b_j$ is its zero-or-one valued polynomial in

$$
R_{2^k}=(\mathbb Z/2^k\mathbb Z)[w_0,\ldots,w_{n-1}]
       /\langle w_i^2-w_i\rangle.
$$

The certificate supplies multipliers $q_j$, a phase polynomial $\delta$, and
a constant $c$. The checker verifies the polynomial identity

$$
\delta-c=\sum_j q_j\widetilde b_j
$$

and the prefix wrapper separately verifies, by exact ANF substitution,

$$
\forall x\in D,\quad b_j(F(x))=0.
$$

Together these establish $\delta(F(x))=c\pmod {2^k}$ for every $x\in D$.
The corresponding diagonal phase is therefore a scalar on the coherent span
of the reachable basis states. No statistical sampling is used by the proof.

The algebraic identity is sufficient; failure of a particular certificate
does not imply that the phase is nonconstant on the prefix image.

### Why the Boolean lift matters

Suppose $z=ab$ at the cut. The Boolean relation is $b_1=z\oplus ab$.
Modulo eight its exact lift is

$$
\widetilde b_1=z+ab-2abz,
\qquad
z-ab=(1-2ab)\widetilde b_1.
$$

Reusing $z+ab$ as a zero relation modulo eight would be wrong: it equals two
at $a=b=z=1$. The implementation reuses the existing exact `lift_anf` from
`symq.labs.dyadic_phase`; it does not perform division or Gaussian elimination
over a ring containing noninvertible even elements.

## Example

Monomials are bit masks over the cut wires. Coefficients are canonical modulo
$2^k$, so the example stores $-1$ as seven and $-2$ as six.

```python
from symq import Circuit
from symq.anf import ANF
from symq.labs.phase_quotient import (
    PhaseQuotientCertificate,
    certificate_from_dict,
    certificate_to_dict,
    check_prefix_phase,
    replay_prefix_phase,
    verify_phase_identity,
)
from symq.resources import Budget

# Wires 0,1,2 are a,b,z. Initially z=0; the prefix computes z=ab.
prefix = Circuit(3).ccx(0, 1, 2)
certificate = PhaseQuotientCertificate(
    width=3,
    k=3,
    delta=((3, 7), (4, 1)),              # z - ab
    invariants=(ANF(frozenset({3, 4})),), # z XOR ab = 0
    multipliers=(((0, 1), (3, 6)),),      # 1 - 2ab
)

# This establishes only the conditional ring identity.
assert verify_phase_identity(certificate)

budget = Budget(max_terms=10_000, max_seconds=2)
proof = check_prefix_phase(
    prefix, certificate, budget, initial_constants=((2, 0),)
)
assert proof.outcome == "proved"
assert proof.constant == 0
assert proof.to_dict()["candidate_authorized"] is False

# JSON is data; parsing is not proof. Replay recomputes every obligation.
encoded = certificate_to_dict(certificate)
decoded = certificate_from_dict(encoded)
replayed = replay_prefix_phase(
    prefix, decoded, proof.to_dict(), budget, initial_constants=((2, 0),)
)
assert replayed == proof

# Omitting z=0 keeps it arbitrary. The relation then fails on a replayed witness.
dirty = check_prefix_phase(prefix, certificate, budget)
assert dirty.outcome == "not_proved"
assert dirty.violating_invariant == 0
assert dirty.witness is not None
```

## Trust, identity and failure behavior

- `PhaseQuotientCertificate` is immutable input data. It carries no trusted
  success flag. All public verification and serialization entry points
  validate its integer types, dimensions, masks and canonical coefficients.
- `verify_phase_identity` returns a Boolean for the ring identity only. It
  does not establish the assumptions or their consistency.
- `check_prefix_phase` snapshots and revalidates the prefix, proves every
  declared invariant and returns `proved` or `not_proved`. Invariant failure
  includes a legal original input replayed through the frozen circuit.
  Identity failure carries no invented inequivalence witness.
- A successful result identifies the prefix gate stream and certificate by
  SHA-256 and records the exact initial constants. These hashes identify
  content; they are not cryptographic signatures or proofs by themselves.
- `replay_prefix_phase` recomputes the complete result and compares the
  untrusted serialized receipt, including its theorem and provenance.
  Changed source, contract or receipt produces a mismatch even if the changed
  circuit happens to compute the same function. JSON Booleans are not accepted
  as integer versions, masks or coefficients.
- Invalid input raises `TypeError` or `ValueError`. Unsupported gates are
  refused. Exhausting a resource bound raises `ResourceLimitExceeded`; no
  partial certificate is returned and the exception is not a negative verdict.

The wrapper proves invariants with sparse Boolean substitution. Its trusted
implementation includes the reversible gate interpreter, sparse arithmetic
and the existing dyadic lift/multiplication routines. The independent scalar
oracles in the tests reduce implementation risk but are not a formal proof of
the checker. General SAT proof certificates are outside this module.

## Scope and resources

The first version supports widths 1–256 and exponents $1\leq k\leq64$.
These are explicit implementation limits, not mathematical limits. General
relational input assumptions, H/measurement/reset prefixes, output tracing,
measurement records and controlled substitutions are not accepted.

Distinct initial constants define a nonempty support by construction. Repeated
or conflicting wire assignments are refused. An algebraically valid identity
with the impossible assumption `1=0` cannot pass the prefix wrapper.

`Budget.max_terms` bounds the aggregate certificate term records, each
intermediate explicit polynomial and the retained prefix state terms. No term
is truncated. `Budget.max_seconds` and inherited absolute deadlines cover the
whole call, including parsing, lifting, prefix propagation, witnesses and replay.
Time checks are cooperative; they are not a subprocess wall-clock kill.
`max_nodes` and `max_bytes` are rejected because this sparse implementation does
not implement those resource measurements. Omitted budgets mean no caller term
or time limit, so resource-sensitive callers should pass an explicit budget.

## Qualification and reproduction

```bash
python -m pytest tests/test_phase_quotient.py tests/test_phase8_research.py
python -m benchmarks.phase_quotient --repetitions 3 \
  --output evidence/phase-quotient.json
```

The benchmark authenticates the existing public `inc8.kmx` against its corpus
manifest, retains its source revision and Apache-2.0 license, and extracts the
first five CCX gates. It checks a sum of five phase identities on all 256 legal
basis inputs. Adverse cases remove the last CCX, leave its ancilla arbitrary,
or mutate the supplied phase. Complete proof replay is checked for each case.

Certificates in this qualification are constructed explicitly. The fixture is
previously explored development data, not an untouched holdout. The JSON records
the imported source identity, harness hash, environment, all full-call timings,
Python allocation peaks, repetitions, failures and scalar-oracle outcomes.
`tracemalloc` does not measure total process RSS. No comparative speedup or
large-circuit scaling claim follows from this bounded qualification. Publish
the result as a CI artifact, without committing machine-dependent run JSON.

Tests additionally cover every two-variable Boolean ANF relation with every
Boolean coefficient vector embedded in $\mathbb Z/8$, seeded multirelation
certificates with independently interpolated truth tables, corrupted certificates,
random reversible prefixes, dirty inputs, strict JSON, source/contract tampering,
empty-domain attempts and intermediate lift limits.

## Relationship to prior work and next steps

Relational phase analysis is established work; see Amy and Lunderville,
[*Linear and non-linear relational analyses for Quantum Program Optimization*](https://arxiv.org/abs/2410.23493),
POPL 2025. The adaptation here is an explicit, source-bound certificate interface
for SymQ's narrow cut contract, with a separate conditional algebra checker.

The next research step is discovery of small multipliers and connection to
actual source/replacement phase differences, together with separate output and
restoration proofs. Discovery can be expensive even when checking a supplied
certificate is easy. Integration with invariant inference and broader input
contracts should preserve the independent obligations and explicit refusal
behavior above.
