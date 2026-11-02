# Program phase differences bound to a prefix image

`symq.labs.phase_delta_binding` is an opt-in research module built on
[phase quotient certificates](phase-quotient.md). Where `check_prefix_phase`
proves that a **supplied** phase polynomial is constant on a prefix image, this
module extracts that polynomial from two actual programs, proves their outputs
agree on the same image, and only then reuses the unchanged certificate check.
It has no API promise.

## Exact theorem

Let $F$ be a reversible X/CX/CCX/MCX prefix on $n$ wires. Its input contract
fixes distinct wires to zero or one and leaves every other input arbitrary,
including borrowed ancillas; this defines a nonempty basis support $D$. Let
$L$ and $R$ be `DyadicPhaseProgram` objects on the same $n$ wires, with moduli
$2^{k_L}$ and $2^{k_R}$. Each acts on a basis state $|w\rangle$ as

$$
L|w\rangle = e^{2\pi i\,\varphi_L(w)/2^{k_L}}\,|\pi_L(w)\rangle ,
\qquad
R|w\rangle = e^{2\pi i\,\varphi_R(w)/2^{k_R}}\,|\pi_R(w)\rangle .
$$

**Variable convention.** Every polynomial in this module, like the
invariants of a phase quotient certificate, is over the *cut wires*
$w=F(x)$, which are exactly the program inputs. The prefix input $x$ appears
only in obligations composed through $F$ and in witnesses.

A `proved` result of `check_program_phase_difference` establishes, with
$k=\max(k_L,k_R)$ and the certificate's constant $c$,

$$
\forall x\in D:\quad L\,F|x\rangle = e^{2\pi i\,c/2^k}\,R\,F|x\rangle ,
$$

and therefore the same identity on the coherent span of $D$. It is the
conjunction of three exact obligations:

1. **Outputs on the image.** For every output wire $i$, the Boolean ANF
   $\pi_{L,i}(w)\oplus\pi_{R,i}(w)$ is either identically zero (recorded as
   `output_scope = "all_cut_inputs"`) or becomes zero after exact substitution
   of the prefix state ANFs $w=F(x)$ with the fixed inputs inserted
   (`output_scope = "prefix_image"`). Outputs are therefore proved equal on
   $F(D)$, never sampled. A nonzero composition yields a legal input $x$ that
   is replayed by scalar execution of the prefix and both programs.
2. **Phase extraction.** Both phases come from the exact symbolic execution of
   `symq.labs.dyadic_phase` (with its exact parity lift). Each is scaled to
   $2^k$ by $2^{k-k_L}$ or $2^{k-k_R}$ and
   $\delta=\varphi_L 2^{k-k_L}-\varphi_R 2^{k-k_R}\bmod 2^k$ is put in canonical
   form: multilinear, coefficients in $[1,2^k)$, masks sorted. Negative angles
   and full turns reduce to these canonical coefficients. The certificate's
   `k` and `delta` must be **equal** to the extracted ones; a mismatch is
   `not_proved` with `obligation = "phase_difference"`. A certificate is never
   silently corrected or replaced.
3. **Constancy.** `phase_quotient.check_prefix_phase` is called unchanged on the
   same frozen prefix, domain and certificate: it verifies
   $\delta-c=\sum_j q_j\widetilde b_j$ and proves every $b_j(F(x))=0$ on $D$.

Together, for $x\in D$ and $w=F(x)$: $\pi_L(w)=\pi_R(w)$ and
$\varphi_L(w)2^{k-k_L}-\varphi_R(w)2^{k-k_R}\equiv c$, which is the identity
above. If `expected_constant` is given, the proved $c$ must also equal it.

**What it does not claim.** A nonzero $c$ is a relative phase under quantum
control, so the result does not authorize a controlled substitution, a
replacement inside a larger coherent context, a measurement, reset or
output tracing. Outside $F(D)$ nothing is claimed. `not_proved` means an
obligation was not established, for example a stale or insufficient
certificate; it is not a proof that the programs differ.

## Example

On the image of `ccx(0, 1, 2)` with `z = 0` initially, $z=ab$, so `Z` on $z$
equals `CZ` on $a,b$. The right program also carries a global $1/8$ turn.

```python
from fractions import Fraction

from symq import Circuit
from symq.anf import ANF
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_delta_binding import (
    check_program_phase_difference,
    extract_phase_difference,
    replay_program_phase_difference,
)
from symq.labs.phase_quotient import PhaseQuotientCertificate, check_prefix_phase
from symq.resources import Budget

prefix = Circuit(3).ccx(0, 1, 2)
left = DyadicPhaseProgram(3, k=3).z(2)
right = (DyadicPhaseProgram(3, k=4).cz(0, 1)
         .x(0).phase(0, Fraction(1, 8)).x(0).phase(0, Fraction(-15, 8)))

# Extraction is exact and canonical; it says nothing about outputs.
found = extract_phase_difference(left, right)
assert found.k == 4 and found.delta == ((0, 14), (3, 8), (4, 8))

certificate = PhaseQuotientCertificate(
    width=3, k=4, delta=found.delta,
    invariants=(ANF(frozenset({3, 4})),),  # z XOR ab = 0 at the cut
    multipliers=(((0, 8),),),              # 8*lift(z XOR ab) = 8z + 8ab mod 16
    constant=14,
)
budget = Budget(max_terms=10_000, max_seconds=2)
proof = check_program_phase_difference(
    prefix, left, right, certificate,
    initial_constants=((2, 0),), expected_constant=14, budget=budget,
)
assert proof.outcome == "proved" and proof.constant == 14  # exp(2*pi*i*14/16)
assert proof.to_dict()["controlled_use_authorized"] is False

# Replay recomputes everything; the consumer pins the constant it relies on.
replayed = replay_program_phase_difference(
    prefix, left, right, certificate, proof.to_dict(),
    initial_constants=((2, 0),), expected_constant=14, budget=budget,
)
assert replayed == proof

# A certificate written for another right program is refused, even though
# check_prefix_phase alone would accept it.
stale = PhaseQuotientCertificate(3, 4, ((3, 8), (4, 8)), certificate.invariants,
                                 certificate.multipliers)
assert check_prefix_phase(prefix, stale, initial_constants=((2, 0),)).outcome == "proved"
refused = check_program_phase_difference(prefix, left, DyadicPhaseProgram(3).cz(0, 1).t(0),
                                         stale, initial_constants=((2, 0),))
assert refused.outcome == "not_proved" and refused.obligation == "phase_difference"

# A resource bound gives "inconclusive", which carries no replayable claim.
tight = check_program_phase_difference(prefix, left, right, certificate,
                                       initial_constants=((2, 0),),
                                       budget=Budget(max_terms=2))
assert tight.outcome == "inconclusive"
```

## Trust, identity and failure behavior

- Inputs are detached first. The prefix, both programs and every gate are
  rebuilt from exact `int`, `str`, `tuple`, `int`/`Fraction` data and
  revalidated; subclasses (including `bool` for integers and masquerading
  string names), forged gate attributes, angles outside $2^{-k}\mathbb Z$,
  unequal widths and `k` outside $[1,64]$ are refused with `TypeError`,
  `ValueError` or `UnsupportedOperation`. Later mutation of the caller's objects
  cannot affect a running check. Certificates use the `phase_quotient` validator.
- Outcomes are `proved`, `not_proved` (with `obligation` one of `outputs`,
  `phase_difference`, `prefix_phase` or `expected_constant`) and
  `inconclusive` (`obligation = "resources"`). Witnesses are legal prefix
  inputs, replayed through the frozen prefix and both programs.
- The receipt (`ProgramPhaseResult.to_dict()`) binds SHA-256 identities of the
  prefix gate stream, each program's gate stream (names, wires, exact rational
  angles and `k`), the certificate and the extracted delta, together with the
  initial constants, `k`, the constant and the pinned `expected_constant`.
  Hashes identify content; they are not signatures.
- `replay_program_phase_difference` treats the receipt as untrusted data: a
  closed field set with exact JSON types, then a complete recomputation and a
  canonical comparison. A changed prefix, program, domain, certificate, pin or
  field is a mismatch, even when the change is semantically harmless. An
  `inconclusive` receipt is refused, and resource exhaustion during replay
  raises `ResourceLimitExceeded` rather than reporting a mismatch.
- `Budget.max_terms` and deadlines bound the whole call, including snapshots,
  symbolic execution, composition and the inner certificate check.
  `max_nodes` and `max_bytes` are refused. An inconclusive result reports the
  stage reached and only the identities computed before the limit.

The trusted base is `phase_quotient` (prefix state, substitution, certificate
check), the symbolic executor and lift of `dyadic_phase`, and this module's
scaling and comparison. The tests compare it with an independent scalar oracle
(`tests/testkit/phase_delta_oracle.py`) that executes the prefix and both
programs on every legal input with exact `Fraction` turns, and never imports
the extraction code. This reduces implementation risk; it is not a formal proof.

## Scope and limits

Widths 1–256 and $1\leq k\leq 64$ are implementation limits. Only the
`DyadicPhaseProgram` grammar is accepted: X/CX/CCX/MCX and diagonal
T/S/Z/CZ/CCZ/phase gates; Hadamards, measurements and resets are not. Both
programs share one wire layout with the prefix: relabelled wires or reordered
ancillas are different programs and are refused unless they really agree on
the image. Certificates are supplied, not discovered; extraction may grow
exponentially with the number of nonlinear gates and is bounded by `max_terms`.

## Qualification and reproduction

```bash
python -m pytest tests/test_phase_delta_binding.py \
  tests/test_phase_delta_binding_qualification.py
python -m benchmarks.phase_delta_binding --repetitions 3 \
  --output evidence/phase-delta-binding.json
```

The harness authenticates the public `inc8.kmx` prefix through
`benchmarks.phase_quotient.public_case` (Apache-2.0, pinned source revision).
Two constructed programs differ by the global turn $14/16$ on its 256 legal
inputs: $-1/2$ turn on each Toffoli target at $k=4$ against CZ on its
controls at $k=3$ with a global T-gadget. The certificate delta is written from
this construction, not by the extractor. Adverse cases use a stale delta, a
certificate at $\min(k)$, different outputs, a shortened prefix, an arbitrary
ancilla and an exhausted budget. Every trial records outcome, reason, receipt,
a fresh replay and the exhaustive oracle; a proved constant must equal the
oracle's global turn, and each case's declared truth is checked against the
oracle. The JSON is always written, and any failed trial gives a nonzero exit
while remaining visible beside later successes. The fixture is previously
explored development data, not a holdout; no speedup or scaling claim follows.
