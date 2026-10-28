# Hybrid circuit verification: current theorem boundaries and next milestones

**Research design note, not an implementation claim.** This document is standalone
and deliberately does not import or depend on any other repository. Source-code
correctness, whole-program channel equivalence, and benchmark score are **three
different** claims. No engine is selected automatically.

## Current state

The maintained `symq.phase` accepts reversible basis permutations X/CX/CCX/MCX,
sign phases Z/CZ/CCZ, unconditional X-basis `hmr` (measurement **and** reset),
and conditional sign-phase corrections based on an *earlier single* measurement
outcome. Its strict equivalence check assumes input ancillas start in `|0⟩`
and checks O1 (restored ancillas) and O2 (phase independent of all outcomes).
A separate experimental research path can compare full channels in this
restricted grammar using factorized outcomes and a small exact Kraus oracle.

This already establishes **restricted** HMR/feed-forward support. The classical
`Circuit` and OpenQASM reader do not expose it, and the independent diagonal
Z/8-phase prototype does not accept measurements. The explicit-verification
facade marks full-channel proof as unsupported, by design.

## The actual next grammar

| Feature | Starting milestone | What must be proven |
| --- | --- | --- |
| Classical outcome XOR/NOT/constant and variable reuse | H0 | Unique event per HMR and correct versioned binding of each storage bit |
| X/CX and Z/CZ conditional on prior outcome expressions | H1 | Exact branch state and phase, including nested scopes and all reachable outcomes |
| Clean zero-ancilla `reset0` | H1 | State known to be `|0⟩` before reset for all allowed inputs and branches |
| General reset on an unknown/dirty qubit | H2 | **CPTP channel** with discarded environment, not a unitary step |
| Independent channel comparison after outcomes | H1/H2 | Equality on every input density operator, including all off-diagonal coherences |
| Arbitrary H / S/T with H / arbitrary rotations | Different engine | Complex amplitudes, interference and separate exact/approximate semantics |

"Outcome name" and "measurement event" must be separate objects. An output
`b0` may store the XOR of several outcomes and later be reassigned; the
events `m_0,m_1` remain independent even if the same storage identifier is
reused.

## Semantics and the crucial counterexample

For the **restricted** subgrammar of basis-permuting reversible gates,
diagonal signs and unconditional X-basis HMR (with no dirty standalone reset),
a branch for an input basis state has the form

$$
K_m|x\rangle=2^{-M/2}(-1)^{\phi(x,m)}|F(x,m)\rangle .
$$

Here $M$ is the number of independent HMR events. With classical feedback
onto value gates, **$F$ can depend on $m$**; with composed guards, **$\phi$
can be nonlinear in $m$**. Neither the old outcome-independent-output
invariant nor the affine-phase-in-outcomes invariant may be reused without
an explicit proof of eligibility.

The quantum channel is

$$
\mathcal{E}(\rho)=\sum_m K_m \rho K_m^\dagger .
$$

Two programs can agree on all **basis inputs** and nevertheless implement
different channels. A minimal counterexample is: start with a clean ancilla
`a`, prepare data `d` in `|+⟩`, apply `CX(d,a)`, then reset `a` and
discard its environment. The data becomes dephased. A do-nothing program
leaves `|+⟩` coherent. On each classical input basis state `d=0` or
`d=1`, however, both programs return the same data value and a zero
ancilla. **A basis-value replay would give the wrong channel verdict.**

Therefore, a finite-domain Boolean contract does not grant a quantum
channel theorem merely by observing all its diagonal basis-state values.
If the legal input set is $D$, a full channel theorem on the coherent
span of $D$ must account for **every pair $(x,y)\in D\times D$**, not just
for $x=y$.

For small programs, an independent rational Kraus/density-matrix
oracle must establish these distinctions first. Only then should a
symbolic proof backend be introduced.

## Suggested architecture

**H0 — Contract and typed IR.** Closed grammar; initial free/zero/borrowed
quantum wires; exactly named observed outputs; fresh measurement events;
classical expression AST (constants, XOR, NOT and bounded AND); explicit
scopes; exact wire/bit validation; fail closed for unknown gates, rotation
families or reuse beyond the grammar. No backend promotion.

**H1 — Exact small hybrid proof.** Independent branch interpreter and
Kraus oracle; all data basis inputs, all HMR branches and all input
coherences. Support outcome-conditioned phase, then outcome-conditioned
X/CX. Preserve exact amplitude normalization. Separate strict branch
equivalence, full output channel, traced/observed channel, and precondition
failure. Reproduce witnesses independently.

**H2 — Specialized scale-up.** If H1 passes, experiment with bounded
ANF bitsets, coefficient truth tables on an explicit finite legal domain,
a per-event phase ledger and ZDD/SAT residual decisions. Use formal
saturation markers for unmodeled or over-budget behavior: *unknown* must
never be silently interpreted as zero. Profile full-call time and memory
with matched cohorts before changing any default.

**Separate engineering track — proof receipts.** Canonical semantic IR,
domain and output-contract hashes; immutable solver and oracle versions;
evidence-specific witness or UNSAT status; explicit proof coverage and
unsupported counts. SAT UNSAT relative to CNF is not an independently
validated LRAT certificate.

## Required soundness regressions

1. A valid temporary-AND gadget erased by HMR with the exact conditioned CZ;
   a missing CZ must be rejected, including on superpositions.
2. Two independent HMR events stored successively in one classical slot;
   overwriting the slot must not merge the two event symbols.
3. XOR of two measurements used as the guard of a value gate; a wrong parity
   must produce an observable channel difference.
4. Unknown/entangled-ancilla reset vs identity: basis outputs agree, but
   channels differ.
5. A valid partial-output channel relation vs different full-output channel;
   do not confuse tracing ancillas with proving their restoration.
6. Unsupported standalone H, S/T+H, arbitrary rotation and malformed
   conditional scope: reject before symbolic interpretation.
7. Finite-domain vacuity, unproved clean ancilla, outcome-dependent reset,
   ambiguous classical-bit reuse and budget exhaustion: **no PASS**.
8. Differential tests against a separate exact Kraus oracle and explicit
   unsupported denominators on external/realistic examples.

## Promotion gate

No public claim of general dynamic-circuit verification until the typed
IR and independent channel oracle jointly support the corresponding
grammar. Avoid promoting an HMR SAT path solely on correctness if paired
benchmarks find it slower than the existing ZDD criterion. Keep the
experimental Z/8 unitary engine separate until any combined phase-and-HMR
semantics is independently proven.

Related discussion: [#85](https://github.com/yoch/symq/issues/85)
(new hybrid semantics) and [#86](https://github.com/yoch/symq/issues/86)
(bounded exact representations). These are **standalone SymQ milestones**,
not dependencies on external projects.
