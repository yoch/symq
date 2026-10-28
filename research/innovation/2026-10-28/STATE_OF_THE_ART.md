# State of the art and novelty matrix -- 28 October 2026

Verified against repository HEAD `aaff35f` and the sources below. Nothing in this file is
allowed to call a mechanism "new" without the citation that shows what it would be new *to*.

## 1. The baseline the project already has

`symq` today: exact symbolic simulation in `GF(2)[x]/(x^2-x)` with monomial ZDDs; a native C
core (hash-consed unique table, three-product recursion, lossless operation cache, per-node
monomial counts, budgets); interchangeable Python/PolyBoRi/CUDD backends; an exact checker with
concretely re-checked counterexamples; and a verified measurement fragment (`src/symq/phase.py`)
with X-basis measure-and-reset, single-outcome Z feedback and two obligations (O1 clean ancillas,
O2 phase independent of outcomes).

None of that is a new algorithm. It is a careful implementation of known ones.

## 2. Prior art, per candidate mechanism

### 2.1 Monomial ZDDs and their ring operations

| source | what it establishes |
|---|---|
| Minato, *Zero-suppressed BDDs for set manipulation*, DAC 1993 | the diagram and its canonicity |
| Minato, *Implicit manipulation of polynomials using ZDDs*, 1995 | polynomials as ZDDs, recursive ring operations |
| Brickenstein & Dreyer, *PolyBoRi*, JSC 44(9), 2009 | Boolean polynomials as monomial ZDDs; the production implementation, including the recursive product with parity cancellation |
| Brickenstein et al., *Gröbner bases for circuit verification*, 2008 | applies the same representation to circuit verification |

**Consequence.** The representation, the product recursion and the use for circuit verification
are all prior art. `symq`'s product is Brickenstein–Dreyer's recurrence. No claim of novelty is
available at this level.

### 2.2 Variable ordering, sifting, GC, computed tables

| source | what it establishes |
|---|---|
| Somenzi, *CUDD manual*, 2015 | dynamic reordering (sifting and variants), garbage collection over the unique table, computed-table management with lossy resizing |
| Bryant, *Graph-based algorithms for Boolean function manipulation*, 1986 | ordered BDDs; the ordering question itself |

**Consequence.** Reordering, GC and bounded caches are standard in the reference package.
Reimplementing any of them is engineering. What is *not* settled is whether a cheap,
structure-derived order can be predicted for reversible circuits; see §2.6.

### 2.3 Equivalence checking of reversible circuits

| source | what it establishes |
|---|---|
| Wille, Große, Miller, Drechsler, *Equivalence checking of reversible circuits*, ISMVL 2009 | miter construction plus SAT for reversible circuits |
| Brayton & Mishchenko, *ABC*, CAV 2010; Mishchenko et al., *FRAIGs*, 2006 | combinational equivalence checking by SAT sweeping on and-inverter graphs |
| Burgholzer & Wille, *Advanced equivalence checking for quantum circuits*, TCAD 2021; QCEC | decision-diagram, simulation and ZX checkers for the unitary question |

**Consequence.** The miter idea -- compose `L` with `R^{-1}` and ask whether the result is the
identity -- is prior art, and the SAT formulation of it is decades old. Anything `symq` gains
from a miter must be argued at the level of the *representation* (what the intermediate
polynomials look like), never presented as a new equivalence-checking method.

### 2.4 Measurement-based uncomputation and phase handling

| source | what it establishes |
|---|---|
| Gidney, *Halving the cost of quantum addition*, 2018 | measurement-based uncomputation as a primitive |
| Amy, Azimzadeh, Mosca, *On the CNOT-complexity of CNOT-PHASE circuits*, 2019 (path sums) | the phase polynomial carried alongside the Boolean wire functions |
| Kliuchnikov et al., *Phased outcome-complete stabilizer simulation*, 2026 | outcome-complete simulation with phases; explicitly lists reversible adders and multipliers |
| Hong et al., 2022; Burgholzer & Wille, 2022; Ricciardi et al., 2025 | dynamic/hybrid circuit equivalence with measurement and feed-forward |
| Ke et al., *Irene*, 2026 | hybrid-program equivalence by structure-preserving symbolic reduction over XOR–AND graphs; reports that explicit ANF would exceed 6 GiB on 30 of its pairs |

**Consequence.** Factoring the phase as `phi0(x) + sum_j m_j g_j(x)` is *not new as an
identity*: it is the normal form of a phase polynomial that is affine in the outcome variables,
and every tool above that handles measurement already carries the equivalent information. It is
new here only if it buys a decision procedure with a better cost, or accepts a class the others
reject.

### 2.5 Algebraic verification of arithmetic circuits

Mahzoon et al. (RevSCA-2), Kaufmann et al. (Amulet-2, linear-relation extraction) attack the
same monomial blow-up with backward rewriting and vanishing-monomial elimination, on
and-inverter graphs. They are not applied to reversible circuits in the sources read, but their
*technique* -- do not expand what can be cancelled first -- is exactly the kind of thing a
proposal here would have to be compared against.

## 3. Candidates considered and their status

| candidate | prior art? | what would be new | verdict after the pilots |
|---|---|---|---|
| A. Factored HMR phase + outcome-free channel criterion | identity: normal form, prior art; **criterion: not found in the sources read** | deciding channel equality by two Boolean-function comparisons over pair variables, with no `2^M` enumeration | **new criterion, but no demonstrated practical need** (`PILOT_A.md`) |
| B. Equivalence by simulating the composed circuit | miter: Wille 2009, ABC | that the *ANF* intermediate stays proportional to the difference | **real but modest effect on structured circuits** (`PILOT_B.md`) |
| C. GC over the native unique table | CUDD | nothing | **justified engineering**: 99.6-99.8 % dead (`PILOT_C.md`) |
| D. Native width > 64 | none needed: Python backend and block decomposition already exist | nothing demonstrated | **not started**: no connected circuit identified that needs it |
| E. Decomposition with proof obligations at interfaces | structural decomposition and SAT sweeping exist | a reversible/ancilla-specific obligation | **not started**: no concrete primitive identified yet |

## 4. What this document forbids

* Calling the factored phase a new representation.
* Calling the composed-circuit simulation a new equivalence-checking algorithm.
* Calling a collector a scientific contribution.
* Claiming any of these is novel against CUDD, ABC, QCEC or Irene without an experiment that
  compares the same predicate on the same instances.
