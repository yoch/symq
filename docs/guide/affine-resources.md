# Existing wires with a proved affine state relation

`symq.labs.kmb_affine_resources` is a bounded sufficient resource checker. It
does not rewrite a source or verify a cache replacement. Its inputs independently
pin the entire KMB file and a closed version-1 request; replay rebuilds the source
snapshot, both extractions, the support expressions and every reported obligation.
All coordinates count zero-based raw KMB operations, including INFO_TAG.

The new case is an existing wire whose value is not a known constant but obeys

```text
q = constant XOR parity(parents)
```

If that graph is proved at the actual reservation cut, `X(q)` for a constant one
and `CX(parent,q)` for each parent make q **pure zero**, including for coherent
states entangled with the parents and an external frame. The inverse preparation
restores the graph and those correlations. This follows from an unsigned basis
permutation on the whole graph subspace, not a measurement of the borrowed bit.

There are separate obligations: the graph relation must be proved; the original
window must not touch q; the parent values must be preserved; and the eventual
replacement must return q to pure zero with the required phase and classical
semantics. The checker proves the first three, using absence of possible writes
as its deliberately sufficient parent-preservation rule. **Absence of writing
does not establish the initial graph relation.** A replacement still needs a
fresh signed-column, channel or instrument proof at the site. See
[reset caches](reset-cache.md) for that distinct proof boundary.

The `restoration_condition` field makes the final condition explicit. Neither a
`proved` resource receipt nor its example is an authorization to apply a rewrite.
The checker never sets `candidate_authorized` or `global_substitution_proved`.
There is no independent certificate or ancilla allocator.

Resources in one request must not be parents of other requested resources.
Shared parents outside that resource set are allowed: every preparation writes
only its own resource, so all accepted preparations preserve each other's parents
and can make the returned resources jointly zero. Restore by applying the inverse
of the combined preparation after the replacement returns every resource to zero
and preserves those parents. A batch with cross-resource parents is `unsupported`.
For example, two individually valid graphs `q0 = q1` and `q1 = q0` do not give two
simultaneously clean wires: the first preparation changes the second graph's
parent. Assess such alternatives separately; this checker does not schedule
dependent resource preparations or prove a compatible subset.

## Closed request and exact domain

```python
source_sha256 = "0" * 64  # Template: replace with the independently pinned complete-file hash.
request = {
    "kind": "symq_kmb_affine_resources", "schema_version": 1,
    "source_file_sha256": source_sha256,
    "analysis_window": [0, 2], "reservation_window": [2, 4],
    "domain": "all_source_quantum_states_and_classical_values",
    "resources": [{"wire": 2, "parents": [0], "constant": 0}],
}
```

The analysis ends exactly at the reservation cut. Its initial quantum inputs and
classical values are arbitrary, including correlations. An unwritten predecessor
is an identity input. No zero or relation is assumed at an intermediate cut.
Thus a proved relation holds for every state the pinned complete prefix can
produce. Nonzero analysis starts weaken the available facts; they do not silently
inherit any state preparation. A different restricted or empty domain is refused.

Quantum support is propagated through X/CX/CCX, SWAP/CSWAP, resets, HMR, conditions,
classical stores and inversions. Each HMR supplies a fresh possible outcome;
conditional definitions retain the prior slot value on skipped branches. Initial
classical reads remain arbitrary, with no implicit zero or reused old outcome.
Z/CZ/CCZ/NEG change signs and leave computational support unchanged. Ignoring
their signs here proves **only a support fact**, never phase equivalence.

The support representation uses XOR cancellation and interned Boolean products,
with zero, one, idempotence and complement identities. It avoids expansion into
potentially enormous monomial sets. It is incomplete: a nonzero residual may
still be the zero Boolean function. `not_proved` therefore does not mean dirty,
unsatisfiable, inequivalent or impossible. There is no counterexample export.

Initial cleanliness has separate `proved_zero`, `proved_one` and `unknown` values.
A graph receipt may be usable with `unknown` initial cleanliness, because its
explicit affine preparation proves zero afterwards. A demonstrated one fails a
requested zero relation, while a constant-one graph can be prepared using X.

## Limits and qualification

The entire source is copied and SHA-256 checked, then validated with the existing
resource-frontier grammar. Unknown, debug and Z_POW instructions are refused
anywhere, including outside either selected span. Selected spans must have empty
outer condition stacks and contain no PUSH/POP; conditional individual operations
remain supported. No full prefix Circuit is materialized.

Defaults: complete file ≤2 GiB / 100 million raw operations, 4096 global wires,
250000 analysis operations, 4096 reservation operations, 32 requested resources
and 32 parents each, 100000 support atoms, 8192 terms per value and 2 million
retained product operand terms. These are representation/work caps, not measured
RSS guarantees. Source validation, extraction, support proof, dependency identities
and replay share the caller's time budget. Expiration or a representation limit
returns `inconclusive` with **no facts or usable resources**. An unsupported
instruction returns `unsupported`, separately from an unproved graph.

The tests compare full tiny instruments on every matrix unit with an independent
Kraus oracle, including an originally dirty/correlated borrowed wire and the old
measurement result. A separate scalar differential checks all 64 tiny quantum/
classical inputs through conditional permutations, measurements and slot updates.
Mutants cover wrong graph, assumed cleanliness, overwritten product, parent write,
resource read or phase, stale source/request/receipt, empty domain, timeout and
representation limits. The synthetic benchmark retains positive and negative
trials at three repetitions; it makes no external performance claim.

```sh
python -m pytest -q tests/test_kmb_affine_resources.py
python -m benchmarks.kmb_affine_resources --output evidence/kmb-affine-dev.json
```
