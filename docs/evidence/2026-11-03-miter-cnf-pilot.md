# C0 research: deterministic CNF snapshot of a classical SAT miter

Source: issues #167/#170 and coordination #179. Pinned reference:
main 766d3dfb3bad0212beb3e0b4d6ef4daf5078d6dc.

The existing `symq.sat.miter.build_miter` constructs a Tseitin
encoding and `check_sat_equivalence` appends the clause asserting
that at least one required output differs. `miter_cnf.py` uses
**that same code** to expose a deterministic, source-bound DIMACS
snapshot, not a second implementation of the encoder.

It accepts a **narrow** classical reversible Contract subset:
input constants, optional output observation/map and restored wires.
Arbitrary assumption ASTs are rejected until their serialization
and source-to-CNF bindings are qualified. Every source-facing input
is copied before the encoding, and SHA-256 pins identify the
frozen sources/contract and exact emitted formula. A manifest is
not a proof and is not an independently authenticated signature.

Test code uses a pure Python DPLL oracle to check per-input
satisfiability and complete small truth-table semantics without
using the SAT solver. It passes the exact DIMACS through the
strict standalone portable proof checker's parser.

## Not yet implemented by this pilot

- UNSAT LRAT producer/exporter or third-party proof checker handoff.
- Full contextual cut contract and source-to-high-level theorem binding.
- A verified Python or C source-to-CNF refinement.
- A standalone positive source-verification certificate.
- Measurement/HMR/coherent channel obligations.

C1 must derive source obligations from independently supplied
source files and verify the exact miter CNF and compatible RUP
proof in a solver-free consumer. Existing `phase_proof_bundle`
must not be reused as a false source proof.

All test/CI claims require exact published SHA after opening the
Draft research PR; the source and this note alone do not
constitute qualification. No merge, API promotion or default change.
