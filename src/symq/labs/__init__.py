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
