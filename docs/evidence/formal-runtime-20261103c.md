# Exact qualification — 54 universal SymQ formal-runtime theorems

The objective is to **certify algorithms during development**, without
requiring Lean during normal SymQ execution. This is not a source-level
certification of all Python code.

## Exact source and execution

- Repo: `yoch/symq`, Draft PR #169, branch
  `research/formal-runtime-cnf-20261103`.
- Base `main`: `7861aa9d4a31791644382df8bdfd5abbcdf4a628`.
- **Executable HEAD**: `7f04a59de7f06e4f74c9573443ed71e87d333efb`.
- Git tree: `bba8c355538463eb826e1cada9856cd0b3cc9dac`.
- Synthetic merge: `424661fcfc74a7dfe0cafa0d20d03f5301964692`,
  whose parents, independently fetched from GitHub, are exactly the base
  and the executable HEAD, with the identical Git tree.
- [Formal qualification 41606235894](https://github.com/yoch/symq/actions/runs/41606235894)
  passed Ruff, **32 targeted Python tests**, actual Lean 4.19 proof
  elaboration, and the strict **54-name** axiom-report allowlist.
- Downloaded GitHub artifact `13216662611`; independent ZIP SHA-256
  `5a273d63e16f49df235f27ad9e15cf0a0adfa34a9be2eb885732c9df6feb7537`,
  equal to the GitHub API digest. `commit.txt`, `tree.txt` and
  `theorems.log` were extracted: all 54 theorem reports are distinct,
  the published merge/tree match, and no `sorryAx` appears.
- The general multi-platform CI run on the executable HEAD is a separate
  qualification; it was in progress when this note was authored.
  Do not treat its status as inherited from an earlier commit.

## What Lean now proves

The total comprises 54 **named** model theorems, including many small lemmas,
not 54 independently discovered quantum theorems.

1. Boolean AND/XOR Tseitin clauses, arbitrary relational gate lists,
   complementary signed edges and a sound root UNSAT implication.
2. A typed acyclic DAG has a unique execution valuation for every input;
   its hierarchical and physical flat CNF clauses match those semantics.
3. Exactly modelled physical node IDs, true-constant clause `[1]`,
   input pins and separate root assumption.
4. Without input-key uniqueness, UNSAT of the runtime-shaped **free-input**
   formula still excludes a real source counterexample (soundness).
5. Under `uniqueInputKeys dag` the converse also holds:
   a SAT assignment can be mapped to a source input, and the source input
   can be lifted back to a SAT assignment. Therefore SAT/UNSAT correspond
   exactly to the source's output condition in the typed model.
6. `uniqueInputKeys` is equivalent to `List.Nodup (inputKeys dag)`.
   An explicit duplicate-key typed DAG demonstrates the failure of the
   unguarded SAT-to-source direction.
7. General ripple-carry Boolean addition and fifteen XOR/AND rewrite
   identities.

These mathematical results have no `sorry`, native trusted computation
or custom axioms. The declared Lean axiom dependencies are only the
standard `propext`, `Quot.sound` and `Classical.choice`; many local
algebra identities use none.

## New Python implementation-conformance seam

The *development-only*, standard-library-only
`tools/formal_graph_snapshot.py` checks the concrete `Graph.nodes`,
`variables` and `unique` dictionaries; validates topological signed
edges, strict nonnegative plain-integer input keys, unique source names,
normalized gate records and constant node 1; serializes an independently
computed ordered clause stream; and keeps the queried signed root
**separate** as a SAT assumption. A deterministic SHA-256 identifies this
serialized data, but is NOT a logical proof.

New tests (`tests/test_formal_graph_snapshot.py`) cover 80 deterministic
graphs, exhaustive small source valuations, scalar replay, malformed
inputs/edges/caches and a recording SAT backend. The recorder forces
`inconclusive`; it checks the actual **incrementally appended clauses**
and assumption lists against the independent serializer, not solver
soundness. A deliberately invalid `Graph.var(True)` first-call index is
rejected when visible in the snapshot.

**Honest negative:** after `var(1)` was previously interned,
`var(True)` aliases the same dictionary key in Python. A post-hoc
snapshot cannot detect this historical invalid call. We tested and
documented that limitation rather than claiming it is impossible.
A strict caller/API-boundary input type contract is still necessary.

## Remaining proof boundary and next objective

The generic Lean model is **not** an automatically verified copy of
`kraus_graph.py`. Source extraction, Python's control flow and type
handling, hash-map integrity, incremental SAT process semantics,
quantum/HMR domain assumptions and full-channel composition have not
been proved end to end. The snapshot validator is tested, not
formally verified, and no Lean parser yet reconstructs its actual
serialized bytes as a typed DAG.

The next useful milestone is an independently checked **typed parser
or formal refinement contract** for the snapshot, followed by source to
Boolean-phase/channel semantics. Preserve the no-Lean-runtime requirement
and keep optional per-proof export #168 separate.

No qant/KMB real circuit certification, new runtime dependency, public
API promotion, default backend change or integration authorization.
