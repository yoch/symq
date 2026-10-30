# Strict hybrid import and branch sharing

The maintained importer is `symq.experimental.importers`. Its strict phase-stream
compiler was reviewed from public SymQ PR #88 at exact head
`2757ba0552d50c5718d4d4c9d357e0fd51a53fa2`; its original independent branch-oracle
qualification is retained in `tests/test_hybrid_phase_stream_research.py`.
`importer.py` here is a compatibility shim, with explicit exports.

The stream accepts X/CX/CCX/MCX/SWAP/CSWAP, Z/CZ/CCZ/NEG, HMR, affine classical
stores/inverts/XOR, and sign gates guarded by a classical bit or its complement.
Every HMR allocates a fresh event even when a classical slot is overwritten.
A reset lowers only when a conservative proof establishes that its wire is
already zero. Dirty reset, Z measurement and guarded quantum value updates
must retain their CPTP semantics in `symq.experimental.hybrid`; lowering them
to `PhaseProgram` raises `UnsupportedOperation`.

`freeze_hybrid` snapshots a validated `HybridProgram` into an immutable
`HybridIR`. The IR records immutable `MeasurementEvent` identities,
`ClassicalVersion` reads and writes, and each slot's final affine expression.
`to_program()` reconstructs and rechecks every event and SSA binding. A
builder's later mutation cannot change the frozen program.

`symq.experimental.qasm3.parse_qasm3` accepts an explicitly bounded OpenQASM 3
subset: qubit/bit declarations, indexed scalar permutation/sign gates,
Z measurement, true reset, affine XOR/NOT assignments and single-level
conditional gate blocks. Classical bits start at zero. Quantum registers
flatten in declaration order; `data` and `ancillas` mark the input frame.
Loops, nested conditions, general H/rotations, broadcasts, custom gates,
timing, metadata and unknown syntax are rejected. This subset is distinct
from the older OpenQASM 2 reversible parser.

## Exact branch sharing and its limitation

The canonical oracle is installed at `symq.experimental.hybrid`; the former
`research/hybrid_channel/oracle.py` explicitly reexports all original private
and public definitions. Its full channel comparison checks every matrix unit
`|x><y|`; checking basis probabilities alone cannot certify coherence.
Its observed instrument API preserves the requested final classical slots.
Standalone reset uses its full CPTP map.

`coherence_image_shared` is an additional bounded exact evaluator. Backward
liveness identifies classical bits that can still affect future operations or
observed output. After each instruction, matrices are summed only when their
live classical assignments are identical. For a group with common live bits,
all future classically selected quantum maps are the same linear maps, and
each measurement Kraus outcome map is linear. Therefore summation commutes
with every future step. Dead event histories can be removed; live classical
reads and requested observations cannot be removed. The evaluator retains
the original width/event/branch/resource guards and exact rational entries.

This does **not** establish a polynomial or general scalable hybrid verifier.
Forty HMR operations on an unused zero ancilla, overwriting one dead slot,
need one shared group. Conversely, k HMR outcomes stored in distinct slots
and used by k later guarded X operations keep all `2**k` classical assignments
live before those gates. The implementation deliberately raises at a
configured branch bound; eight such bits exceed a limit of 128 even on two
quantum wires. Density-entry support is also exponential in quantum width.
The retained study measures both cases and records failures, without an
external performance or speedup claim.

## Reproduction

```sh
PYTHONPATH=src python -m pytest -q tests/test_experimental_hybrid.py tests/test_hybrid_phase_stream_research.py tests/test_hybrid_channel_research.py
PYTHONPATH=src python research/hybrid_phase_stream/sharing_study.py
```

All generated examples and random seeds here are development qualification,
not untouched holdout data. This experiment establishes exactness on the
specified fragment and concrete resource limits, not external comparative
performance. Public Qualtran imports have their own provenance and embedding
contract in `benchmarks/corpus/qualtran/README.md`.
