# Source-bound phase certificate discovery (research, outside the #159–#162 audit)

This work is isolated on #161's exact HEAD
`2f992a61a0cf0a60a9e1204ccb2c4c4cd79384d2`. It does not alter the four branches
being audited or the existing certificate checker. It is not authorized to merge.

## Problem and algorithm

For frozen real dyadic programs L/R, a strict source dephaser D and an affine
support, extract the effective signature h and delta=phi_L-phi_R modulo 2^k.
Restoration and equal outputs are checked first. Seek Boolean bit functions
b_j in the span of a **declared finite monomial dictionary M** over h such that
`delta(x)=sum_j 2^j*b_j(h(x)) mod 2^k`.

One GF(2) interpolation system is shared by every phase bit. Its rows are feature
values `v(h(x))` and its RHS is the whole k-bit source delta. Free coefficient
variables are set to zero to choose a deterministic candidate. The existing
Boolean DAG/SAT algebra searches for any bit violation; a separate scalar source
interpreter verifies the returned signature and delta before adding an equation.
Source semantics and the phase DAG are prepared once, rather than rerunning
extraction at every refinement. The candidate is NOT trusted: positive results
require a fresh run of the unchanged #161 checker on detached source objects,
with source identity equality and the same absolute deadline.

CEGIS and Boolean functional synthesis are prior art, not new claims here:
[Combinatorial sketching, ASPLOS 2006](https://research.ibm.com/publications/combinatorial-sketching-for-finite-programs),
[MIT CEGIS lecture](https://people.csail.mit.edu/asolar/SynthesisCourse2020/Lecture10.htm),
[Counterexample-guided knowledge compilation, CAV 2023](https://link.springer.com/chapter/10.1007/978-3-031-37706-8_19).
The scoped contribution is source-bound, aggregate phase discovery with shared
multi-bit interpolation and explicit, checkable failure semantics.

## Rank progress and constructive negative results

Every candidate satisfies all observed rows. A refuting new row therefore either
increases the feature-matrix rank or proves the augmented system inconsistent.
For t dictionary features, there can be at most t independent refinements, then
one concluding verifier call (resource bounds can stop earlier). All k phase
bits are learned together, so the algebraic rank bound is t, not k*t. This is a
bound on refinement count, not runtime: the SAT calls and source extraction can
still be expensive, and the dictionary itself may be exponentially large.

An inconsistent row keeps an XOR combination of concrete source samples:
`XOR feature_rows = 0` while `XOR source_delta_labels != 0`. Re-executing those
samples and checking the two XORs certifies **no candidate in the stated dictionary**.
It does not establish channel inequivalence: a higher-degree dictionary may work.
If two source samples have exactly the same effective signature and distinct
source deltas, they instead witness a genuine surviving-coherence difference.
That is a different outcome and both physical inputs are replayed.

## Status and trust contract

- `proved`: discovered candidate AND fresh unchanged-checker verification succeed.
- `dictionary_exhausted`: finite source-replayed obstruction to the chosen dictionary only.
- `different`: literal output mismatch, or same-effective-signature/different-phase pair.
- `not_proved`: source dephaser restoration does not meet this supported theorem.
- `inconclusive`: time/terms/rounds/dictionary/graph/clause cap; no decisive evidence retained.
- `unsupported`: SAT unavailable. Malformed closed inputs raise instead of weakening the claim.

The image support is declared, not proved prepared externally. All quantum outputs
are retained, classical outcomes forgotten; no coherently controlled substitution.
No independent UNSAT proof kernel, portable replay receipt or optimal-certificate
size guarantee. Private source helpers are reused only as labs research.

## Evidence at this checkpoint

The pure multi-RHS elimination kernel was executed locally on 5,760 seeded random
systems (width1..9, RHS bits1..8). All returned solutions satisfy all observed rows;
all 5,710 contradictions have zero XOR feature row and nonzero XOR label. The 50
remaining runs are consistent. This does **not** test installed SymQ, Glucose,
source extraction or channel semantics. Source-bound tests and dedicated CI are
required before any end-to-end validation claim.
