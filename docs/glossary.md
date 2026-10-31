# Glossary

**ANF (algebraic normal form).** The unique square-free polynomial over GF(2) representing a
Boolean function: XOR is addition, AND is multiplication, and `xᵢ² = xᵢ`. Equal functions have
identical ANFs, which makes symbolic comparison exact.

**Monomial mask.** An integer whose bit `i` set means variable `xᵢ` occurs in the monomial.
Input assignments use the same LSB-first convention: bit `i` is the value of wire `i`.

**ZDD (zero-suppressed decision diagram).** A shared, hash-consed DAG representing a family of
monomials. The **unique table** guarantees one node per `(level, lo, hi)` triple; the **operation
cache** memoises XOR and product results.

**Native core.** The optional C extension behind `zdd-native` (64 variables) and
`zdd-native-wide` (128 variables).

**Budget, guard, session.** A `Budget` declares limits (`max_terms`, `max_nodes`, `max_seconds`).
A `Guard` is a running budget whose clock starts at construction. A `VerificationSession` shares
one whole-call deadline and resource reservations across nested engines. Deadlines are
cooperative; only an isolated subprocess enforces hard CPU, wall and memory limits.

**Witness.** A concrete input on which two programs differ. Every negative verdict carries one, and
it is replayed by concrete execution before it is returned.

**Inconclusive.** A computation that stopped (budget, unsupported case, solver limit) without a
verdict. It never establishes equivalence or non-equivalence.

**Miter.** The SAT encoding of two circuits with shared inputs and a clause stating that some
observed output differs. UNSAT means equivalent for that contract.

**Contract (SAT).** Input constants, observed outputs, restored wires and an optional output map;
see the [SAT guide](guide/sat.md).

**Restored wire, dirty (borrowed) ancilla.** A restored wire must end with its own initial value,
whatever that value was. A dirty ancilla starts in an unknown state and is never silently assumed
to be `|0⟩`.

**Relational composition.** Proving `A;B` against `A';B'` from a relation `R` on the cut states and
four SAT obligations, instead of one monolithic miter.

**HMR.** Unconditional X-basis measurement followed by reset of a wire. In a
`symq.phase.PhaseProgram` each HMR produces a fresh outcome variable `mⱼ`.

**Sign phase.** A phase `(−1)^φ(x, m)` with `φ` a Boolean polynomial, produced by Z-type gates
(`z`, `cz`, `mcz`) and outcome-controlled corrections (`mcz_if`).

**O1, O2.** The strict branch obligations of the [HMR specification](reference/phase-hmr-spec.md):
O1 (clean ancillas) requires every ancilla output to be zero; O2 (outcome independence) requires
the phase polynomial not to depend on any outcome variable. Together they imply the program applies
one unitary on its data wires for every outcome sequence.

**Full channel.** Equality of the physical outcome-forgotten channel on every coherent input pair
`|x⟩⟨y|` of the data register, with all quantum outputs retained.

**Reduced channel.** Equality after tracing out the outputs not listed in an explicit ordered
output map. Equality after tracing does not imply full-output equality.

**Instrument.** Equality of the channel together with selected recorded classical outcomes.
Channel equality does not imply equality of observed measurement records.

**Coherent domain.** The set of data inputs over which a channel theorem quantifies: a full cube,
an affine subspace, a Boolean predicate or the image of a reversible preparation.

**`hybrid-exact`.** The bounded exact Kraus/CPTP reference oracle of `symq.experimental.hybrid`,
independent of the symbolic engines.

**Phase debt.** An uncorrected outcome-dependent phase left by a local rewrite, tracked by the
experimental ledger until a later correction discharges it.

**Transcript, clean cut.** In local composition, the pinned sequence of operations around a
substituted block, and a cut where the ancillas are proved to be in their prepared state.
