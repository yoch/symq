# Lean kernel qualification: exact executable checkpoint

Base main: `7861aa9d4a31791644382df8bdfd5abbcdf4a628`.
Executable HEAD: `303ae443551c295898b3b0caa482b2e8d56ae97d`.
Tree: `eaff192ec3c384c9b8106b2db1b8474a9597cc21`.
Synthetic merge: `1f8eecfdac00e46deeec9a0e2a5c152d68904a2b`.
The later guide/inventory/test clarification must still have its own current-head
CI status inspected; this note never reassigns the checkpoint results.

[Qualification41542246059](https://github.com/yoch/symq/actions/runs/41542246059)
passed on the installed package, with actual Lean4.19.0 and kernel reduction.
The pinned Lean source commit is 6caaee842e9495688c1567e78c0e68dbb96942aa. PySAT was
actually uninstalled before the checking stage, and import absence was asserted.

Downloaded artifact13187426808 ZIP SHA-256
`fd60185d08962860a4a6dc57e199b09720752a56fa9dabe54b8ce25b34de9300`
was independently recomputed and matches GitHub's digest. Recorded commit/tree,
all fourteen result rows, accepted/rejected flags, CNF/LRAT/Lean file hashes and
axiom lists were inspected. Generated Lean source was independently regenerated
locally and byte-compared for every row; that is not a second local Lean run.

## Results

| Instance | Input clauses | LRAT steps | Lean process seconds |
| --- | ---: | ---: | ---: |
| phase000 | 2 | 1 | 0.430 |
| phase027 | 8 | 1 | 0.685 |
| phase031 | 65 | 9 | 7.838 |
| phase063 | 50 | 5 | 4.715 |
| phase095 | 5 | 1 | 0.559 |
| phase127 | 33 | 5 | 3.224 |
| phase191 | 54 | 11 | 7.247 |
| phase255 | 2 | 1 | 0.430 |
| pigeonhole | 22 | 7 | 2.638 |
| original empty clause | 1 | 1 | 0.387 |
| sparse variable numbering | 2 | 1 | 0.430 |

All eleven instances produce a checked `SymQPortable.claim`. None uses sorryAx,
a native computation axiom or a custom axiom. Their listed dependencies are only
propext, Quot.sound and Classical.choice. These timings are single small-instance
process measurements, not a paired speed benchmark; kernel reduction is already
nontrivial at65 clauses and no large-proof performance is claimed.

The three negative traces (incomplete no-unit refutation, non-unit hints on a
satisfiable formula, changed literal polarity) fail their positive claims. Each
also has an accepted theorem `SymQPortable.rejection : accepted = false`, with
the same standard axiom list. An invalid trace does NOT in general prove that
its input formula is satisfiable; the first negative formula is unsatisfiable.

The generic `andClauses_iff`, `xorClauses_iff` and `fibre_constancy` lemmas compile
with **no axioms**. They cover all Boolean valuations or abstract domain elements,
not only the generated sample instances. They do not identify the Python encoder
with the formal encodings.

## Provenance and honest boundaries

The emitter blob is b1192e9743315256cfc2becb8bf26097c1ec787d, SHA-256
`757cf296ffd432d362d410dd44aa2664862c0467ccc4da903f2e03f6ce70ddcb`.
The qualification harness blob is cce781108e508f899d9c65854fd0d9a85ceebb62, SHA-256
`adb654de68120f52064ab87f3ed98a0471868a9334f01be35fa93c24170d2847`.
The archive records the independent Python kernel and source consumer hashes,
the formal gate module and toolchain file too. No external hash is a proof axiom.

The existing 256-case portable-proof qualification is a separate source-level
experimental check. This milestone formally proves UNSAT of eleven specific
literal formulas, and proves three specific checker refusals. The source compiler,
parser/data bridge, quantum theorem implementation, toolchain/runtime and caller
assumptions remain explicitly outside an end-to-end verified chain.

Historical setup, root-path, reduction and clause-typing failures are retained in
GitHub Actions; they are not counted as evidence. One initially selected negative
was invalid only for the strict Python profile, not for Lean's preloaded-unit
algorithm. It was corrected to a genuinely nonconflicting hint sequence and then
its rejection was formally proved, rather than weakening the harness.

Local validation used authenticated standalone Python modules and15 emitter tests;
there was no local installed SymQ/PySAT/Lean/full-suite run. The formal executions
above took place in the recorded CI environment. All data are constructed
research fixtures; no real quantum compilation workload is certified.
