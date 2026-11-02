# Functional certificates for full sign/HMR channels

`symq.labs.channel_certificate` is an opt-in research module. It checks a
sufficient, source-bound certificate of **full quantum-channel equality** on
the strict `PhaseProgram` grammar. It is not a default backend, a rewrite
authorization, or a general hybrid-circuit decision procedure.

## Contract

- Both programs have the same number and ordering of free data inputs and
  zero-initialized ancillas. The full Boolean input cube is used; arbitrary
  coherent states and entangled reference systems are covered by channel
  equality on all matrix units.
- Every quantum output is retained, including final ancilla values. Every
  measurement outcome is forgotten. Visible classical records, traced
  outputs, arbitrary input assumptions and dirty input ancillas are excluded.
- Operations are exactly those validated by `PhaseProgram`: reversible
  `mcx`, sign phases `mcz`, X-basis measurement followed by reset `hmr`, and
  sign feedback `mcz_if` from an earlier outcome. No outcome-controlled value
  gates, general reset, H/S/T gates or non-real phases are added.
- The checker snapshots and validates actual programs, computes their sparse
  Boolean semantics, and checks all identities itself. A supplied hash or a
  supplied certificate object is not trusted as evidence.

The module does not authorize substituting a channel-equal block under a
coherent quantum control. For example, a global phase can become a relative
phase under such control. A surrounding rewrite requires its own contract.

## Why a one-copy certificate is enough

The supported grammar gives Kraus operators

$$
K_m|x\rangle=2^{-M/2}(-1)^{p(x)\oplus m\cdot g(x)}|f(x)\rangle.
$$

Thus, after forgetting outcomes,

$$
\mathcal E(|x\rangle\langle y|)
=\mathbf{1}_{g(x)=g(y)}(-1)^{p(x)\oplus p(y)}|f(x)\rangle\langle f(y)|.
$$

The formula does not claim uniform outcome probabilities for arbitrary
superpositions. It follows by summing the Kraus contributions on each matrix
unit. `f` includes every output wire and does not depend on outcomes.

Select some coordinates of the left signature, giving a function `h`. The
certificate supplies Boolean polynomials satisfying

$$
g_L=L(h),\qquad g_R=R(h),\qquad h=S(g_R),\qquad
p_L\oplus p_R=Q(h),\qquad f_L=f_R.
$$

Equality of left signatures implies equality of `h`, because `h` is a
selected subvector. Reconstruction `R` then implies equality of right
signatures. In the other direction, `S` followed by `L` proves the converse.
The two signatures therefore induce exactly the same fibres. The final
identity makes the relative sign constant on each retained coherence. This
proves equality of the channels on all matrix units.

All identities are checked as Boolean polynomials in one copy of the data
variables. No two-copy coherence kernel is materialized.

For instance, `(a,b,ab)` and `(a,b)` induce the same fibres. Linear dependence
of coordinates is sufficient but not necessary for redundancy. A relative
phase `ab` is invisible on these fibres; a phase on an unmeasured spectator
bit remains visible and is rejected.

## API and portable certificate data

```python
import json

from symq.labs.channel_certificate import discover_certificate, verify_certificate
from symq.phase import PhaseProgram

left = PhaseProgram(3, 1)
left.cx(0, 3)
left.hmr(3)
left.cx(1, 3)
left.hmr(3)

right = PhaseProgram(3, 1, list(left.ops))
right.ccx(0, 1, 3)
right.hmr(3)
right.cz(0, 1)

result = discover_certificate(left, right, degree=2)
assert result.equivalent
assert result.certificate is not None
document = json.loads(json.dumps(result.certificate.to_dict()))
assert verify_certificate(left, right, document).equivalent
```

The certificate schema is closed and versioned. Monomial masks are sorted,
unique nonnegative integers; mask zero denotes the constant monomial. Masks
refer to selected left features except in `signature_from_right`, where
they refer to right signature coordinates. Boolean values are rejected in
integer fields. Missing/unknown fields, omitted coordinates, out-of-frame
variables and stale source hashes cannot establish equivalence.
Program outcome indices also require the exact integer type: integer
subclasses with overridden comparisons cannot conceal an invalid event.

`ChannelCertificate` is an immutable data container, not an authenticated
proof token. Construction, serialization, loading or a previous receipt is
insufficient: use `verify_certificate` against the intended source programs.
Even a syntactically changed but semantically identical source requires
a new matching certificate.

### Outcomes

| Outcome | Meaning |
| --- | --- |
| `equivalent` | All source-bound identities were checked exactly. |
| `not_proved` | A certificate was rejected or no certificate was found in the chosen dictionary. This is **not** a channel-inequivalence verdict. |
| `inconclusive` | A resource cap or deadline prevented completion; no certificate is returned. |

Malformed or unsupported program inputs and invalid API settings raise an
explicit exception. Malformed certificate data returns `not_proved`.

## Discovery, resources and limits

Discovery greedily selects left event functions and constructs an exact
linear span of products of up to `degree` selected features. It seeks both
reconstructions and the phase function in that span. Direct right-coordinate
matches are tried before building a nonlinear inverse dictionary. The guessed
certificate then goes through fresh semantic interpretation and exact checks.

Failure of this bounded heuristic does not decide equivalence. A different
feature order, higher degree or different certificate may succeed. The
discovery algorithm and checker share sparse arithmetic and the program
interpreter; the implementation is not formally verified. Tests use a
separate integer/outcome Kraus interpreter as an independent bounded oracle.

The default whole-call budget is five seconds with 20,000 explicit monomials
per polynomial, including temporary products and elimination expressions.
`CertificateLimits` also caps widths, operations, events, dictionary terms,
certificate monomials and canonical certificate JSON bytes. The same deadline
covers source capture, discovery, fresh checking and release of semantic
scratch state before the final result is published.
Time checks are cooperative, not process preemption. The byte cap is not a
process-memory or RSS bound. Unsupported node/native-array byte budgets are
refused, including when inherited from an active verification session.

## Reproduction and relevance screen

```bash
python -m pytest -q tests/test_channel_certificate.py tests/test_channel_criterion.py
python -m benchmarks.channel_certificate --output /tmp/channel-certificates.json
```

The bounded benchmark records source and program hashes, runtime information,
budgets, full-call wall times, outcomes and the reasons of both the search and
the fresh check. Public fixtures are parsed from the exact bytes that were
authenticated. An exception in any trial, or during setup, is recorded in the
JSON, which is always written, and the run exits 1. It is a development reproduction,
not an untouched holdout or a comparison establishing a speed advantage.
Raw results belong in CI artifacts, not in the repository.

The existing public `inc8.kmx` and Qualtran multiplication/uncomputation
fixtures for degrees one and two have **empty corrected final signatures**.
They exercise actual imported circuits, exact equality and rejection after
removing feedback, but do not establish a natural workload benefiting from
nonlinear signature compression. Synthetic redundant/relabelled examples
demonstrate the specific structure only. A larger qualification must compare
the total cost with native SymQ and competitive variable orders, and retain
negative cases and all inconclusive trials.

## Prior art and contribution boundary

The original SymQ channel checker already uses equality of signature fibres
and constancy of the relative phase on those fibres. This module changes the
certificate representation, not that theorem. Functional dependence
`f = h(g)` and SAT/interpolation-based discovery are established techniques:
[Lee, Jiang, Huang and Mishchenko, ICCAD 2007](https://people.eecs.berkeley.edu/~alanmi/publications/2007/iccad07_fd.pdf).
Broader recent hybrid verification includes
[Irene](https://arxiv.org/abs/2609.36065) and
[Hybrid Path-Sums](https://arxiv.org/abs/2604.24578).
No worldwide novelty or general verifier-performance claim is made.
