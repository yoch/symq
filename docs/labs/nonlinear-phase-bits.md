# Aggregate nonlinear phase certificates by Boolean bit planes

Research follow-up to #148, stacked on #160 only for its bounded Boolean-DAG/SAT
algebra. The source semantics come from the existing audited `affine_phase`
helpers; its affine checker and theorem are unchanged. No maintained API promotion.

## Source-bound theorem

Given two real dyadic monomial-unitary sources L,R, an actual strict sign/HMR
dephaser D and an explicit affine coherent support, first freeze and validate all
sources and require D to restore the declared data and zero ancillas. Extract its
**effective** signature h, including conditional phase feedback. Equal raw
measurement counts or supplied signature guesses are not accepted as authority.

Check output equality of L/R on the support separately. Extract delta=phi_L-phi_R
at k=max(k_L,k_R). A supplied immutable certificate gives k Boolean ANFs b_j over
the signature coordinates, and asks for

```math
\delta(x)=\sum_{j=0}^{k-1}2^j[b_j(h(x))]\pmod {2^k}.
```

If all identities hold, delta is constant on every surviving coherence fibre, so
(L tensor I) after D and (R tensor I) after D have equal full quantum channels on
the declared support. Records are forgotten, every quantum output is retained.
No external support preparation or coherently controlled substitution is proved.

## Checking the aggregate without integer-polynomial expansion

Accumulate all weighted Boolean source phase predicates into a k-bit DAG with an
exact ripple adder. For each bit, XOR it with the substituted b_j(h) and ask SAT
for a counterexample. This retains carry propagation and cancellation between
predicates; no inversion of 2 modulo 2^k or integer multilinear lifting is used.
The 3840 locally executed scalar arithmetic comparisons cover k=1..8 and all
three-variable assignments on the generated test cohort. Full source and oracle
qualification is performed by the dedicated installed-package CI, not inferred
from these low-level arithmetic tests.

The motivating example is h=ab, p=a, q=a XOR ab. Neither predicate is constant on
the h=0 fibre, but 2[p]+2[q]=2[h] mod4. It is a test against the incomplete discovery
strategy that insists on factoring every predicate separately, not a new theorem
about Boolean arithmetic.

## Result contract and evidence boundary

- `proved`: all source/output/signature/bit obligations hold for the supplied candidate.
- `not_proved`: a source obligation or the supplied candidate fails. A wrong candidate
  does **not** establish channel inequivalence; the tests include equal channels with
  a deliberately false candidate.
- `inconclusive`: shared deadline, term, graph or clause cap exhausted.
- `unsupported`: required SAT backend unavailable. Invalid closed inputs raise.

Source, support, extracted signature, delta and candidate identities are included
in the result. A SAT model is checked by the independent DAG evaluator and then
against scalar execution of the real frozen dyadic sources. UNSAT trusts the
encoder/solver: no LRAT proof, portable replay receipt, or automatic discovery is
claimed. Existing source extraction still uses Boolean ANFs and can grow; moving
it to a circuit representation is a separate optimization.

The development campaign enumerates all 256 functions of h=(ab,bc) into Z/4,
compares full retained channels with the independent Kraus/cyclotomic oracle,
and adds phase/output/feedback/candidate/source mutations. The workflow records
commit/tree/source hashes and refuses partial successes. These are constructed
examples, not a holdout or a general scaling demonstration.

```bash
python -m pytest -q tests/test_nonlinear_phase_bits.py
python -m benchmarks.nonlinear_phase_bits --output evidence/nonlinear-phase-bits.json
```

`tests/test_nonlinear_phase_independent.py` (audit #164) adds an independent cohort:
random strict dephasers with 1-3 HMR and feedback on the same and earlier outcomes, random
affine supports, mixed precision k=1..4, negative angles and full turns, shared permutations
and output mutations. Certificates come from a separate brute-force simulation of the
effective signature and delta; truth is the exact Kraus/cyclotomic oracle. Every equal
channel is proved with its true certificate, no different channel is proved, and a flipped
certificate bit on equal channels is reported as `candidate_phase_bit`, never as a
difference. The audit ran it on 2,000 cases (910 equal channels) with no disagreement.

Next research: discover small b_j using counterexample-guided Boolean dependence,
compare with direct R(h) and per-predicate certificates, and extract independently
checkable proof logs. A candidate search failure must remain distinct from a
counterexample to existence of any such certificate.
