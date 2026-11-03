# Independent audit mission — #169: development-time formal runtime certification

## Scope and state
The whole existing [Draft PR #169](https://github.com/yoch/symq/pull/169)
must be independently reviewed, not just its last new theorems.
Start from HEAD `7f04a59de7f06e4f74c9573443ed71e87d333efb`, tree
`bba8c355538463eb826e1cada9856cd0b3cc9dac`, base main
`7861aa9d4a31791644382df8bdfd5abbcdf4a628`.
Revalidate these on GitHub, plus the latest reviews, threads, diff and
current-head checks, before analysis or mutation.

## Formal adversarial review
- Read `formal/symq_runtime/{GateCNF,AcyclicDAG,GraphRewrites,PhaseBits}.lean`
  in full, not just theorem names or CI green lights.
- Look for inconsistent assumptions, incomplete pattern matching,
  unsound coercions, hidden `sorry`, unreported axioms, errors disguised as
  theorem successes, missing explicit constant and root semantics.
- Attack equality of source-name keys, duplicate names, late input
  registration, signed/negative edges, literals referring to node1,
  zero, input pins, source support and arbitrary graph widths.
- Check the formal `uniqueInputKeys`/Nodup equivalence and both directions
  of the SAT/source theorem. Reproduce the deliberate duplicate-key
  negative. Distinguish SAT completeness (conditional) from unguarded
  UNSAT soundness.
- Compare the *unrestricted* flat query to Python's lazy SAT clauses,
  noting that `assumptions=[root]` is not necessarily emitted as a
  physical unit clause at the Python API boundary.

## Code conformance and producer trust
- Audit `tools/formal_graph_snapshot.py` as **untrusted** test tool.
  Independently create graph snapshots, mutations, malformed keys and
  separate truth-table oracles. Verify it cannot accidentally accept
  forged graph identities or claim proof authority.
- Audit the actual `Graph` Python source at the exact HEAD, its
  `variables` and `unique` cache invariants, anchoring, incremental
  appends, and `Graph.evaluate` model replay.
- Reproduce the `True`/integer-1 historical aliasing limitation;
  do not confuse visible snapshot validation with call-history or
  source-to-model formal verification.
- Probe deadlines, malformed types, invalid source indices, proof
  result revocation and lazy addition of new graph nodes.
- Preserve standalone Python/natively compiled and SAT optional
  behavior. No Lean runtime import or dependency allowed.

## Outcome and permissions
Require fail-before/pass-after regressions for genuine findings, actual
pinned Lean compilation, strict axiom reports, Ruff, full native/SAT
package and wheel/sdist CI. Record SHA/tree/conditional writes and
inspect the final diff and artifacts.

Decision: ACCEPTABLE_FORMAL_RESEARCH, CHANGES_REQUIRED or DEFER, with
separate assessments for (a) model theorem validity, (b) the Python
conformance tests, and (c) the still-open Python-to-Lean refinement.

Do not merge, promote stable APIs, alter `main`, or open a redundant
assembly. Preserve #168 as optional proof export and #170 as open work.
