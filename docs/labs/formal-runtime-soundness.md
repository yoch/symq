# Formal runtime soundness: the Boolean DAG/CNF reduction

This is a distinct, **development/CI-only** program from #168's optional Lean
proof exporter. Lean is not imported, shipped or needed by the SymQ runtime.
The proof artifact can be inspected independently of any solver-produced trace.

## Exact scope of the first milestone

The Lean module `formal/symq_runtime/GateCNF.lean` defines a small *abstract*
Boolean graph grammar: free input variables and AND/XOR nodes with signed
(complemented) child references. It directly models the 3-clause AND and
4-clause XOR patterns of `symq.labs.kraus_graph.Graph._clauses_for`.

It proves, universally over all Boolean valuations, that each gate's clauses
hold exactly when its output has the specified Boolean value. By induction over
an **arbitrary finite list of gates**, it proves

```math
\mathrm{CNFSat}(\mathrm{encode}(G),v)
\iff
\bigwedge_{g\in G}\mathrm{GateHolds}(g,v).
```

A final consequence proves that a truly UNSAT encoded gate relation plus a
root assertion excludes any valuation satisfying all gate equations and that
root. This is **not** merely a finite truth-table test.

The primary proof covers Boolean relational constraints, rather than the complete
Python execution engine. Input-to-graph compilation, unique propagation of
values through an acyclic graph, graph optimizations/hash-consing, actual Python
code correspondence, source-to-phase/channel semantics and external source
preparation **remain separate obligations**. No theorem silently assumes that
a Python function is the same as its Lean model.

A differential Python test mirrors the gate CNF independently: it compares
the actual generated clauses, all gate truth tables including complemented
edges, 80 deterministic mixed DAGs at 16 inputs each, wrong-output mutations,
and the scalar `Graph.evaluate`. These are *conformance tests*, not a formal
proof of the Python-to-Lean refinement.

## Trust model and roadmap

- Runtime: unchanged `Graph` and SAT, **no Lean dependency**.
- Development: pinned Lean 4.19 checks general theorems in CI. Axiom reports
  are retained. A Lean error fails the build. Because a `sorry` is only a
  *warning* (Lean still exits 0) and a report line is plain text,
  `tools/check_formal_axioms.py` also rejects any Lean diagnostic in the log and
  scans the sources: no `sorry`/`axiom`/`native_decide`, no command or extension
  that can print text (`#eval`, `#print "..."`, `run_cmd`, macros, notations,
  `trace`/logging tactics, meta-programming, any string literal),
  and exactly one `#print axioms` per listed theorem. The checker pins theorem
  *names*; a reviewer must still read each statement.
- Follow-up A: prove that evaluating any well-formed acyclic DAG yields a model
  of its CNF, and conversely that every CNF model respects its evaluated result.
- Follow-up B: prove graph-building rewrites (constant folding, XOR cancellation,
  hash-consing) and the implementation refinement or use a small certified
  checker for an independently serialized graph.
- Follow-up C: certify the ripple-carry modular phase semantics and their
  composition with source-bound quantum equivalence obligations.
- Separate experimental lane: portable LRAT/Lean instance export in #168,
  without requiring Lean at runtime.

This is not formal verification of all SymQ and does not certify a qant/KMB
loader. The `main` backend, public API, and existing semantics are unchanged.

## Reproduce

```bash
python -m pytest -q tests/test_formal_runtime_contract.py tests/test_kraus_graph.py
# With the toolchain pinned by formal/symq_runtime/lean-toolchain:
cd formal/symq_runtime
lake build   # builds all four libraries
(lean GateCNF.lean && lean PhaseBits.lean && lean AcyclicDAG.lean && lean GraphRewrites.lean) 2>&1 | tee theorems.log
cd ../..
python tools/check_formal_axioms.py formal/symq_runtime/theorems.log --sources formal/symq_runtime
```

Claims of successful Lean compilation are bound to the exact CI run/commit,
not inferred from this source text.

## General phase accumulator arithmetic (separate formal theorem)

`PhaseBits.lean` proves the exact full-adder identity and an induction over
arbitrary same-length little-endian input words:

```math
\mathrm{word}(\mathrm{sum})+2^k\mathrm{carryOut}
=\mathrm{word}(a)+\mathrm{word}(b)+\mathrm{carryIn}.
```

This is one addition with the final carry kept. The corollary "the sum word
is correct modulo `2**k`", the per-coefficient masking of the addend and the
fold over all phase terms in `_phase_bits` are **not** stated in Lean; they are
covered only by the Python tests below. The recurrence models the
XOR/parity and XOR-of-disjoint-carry-terms structure used in
`nonlinear_phase_bits._phase_bits`. It is a universal arithmetic property
of the abstract recurrence; the tested Python implementation is not yet
mechanically refined to this Lean definition. Python tests compare it with
integer modular arithmetic for k=1,2,3,4,8,12,16 over seeded phase predicates.

## Second milestone: acyclic execution, exact hierarchical clauses, and rewrites

`AcyclicDAG.lean` encodes a graph whose edges can only refer to earlier nodes,
proves existence **and uniqueness** of its evaluation for any input, and proves
that the exact local three-/four-clause gate constraints (plus input-pin clauses)
are equivalent to those defining equations. It derives uniqueness of the
hierarchical CNF model and a conditional root-UNSAT theorem. Its type permits
input variables created *after* previous Boolean gates.

`GraphRewrites.lean` proves 15 universal Boolean identities for signed
XOR cancellation, complement propagation and AND/constant/idempotent
simplification. The Python conformance suite separately tests the real Graph
implementation including late inputs, hash-consing and scalar replay.

The proof does **not** yet establish byte-identical flat Python CNF encoding
or the soundness of Python's complete graph builder and phase/channel
compiler. See [the 32-theorem exact qualification](../evidence/formal-runtime-20261103b.md).
## Development-only concrete graph snapshot seam

The new standalone `tools/formal_graph_snapshot.py` validates a canonical
snapshot of the **actual Python** `Graph.nodes`, `Graph.variables` and
`Graph.unique` tables. It refuses bad physical node 1, reused/negative
logical input names, forward/self edges, malformed or unsupported gates,
wrong hash-consing caches and root references. It accepts gate edges to the
constant node 1 and roots `1`/`-1`, which the Lean DAG cannot represent (its
children are earlier *gate or input* positions); the public `Graph.mul`/`xor`
fold constants away and never create such edges, but a future Lean parser of
the snapshot must reject them or extend the model. It then emits the deterministic
flat clause list and a separately tagged SAT assumption, together with a
content digest. Its scalar evaluator is independent of `Graph.evaluate`.

The accompanying tests use 80 seeded graphs (including late variables),
source truth tables, deliberate input-name aliasing, malformed graph mutations
and a recording SAT backend to check the **actual incremental clause stream**
against the independent snapshot serializer. The recorder deliberately returns
`inconclusive`; it must not impersonate a successful proof.

This is an **auditable interface proposal**, NOT a formally verified Python
implementation or an accepted proof receipt. Its output is not yet fed to a
formally checked Lean parser. It is development-only, with no import from
`src/symq/` and no overhead or dependency in normal SymQ execution.

The logical uniqueness precondition of `runtimeQuery_sat_iff_unique_keys`
is thus checked against real hash-consed input tables in independent tests.
The Lean theorem, the Python snapshot validator and these tests have different
trust roles; none substitutes for a machine-checked Python-to-Lean refinement.

## Third milestone: guarded SAT completeness and concrete Python snapshots

Lean proves the source-key-coherent converse of the unpinned runtime
query theorem, plus `uniqueInputKeys ↔ List.Nodup inputKeys`. With genuinely
unique logical input names, SAT existence and source-execution existence
are equivalent; without that hypothesis, only the UNSAT→no-source-witness
direction remains generally valid (and a counterexample is included).
The separate development-only snapshot parser is an independently tested
conformance seam, **not** formal Python refinement. See
[the exact 54-theorem qualification](../evidence/formal-runtime-20261103c.md)
and [the external audit checklist](../audit/formal_runtime_169.md).
