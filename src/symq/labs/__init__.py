"""Installed research modules with **no API promise**.

Everything under ``symq.labs`` is exact and tested, but its interfaces may change or disappear
between any two versions. These modules build on the maintained classical package and on the
opt-in ``symq.experimental`` core; nothing outside ``symq.labs`` depends on them.

| Module | Content |
| --- | --- |
| ``dyadic_phase`` | exact phases modulo ``2**k`` (``DyadicPhaseProgram``) |
| ``cyclotomic`` | bounded exact cyclotomic channel reference |
| ``qcec_adapter`` | optional MQT QCEC unitary adapter for the dyadic/cyclotomic grammars |
| ``classical_transcript`` | transcript-bound classical substitutions |
| ``channel_composition`` | transcript-bound local channel/instrument substitutions |
| ``rewrite`` | shared rewrite core: outcomes, declared weights, cost reports, receipts |
| ``contextual_substitution`` | classical rewrites at a span under a contract (SAT or total) |
| ``hybrid_substitution`` | bounded local coherent channel/instrument rewrites |
| ``rewrite_request`` | request/report format behind ``symq rewrite`` and ``symq replay`` |
| ``bilinear_substitution`` | proved GF(2^n) multiplier rewrites on a wire map |
| ``gf24_tower`` | the 99-product GF(16)-tower factorization of GF(2^24) |
| ``gf24_order`` | the pinned 2634-CX factor order for that tower |
| ``gf24_choice`` | choice among three GF(2^24) multipliers under declared weights |
| ``ledger`` | phase-debt ledger |
| ``proof_graph`` | versioned obligation DAG with a replaying kernel |
| ``rename`` | renamed-half reuse for the full-channel checker |
| ``qasm3`` | strict OpenQASM 3 hybrid subset |
| ``importers`` | strict hybrid phase-stream importer |
| ``qualtran`` | pinned Qualtran fixture import |
| ``xag`` | analyses of GF(2^n) multiplier decompositions (incidence bound, proofs, costs) |
| ``bitset_anf`` | degree-bounded integer-bitset ANF for sign/HMR programs |
| ``finite_domain`` | finite outcome-domain evaluation |
| ``linear_certificate`` | GF(2) dual certificates of infeasibility |
| ``hmr_repair`` | synthesis of late HMR phase repairs |
| ``verification_contracts`` | explicit contract-grammar prototype |
| ``corpus_qualification`` | classical corpus qualification harness |
"""
