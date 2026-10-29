# Exact degree-k integer-bitset ANF research pilot (#86)

A separate, explicitly opt-in Python/CPython bigint-backed Boolean-ring
representation for degree <=3 (optionally <=4), with combinadic colex indices,
canonical conversion to SymQ's immutable ANF, and a strict \`PhaseProgram\`
interpreter. There is **no dependency on external or private repositories**,
no change to the public backends, and no automatic fallback. The integer
bitset XOR, bit_count and long-integer storage are native CPython operations;
monomial-pair multiplication remains in Python and is *not* a native C
multiplication engine.

## Accepted semantics

\`evaluate_phase\` accepts only the validated existing sign-phase/HMR grammar,
with data inputs free and every ancilla initialized to zero. Each HMR receives
a fresh outcome variable (even for repeated measurements on the same wire);
phase and wire values are separate polynomials. The sign semantics is
\`(-1)^(phase)\`. The resulting O1/O2 checks are the **restricted branch-exact
preconditions**, not a full quantum-channel theorem. Standalone H, arbitrary
reset, classically conditioned X/CX, S/T, Z measurements and arbitrary
rotations are outside the grammar, and cannot be silently interpreted.

Multiplication uses canonical Boolean-ring monomial union with GF(2) XOR
cancellation. A product generating even one monomial beyond declared degree
**raises ResourceLimitExceeded**, not an approximate polynomial. The exact
identity \`f*f=f\` avoids unnecessary high-degree intermediate materialization.
Term, capacity and whole-call deadlines are fail-closed; max_nodes is rejected
because this pilot does not allocate ZDD nodes.

## Evidence and promotion

Tests compare the accepted programs with SymQ's independently implemented
unbounded sparse ANF phase interpreter; independently enumerate products and
small assignments, and reject overflow, dirty outputs, missing CZ phase
correction and invalid resource configurations. The 126-event HMR test does
not enumerate outcome assignments. Benchmarks may be run explicitly via

\`\`\`bash
python -m pytest -q tests/test_bitset_degree3_research.py
python -m research.bitset_degree3.benchmark
\`\`\`

This small benchmark measures full-call wall time and Python allocations,
**not RSS**, and is not itself a promotion benchmark. Native C optimization
requires an A/B profile against \`sparse\`, \`zdd\`, the existing \`packed\`
and \`zdd-native\` on matching semantics and *real*, licensed fragments.
Evaluate CPU/RSS, cache behavior and held-out families before implementing
or claiming a C acceleration. A reference oracle cannot be called a
Kaggle/physical circuit or quantum-channel certification without separate
input-domain, phase and coherence proofs.

Remaining #86 track: legal-domain coefficient bitsets and small dual GF(2)
certificates, in separate independently evaluated milestones. No backend or
default verifier is changed by this pilot.
