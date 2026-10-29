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

## SHA-pinned native microbenchmark screen — 2026-10-29

The independent GitHub Actions benchmark on **source HEAD `7a75f82717801fa8606a35715f5ddaae048a726b`**,
[run 40839531614](https://github.com/yoch/symq/actions/runs/40839531614),
completed with five fresh subprocesses per backend/case (CPython 3.12,
Ubuntu hosted, C core built explicitly). The retained raw timings and
process RSS values are in `RESULTS/paired-native-20261029.json`.

| Synthetic family | Python ZDD median | C/ZDD median | Python/native |
| --- | ---: | ---: | ---: |
| affine, 8 data, 130 HMR | 3.401 ms | 3.498 ms | 0.97x |
| affine, 16 data, 500 HMR | 12.890 ms | 13.339 ms | 0.97x |
| nonlinear, 8 data, 70 HMR | 188.246 ms | 22.170 ms | 8.49x |
| nonlinear, 12 data, 25 HMR | 5.690 ms | 1.888 ms | 3.01x |

The simple affine HMR stream is **slightly slower** with the native engine:
the Python opcode loop and interpreter overhead dominate. The nonlinear
families obtain sizable native gains when ZDD multiplication dominates.
The 8-data/70-HMR nonlinear case also reduces measured process peak RSS
(from 37668 to 27444 KiB).

**No production speedup is claimed.** This is a small synthetic pilot,
not a matched real/holdout workload or a balanced randomized backend-order
trial. Small whole-call times, shared CI runner noise and process-wide RSS
limit interpretation. An actual compiler corpus with pinned provenance,
unsupported denominators and predeclared CPU/RSS conditions remains the
mandatory promotion gate. This report belongs to the measured source SHA,
not automatically to subsequent commits.
