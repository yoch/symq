# Related work for paper A (verified on 27 Oct 2026)

Every bibliographic fact below was checked against a primary source: the arXiv abstract page
(`https://arxiv.org/abs/<id>`), the Crossref record of the DOI, the publisher page, or the
project's repository/PyPI page. BibTeX: `paper/references.bib`. Quotes are from the PDFs or
READMEs named. "Not verified" marks what we could not check.

## Positioning in one table

| work | object | representation | exact? | relation to symq (paper A) |
|---|---|---|---|---|
| PolyBoRi / BRiAl (Brickenstein & Dreyer, JSC 44(9) 2009, doi 10.1016/j.jsc.2008.02.017; BRiAl 1.2.15, GPL-2.0+) | Gröbner bases over Boolean polynomials | ZDD of the monomial family | yes | **Same representation and recursion family.** Used as a baseline through passagemath-brial 10.8.13. We claim no novelty over it. |
| Minato (DAC 1993, doi 10.1145/157485.164890; ED&TC 1995, doi 10.1109/EDTC.1995.470321; STTT 3(2) 2001) | ZDDs; polynomials as ZDDs | ZDD | yes | Origin of the data structure and of polynomial manipulation with ZDDs. |
| Brickenstein, Dreyer, Greuel, Wedler, Wienand (arXiv:0801.1177, 2008) | Boolean Gröbner bases for formal verification of circuits | ZDD | yes | Prior use of the same representation for circuit verification. |
| CUDD 3.0.0 (Somenzi; BSD-3) via `dd` 0.6.0 (Caltech, BSD-3) | BDD/ADD/ZDD package | BDD (Shannon cofactors); ZDD products on covers | yes | BDD baseline. CUDD's ZDD products are cover products, not GF(2) sums, so no ANF ring. |
| Bryant (IEEE TC C-35(8) 1986) | ROBDDs | BDD | yes | Background. |
| MQT QCEC (Burgholzer & Wille, TCAD 40(9) 2021, arXiv:2004.08420; Software Impacts 7 2021; repo MIT, v3.11.0) | equivalence of quantum circuits | decision diagrams of unitaries, simulation, ZX | complete with the alternating checker; simulation is not a proof | Context baseline: on X/CX/MCX circuits, unitary equality = functional equality, but QCEC computes no polynomial. Restricted to its alternating checker so every verdict is a proof. |
| Wille, Große, Miller, Drechsler (ISMVL 2009, doi 10.1109/ISMVL.2009.19) | equivalence of reversible circuits | DDs and SAT | yes | Closest classical prior work on our exact question; not run (no available implementation was evaluated). |
| RevLib (Wille et al., ISMVL 2008) | benchmarks | — | — | The QCEC test circuits carry RevLib-style names (e.g. `rd84_313`); we did not verify their provenance and import them from QCEC's repository (MIT). |
| Viamontes, Markov, Hayes (ICCAD 2007, arXiv:0705.0017) | quantum circuit/state equivalence | decision diagrams | yes | Background. That it uses QuIDD is *not verified* from the abstract. |
| Amy (QPL 2018, EPTCS 287, arXiv:1805.06908) | functional verification of Clifford+T | path sums: Boolean output polynomials + phase polynomial | yes (rewrite system; complete for Clifford) | For reversible gates, a path sum's output signature *is* our ANF. Paper A adds nothing to path sums; paper B (phases) must position against them. |
| Amy, Maslov, Mosca (TCAD 33(10) 2014, arXiv:1303.2042) | T-depth optimisation of {CNOT,T} | linear Boolean functions with phases | — | Phase-polynomial background (the phrase itself does not occur in the PDF). |
| QuPRS: Huang, Chareton, Chen, Chung, Hsieh, Laarman, Mei (TACAS 2026, LNCS pp. 419–439, doi 10.1007/978-3-032-22749-2_21, arXiv:2604.24504) | quantum circuit equivalence | path-sum reduction + weighted model counting | complete up to global phase | Different gate set and question; no matched comparison possible for paper A (issue #17 stop rule). |
| FeynmanDD: Wang, Cheng, Yuan, Ji (CAV 2025, LNCS 15934, arXiv:2509.08276) | path-integral analysis and equivalence | BDDs/MTBDDs for counting | yes | Classical decision diagrams over path polynomials; different question. |
| Irene: Ke, Li, Li (arXiv:2609.36065, cs.PL, 28 Sep 2026; code github.com/WindOctober/Irene, no license) | equivalence of bounded hybrid quantum programs | hybrid path sums; Boolean expressions as XOR–AND graphs; SMT for residuals | yes (bounded) | **Most threatening prior work for the representation choice:** "represents Boolean expressions as XOR–AND graphs (XAGs), retaining nested XOR and AND operations rather than distributing products into algebraic normal form (ANF)"; uses ZDDs "to count ANF monomials without enumerating them"; > 6 GiB explicit ANF on 30 solved pairs. Supports our negative multiplier result; we do not compare performance (different semantics). |
| Ricciardi, Bardin, Chareton, Valiron (arXiv:2511.22523, 2025) | hybrid → unitary equivalence | deferred measurement, path sums | — | Paper B context. |
| Hong, Feng, Li, Ying (ICCAD 2022, doi 10.1145/3508352.3549479); Burgholzer & Wille (DAC 2022, doi 10.1145/3489517.3530482) | dynamic / non-unitary circuits | DDs | — | Paper B context. |
| Kliuchnikov, Paetznick, da Silva, "Phased outcome-complete simulation" (arXiv:2603.24717, Mar 2026); Kliuchnikov, Beverland, Paetznick (arXiv:2309.08676) | equivalence over all inputs and outcomes, with exact global phase | stabilizer / phased outcome-complete | yes | **Most threatening prior work for paper B**: lists "custom compilation strategies for reversible circuits such as adders, multipliers, and table lookups" among applications. Out of scope of paper A. |
| Mahzoon, Große, Drechsler (RevSCA-2.0, TCAD 41(5) 2022); Kaufmann & Biere (STTT 25(2) 2023); Kaufmann & Berthomieu (TACAS 2025, arXiv:2411.16348) | algebraic verification of multipliers (AIGs) | polynomials, Gröbner bases, rewriting | yes | They fight the monomial blow-up we hit on multipliers, with techniques we do not use. Not run (AIG input, different problem). |
| Gidney (Quantum 2, 74, 2018); Jones (PRA 87, 022328, 2013); Luongo et al. (arXiv:2407.20167); Jeon, Huang, Cai (arXiv:2609.31605) | measurement-based uncomputation | — | — | Paper B context only. |
| `andigu/uncompute` (Apache-2.0) with Gu, Kemeny, Yelin, Lukin (arXiv:2610.22367) | exact "kickmix" evaluator + Lean 4 proofs | per-shot classical simulation | yes | Paper B: the natural source of real HMR programs and an independent exact evaluator. |

## What a reviewer will ask, and our answers

1. *"This is PolyBoRi."* — Yes for the representation and the recursion; the paper says so in
   the abstract. The contribution is a specialised engine and a controlled comparison.
2. *"Your PolyBoRi driver is Python."* — Yes, for every tool. We report it as the main threat
   and show that removing Python per-call overhead gains nothing for symq itself
   (fused vs minimal loop 0.97×), which bounds the effect for symq but not for PolyBoRi.
3. *"Why not compare with Irene/QuPRS/FeynmanDD?"* — Different questions (hybrid programs,
   global-phase equivalence, path integrals). Issue #17 forbids unmatched comparisons.
4. *"Why not Wille et al. 2009?"* — No implementation was evaluated; their DD approach is
   represented by CUDD BDDs, their SAT approach is not.
5. *"Is anything novel?"* — Not algorithmically. The defensible novelty is empirical: the
   matched comparison and its negative results.

## Search for closer prior work (not exhaustive)

- arXiv API searches combining "algebraic normal form", "reversible", "circuit", and
  "Reed-Muller", "reversible", "verification" returned no paper on symbolic simulation of
  reversible circuits in ANF (27 Oct 2026). This is weak evidence of absence.
- Not searched: IEEE Xplore and ACM DL full text (fetches returned 403), Google Scholar.
