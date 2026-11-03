# Exact SymQ formal-runtime qualification — 3 November 2026

This records general **development-time** Lean theorems, not Lean proof checking
on every SymQ runtime call and not formal verification of Python itself.

- Executable PR #169 HEAD: `2e33e6e3d751c6d1b1e1ae1b158a952c9fd06083`; Git tree `302b0c0e76dc6687a9419d87f6bfc4ca886f29ee`.
- Main base: `7861aa9d4a31791644382df8bdfd5abbcdf4a628`.
- GitHub synthetic merge: `a843ae8d968bb4f2d43e3c94f774e5df9e8ace04`.
  Its parents were reread and are exactly main + the executable HEAD;
  its tree is identical to the branch tree.
- [Formal CI 41591903783](https://github.com/yoch/symq/actions/runs/41591903783):
  **success** on this source; pinned Lean 4.19, Ruff and 21 targeted Python tests.
- The complete artifact 13210736358 was downloaded and rehashed:
  ZIP SHA-256 `3748e7ab31b6777629d9edf0ca311c9a404dd4981ae2399383d173184bd994ff`,
  matching GitHub's published digest. `commit.txt`, `tree.txt` and
  `theorems.log` were inspected independently.
- All **32** expected axiom reports are present and unique; no `sorryAx`,
  custom axiom or trusted native computation appears. A strict verifier
  fails on missing, duplicated or unapproved reports.

## What has been formally proved

| Lean family | Number | Universal result |
| --- | ---: | --- |
| Relational signed graph CNF | 4 | AND/XOR clauses, arbitrary gate lists and UNSAT root exclusion |
| Modular phase arithmetic | 2 | Full-adder and arbitrary-width carry accounting |
| Acyclic execution | 6 | Evaluation existence/uniqueness on every well-typed DAG |
| Hierarchical pinned CNF | 5 | Input pins, local clauses, CNF/semantic equivalence, unique model, root exclusion |
| Graph rewrites | 15 | Signed XOR cancellation, AND identities, complement and constant folding |

The 15 rewrite identities, local clause identities and full-adder use no axioms.
Others use only Lean's standard `propext`, `Quot.sound` and
`Classical.choice` as reported. These are model theorems, not empirically
estimated properties.

## Trust boundary not yet closed

- The inductive Lean DAG excludes future-child references **by type**;
  the Python graph and its flattening/incremental SAT producer are not
  mechanically refined to that representation.
- The new CNF equivalence is for a **hierarchical conjunction** of exact
  per-gate clauses and input pins, not yet a theorem about byte-for-byte
  flattened Python DIMACS including constant-node 1 and SAT assumptions.
- Cross-language Python conformance tests actually exercise
  `Graph._clauses_for`, `Graph.evaluate`, XOR/AND reductions and
  `nonlinear_phase_bits._phase_bits`; this is testing, not formal proof.
- Source-to-DAG compilation, measurement/environment assumptions, quantum
  channel semantics, coherent control and real compiled KMB programs remain
  outside this formal result.
- Lean is used only by developer CI. No runtime import, dependency change,
  public-API promotion or merge is implied.

Next high-priority theorem: faithful flat-CNF serialization of a typed
acyclic DAG (including lazy clauses, root assertions and node1=true),
then a narrow, auditable bridge to the actual Python code.
