# Exact forgetful-map semantics: research regression kit

This is a **standalone, public, SHA-pinned review fixture** for issue #100.
It lives beside the already merged bounded hybrid-channel oracle and the
public GF(4)/GF(8) qualification kit, without importing anything from a
private repo or from an external auditor's unpublished branch.

The regression suite:
\`python -m pytest -q tests/test_forgetful_channel_maps_research.py\`

## Why a theorem label is insufficient

The implication "a full channel is equal, therefore its partial trace is
equal" applies to **EQUIVALENT**, with the same input domain and preparation,
the same complete quantum outputs, and an explicitly declared trace set.
It does **not** turn a difference witness on a retained ancilla into a
difference witness on the reduced output.

The suite uses the exact counterexample L=identity and R=X(ancilla),
with the ancilla initially |0>. On all four coherent input matrix units,
their full data+ancilla channels differ while their reduced data channels
agree. The partial trace is independently computed as:

  Tr_A M[(i,a),(j,b)] = sum_{a=b} M[(i,a),(j,a)]

For measured classical outputs, the unconditional CP channel is the sum
of all conditioned instrument maps, **including every declared record**.
The suite reconstructs this sum explicitly, for every |x><y|, and
compares it with the independently exposed unconditional-channel oracle.

A separate counterexample overwrites a final classical slot so that
\`DIFFERENT(INSTRUMENT)\` is true while \`EQUIVALENT(CHANNEL)\` is true.
This forbids blindly forwarding DIFFERENT across a forgetful observation.

The fourth test verifies that a conditional CZ cancels the HMR outcome
sign in a nonlinear reversible AND/MAC gadget. The **outcome-summed**
instrument equals the *full and traced* unitary reference on all 64
data-input coherence pairs; omitting the correction does not.

## Required properties for a future typed research adapter

- Do not introduce a total strength ranking of theorem classes.
- Only infer \`EQUIVALENT\` along a specifically justified quantum-output
  partial trace or classical-outcome forgetting, never automatically
  \`DIFFERENT\` or any inconclusive/error verdict.
- Preserve program digests, coherent input domain, ancilla preparation,
  the exact retained/traced output wires and classical observed slots.
- Actually construct/validate the conditioned-map sum when claiming
  instrument-to-channel semantic conversion. The bare enum alone is
  neither a Kraus sum nor an independently checkable proof.
- Unexpected internal exceptions should carry diagnostic information;
  they must not be silently mapped to \`DIFFERENT\` or ordinary
  resource-related \`INCONCLUSIVE\`.
- A result of "equal on a selected finite *basis-input* domain" is
  not automatically a theorem about all off-diagonal coherences.

**Limitations:** this is a correctness regression for the exponential,
bounded reference oracle. It is not a fast channel solver, does not use
the QCEC classical corpus and does not establish an HMR speedup.

An external agent can fetch this PR with ordinary GitHub access. No
archive or private repository permission is necessary. Keep this PR
unmerged pending independent review.


## Additional high-priority frame counterexample (draft proof adapter #102)

A **reduced** instrument may be equal without equal **full** quantum
channels. Construct one data qubit and one initially clean ancilla; both
programs output a constant observed classical slot b0=0. One leaves
the ancilla at |0>, the other applies X to it. They have:

- same_instrument with trace_ancillas=True: **equal**
- same_instrument with trace_ancillas=False: **different**
- same_channel with trace_ancillas=True: **equal**
- same_channel with trace_ancillas=False: **different**

All four input matrix units are tested with exact coefficients. This is
a direct counterexample to taking an unqualified
ProofResult(EQUIVALENT, CLASSICAL_OUTPUT_INSTRUMENT) and always relabeling
it FULL_QUANTUM_CHANNEL without remembering whether the instrument
was already traced. A correct contract preserves the quantum
output frame and may infer equality only on that same reduced
output space, never silently strengthen it.
