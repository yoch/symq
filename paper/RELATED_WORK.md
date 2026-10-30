# Related work and claim boundaries

Critical primary sources were re-read on 30 October 2026. The bibliography's
older entries retain their original metadata; this review is not an exhaustive
priority search. No absence-of-prior-work claim is inferred from search results.
No timings published by another paper are compared directly with this machine.

| Work and primary source | Established object/approach | Relation to SymQ and comparison boundary |
| --- | --- | --- |
| [PolyBoRi, Brickenstein–Dreyer 2009](https://doi.org/10.1016/j.jsc.2008.02.017); [BRiAl](https://github.com/BRiAl/BRiAl) | Boolean polynomial arithmetic and Gröbner bases represented by monomial ZDDs | Same core representation and recursive Boolean-ring operations; no representation or multiplication novelty claimed. Comparable for Boolean simulation/ANF materialization when interfaces and exports match |
| [Minato, ZDDs 1993](https://doi.org/10.1145/157485.164890), [polynomial manipulation 1995](https://doi.org/10.1109/EDTC.1995.470321), [survey 2001](https://doi.org/10.1007/s100090100038) | Canonical ordered set-family diagrams and polynomial manipulation | Foundational prior art; implementation specialization is distinct from an algebraic theorem |
| [CUDD 3.0.0](https://github.com/cuddorg/cudd), [dd](https://github.com/tulip-control/dd) | Shannon BDDs, ADDs and cover ZDDs | BDD functions can answer Boolean equivalence without expanding ANF. CUDD's cover-product API is not already a GF(2) polynomial ring; unavailable CUDD-ZDD adapters must be reported, not simulated by another backend |
| [Wille et al., ISMVL 2009](https://agra.informatik.uni-bremen.de/doc/konf/09_ismvl_rev_ec.pdf) | DD and SAT formulations for reversible equivalence, including constants/garbage specifications | Direct prior art on functional equivalence. Their reported timings do not transfer to this environment. A current SAT baseline must use the identical input/output contract |
| [ABC](https://people.eecs.berkeley.edu/~alanmi/abc/), Brayton–Mishchenko CAV 2010 | AIG optimization, SAT sweeping and combinational equivalence | A practical verdict-only competitor. A PySAT miter is a qualified SAT baseline, not an ABC implementation and not an ANF materializer |
| [MQT QCEC](https://github.com/munich-quantum-toolkit/qcec); Burgholzer–Wille 2021 | Quantum equivalence with a configurable checking portfolio | On the common reversible unitary fragment, functional equality agrees with matrix equality; only conclusive configured results count. No ANF output service, no transfer of a unitary adapter's guarantee to dynamic circuits |
| [Irene, arXiv:2609.36065v1](https://arxiv.org/html/2609.36065v1) | Bounded hybrid programs; factored XOR–AND graphs, hybrid path sums, observable density kernels and SMT residual obligations | Strong prior work for hybrid semantics and avoiding premature ANF expansion. Its broader grammar is not a matched classical ANF benchmark. No universal completeness/performance claim is imported into SymQ |
| [QuPRS, arXiv:2604.24504v1](https://arxiv.org/abs/2604.24504v1), [TACAS 2026 DOI](https://doi.org/10.1007/978-3-032-22749-2_21) | Path-sum reduction combined with weighted model counting; equivalence up to global phase | Broader unitary verification. A phase convention and common gate grammar would have to be fixed before an empirical comparison |
| [Phased outcome-complete simulation, arXiv:2603.24717v1](https://arxiv.org/abs/2603.24717v1) | Exact phase tracking for stabilizer circuits with corresponding symbolic rotations and outcome mappings | Prior all-input/all-outcome reasoning, including conditional Pauli corrections. It is not interchangeable with forgotten-outcome channel equality; SymQ claims no first such semantics |
| [Ricciardi et al., arXiv:2511.22523v1](https://arxiv.org/abs/2511.22523v1) | Deferred measurement lifting plus separation/projection for hybrid equivalence | Relevant hybrid competitor; a classical verdict does not exercise its broader channel problem |
| Amy path sums; Hong et al. dynamic circuits; Burgholzer–Wille nonunitaries | Exact symbolic quantum and hybrid checking | Context in `references.bib`; no claim that this classical engineering study supersedes them |
| OFDD/positive Davio/Reed–Muller representations; ReVerC | Known diagram/Boolean expansion relationships and verified reversible compilation | No new diagram or compiler correctness theorem; only scoped implementation and measurement claims |
| RevSCA/AMulet2/algebraic AIG verification | Backward rewriting, SAT and algebraic reduction of multiplier problems | Motivation for adverse forward-ANF examples; a different input/model is not a matched timing comparison |

The full Irene source was checked for its factored-XAG and density-kernel model;
the four 2025/2026 arXiv version pages were checked for title, authors and scope.
Wille's primary seven-page paper was checked for its DD/SAT and contract scope.
The ABC official project page was accessible but exposed no readable text through
the browser extractor; its algorithmic positioning is supported by the cited
CAV/ICCAD papers, not by invented implementation details. Publisher redirects
for some older DOIs were inaccessible during this refresh; those metadata were
retained rather than silently described as newly verified.

## Non-comparisons are explicit

A returned Boolean verdict, an exported ANF and a quantum channel proof are
separate services. Irene/QuPRS/phased simulation are cited for prior art and
semantic boundaries, not as timed competitors unless a future adapter establishes
an identical theorem. The manuscript's classical qualification does not assert
new mathematics or a first hybrid checker. Code, licenses and redistributable
benchmark data must be verified separately before any import; a paper citation
alone grants no redistribution permission.

Software license refresh: the BRiAl `LICENSE` explicitly states GPL version 2 or later;
`dd` carries the three-clause Caltech BSD terms; CUDD metadata identifies BSD-3-Clause
and QCEC metadata identifies MIT. GitHub `NOASSERTION` for BRiAl/dd is not absence
of a license. No code or data was imported from these repositories for this revision.
