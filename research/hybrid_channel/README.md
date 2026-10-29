# Small exact hybrid CPTP channel oracle (research)

This standalone **exponential-size reference** extends the *tested* hybrid
semantics in SymQ research. It has **no dependency on any external project**,
does not alter existing `Circuit`, `PhaseProgram`, QASM or verification defaults,
and is **not** a scalable solver or a generic arbitrary-H quantum simulator.

## Closed accepted fragment

`research/hybrid_channel/oracle.py` defines a validated `HybridProgram` with:

- Quantum basis permutations X, CX, CCX, MCX, SWAP, CSWAP.
- Sign phases Z, CZ, CCZ and NEG (global sign), optionally conditioned on a
  previously stored measured-outcome bit or its negation.
- Unconditional `hmr(q,"bN")`: **X-basis measure followed by reset to |0>**.
- Unconditional `measure_z(q,"bN")`: destructive projection in the **Z basis**,
  with the post-measurement qubit left in its corresponding eigenstate.
- Unconditional `reset(q)` on an **arbitrary, including entangled** qubit,
  modeled as the genuine CPTP map (trace out q, prepare |0>), not a Boolean
  assignment or a reversible operation.
- Measurement-controlled **value gates** X/CX/CCX/MCX and SWAP/CSWAP, plus
  conditional sign gates.
- Mutable classical slot operations `store`, `invert` and `oxor`.
  Every measurement is a distinct event even if the slot name is reused.

Any unknown/unsupported quantum gate, invalid wire, future/uninitialized
condition, aliased operand, guarded measurement/reset or malformed classical
operation is refused. This research API is typed Python; it is **not** an
OpenQASM/large-circuit text importer.

## Exact channel and critical coherence counterexample

For a quantum state with data input and **initial ancillas |0>**, the oracle
computes `E(|x><y|)` for every pair of data basis inputs. Since the matrix
units are a linear basis of the input density operators, this is a complete
channel equality test (on the declared input subspace), **not** a test of
diagonal classical truth tables.

A genuine standalone reset has two Kraus operators

$$
K_0=|0\rangle\langle 0|,\qquad K_1=|0\rangle\langle 1|
$$

acting on the reset qubit; therefore

$$
\mathcal R(\rho)
=\sum_{b=0}^{1}K_b\rho K_b^{\dagger}.
$$

X-basis HMR has the two *distinct, recorded-outcome* operators

$$
K_m=|0\rangle\langle \chi_m|,
\qquad |\chi_m\rangle
=\frac{|0\rangle+(-1)^m|1\rangle}{\sqrt 2}.
$$

For an entangling CX from coherent data to a zero ancilla, then reset of the
ancilla, the reduced data coherence `|0><1|` is destroyed. The identity
program preserves it. Both circuits give the **same classical data output
on the two computational basis inputs**: comparing only Boolean outputs
would be unsound as a quantum-channel theorem.

Unlike the existing restricted HMR factorization `F(x)` and
`phi0(x) XOR sum_j m_j*g_j(x)`, an X/CX controlled by a measurement
may give an output `F(x,m)` depending on outcomes; arbitrary classical
guards may produce nonaffine outcome phases. This oracle handles such
cases by **explicit Kraus branches**, not by reusing a false invariant.

Full output channels and **ancillas-traced-out** output channels are
separate results, selected explicitly via `trace_ancillas`. A full
channel verdict never silently ignores garbage or borrowed ancillas.

## Limits and evidence

- Maximum total width 6, maximum measurement events 8 and branch cap 256
  by default. Exceeding them raises a resource error; no approximate PASS.
- Budget's `max_terms` bounds explicit stored matrix entries,
  `max_seconds` is one cooperative whole-call deadline, and `max_nodes`
  is explicitly rejected as inapplicable. This is **not** a hard process
  kill or an independently checked proof certificate.
- The suite compares an independently written **ket-vector Kraus reference**
  with the sparse density-matrix implementation on deterministic random
  hybrid circuits. It also cross-checks the earlier independent exact
  channel oracle for the common narrower HMR fragment.
- Mandatory mutants: missing conditional CZ on temporary-AND erasure;
  entangled unknown reset vs identity; wrong classical XOR parity;
  conditional X after HMR; measurement-slot reuse; invalid operations.
- No benchmark speedup is claimed, no finite input-domain shortcut is
  interpreted as a global channel theorem, and no full arbitrary quantum
  circuit is accepted.

Run the single research suite:

```bash
python -m pytest -q tests/test_hybrid_channel_research.py
```

**Next milestone:** lift the exact tested semantics into an independently
validated typed hybrid IR with explicit classical scopes, better budget
accounting, observable instruments and sound symbolic channel proof rules.
Promotion into a public facade requires a separate audited PR.


## Classical-output instruments (additional opt-in theorem)

`same_channel` intentionally **forgets** all classical measurement records.
A program that measures Z and stores the outcome can have the same quantum
channel as an otherwise identical program overwriting that slot with zero;
they do **not** implement the same observed classical/quantum instrument.

The separate `same_instrument(left, right, observed_slots=("b0",))` compares
the exact conditioned quantum outputs for **each selected final classical
record** and for **all** coherent input pairs `|x><y|`. Unlike event
identities, observed mutable storage is versioned by its final value.
The set of observed slots is required and nonempty; uninitialized or repeated
slot names are rejected. Partial classical observation is a deliberate
coarse-graining: unobserved slots/events are summed out. Ancilla trace is
still a separate explicit theorem parameter.

The independent ket-vector Kraus oracle groups branches by the same observed
records in regression tests, including reused slots, conditional-X feedback
and a wrong-classical-output mutant. This remains a **tiny exponential
research oracle**: no import, QASM support, default dispatch, scalable
hybrid proof or independently checkable formal certificate is claimed.
