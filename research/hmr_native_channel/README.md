# Native outcome-factored HMR full-channel pilot (#50)

Research-only, standalone SymQ source. This is **not** a universal hybrid
circuit verifier, a default verifier dispatch, or a replacement for
`symq.phase`. It reuses the existing **C-native monomial ZDD engine**
(`zdd-native`), independently selecting a Python ZDD path for comparisons.

## Native algorithm and mathematical scope

The strict `PhaseProgram` (X/CX/CCX/MCX, diagonal ±1 signs, unconditional
X-basis measure-and-reset HMR and earlier-outcome conditional Z/CZ/CCZ) has:

```
K_m|x> = 2^(-M/2) (-1)^(phi0(x) XOR SUM_j(m_j & g_j(x))) |F(x)>
```

Output functions `F`, the measurement-free phase `phi0`, and individual
coefficient functions `g_j` depend on **data inputs only**, not on HMR
outcomes. A C/ZDD manager is constructed with **2*n_data variables**
for a pair of coherent basis inputs `(x,y)`. All HMR events are kept as
separate C/ZDD *root handles*, never as extra symbolic variables.
The native 64-bit variable mask therefore requires `2*n_data<=64`,
independently of the number of measurement events and ancilla wires.
The variable-elimination identity yields:

```
E(|x><y|) = (-1)^(phi0(x) XOR phi0(y))
             * [g(x)=g(y)] * |F(x)><F(y)|.
```

For **full data+ancilla quantum output channels**, equality follows from
three exact obligations: identical outputs on every basis input; equal
pair-input coherence survival kernels; and equal relative phase on every
surviving coherence. Each is checked using native C/ZDD symbolic
XOR/product/equality and, on a detected difference, an independent
integer-gate interpreter replays the concrete input or coherence witness.
No exponential `2**M` branch enumeration is performed.

This is a specific accelerated algebra implementation of the existing
`research/innovation/2026-10-28/prototype/factored.py` theorem,
**not a newly invented quantum equivalence criterion**. The old pure
sparse factorisation and Kraus/density oracle remain independent references.
The full output includes ancillas, **does not trace them out**, and
**forgets final classical measurement records**. The observed instrument
of #85/#90 is a different theorem. General reset, Z-measurement,
classically controlled X, arbitrary rotations, S/T+H and general
dynamic quantum programs remain UNSUPPORTED, not approximated.

## Safety, performance and promotion gate

- Default backend is **explicit native** `zdd-native`: if its extension
  is missing, refuse. `backend="zdd"` deliberately selects Python ZDD
  without fallback. The native manager owns all four x/y symbolic states;
  no collection or stale node-ID reuse is attempted.
- Full-call wall budget, native node/term budgets, and caps on gates/HMR
  events are respected; exceed => ResourceLimitExceeded, never a PASS.
- Per-input witnesses `(x,x)` and pair-coherence witnesses `(x,y)`
  are concretely validated against a separate integer interpreter.
- 80 seeded small randomized comparisons against **both** a separate
  sparse outcome-factored exact theorem **and** a Kraus/density-matrix
  oracle, plus relative-phase, quantum-output, global outcome sign,
  wrong-feedback and 130-HMR regressions.
- A separate full-call/RSS fresh-process benchmark is included, but **no
  speedup is claimed without matched multi-family measurements** on
  source-cleared real circuits and independent untouched holdout.

```bash
pytest -q tests/test_hmr_native_channel_research.py
python -m research.hmr_native_channel.benchmark --repetitions 3
```

This remains a research PR until exact-head CI, source-cleared
HMR-heavy corpus, full-call/native RSS time benchmarks and
independent review prove useful coverage, correctness and cost.
No private-project import, external fixture, or binary redistribution.
