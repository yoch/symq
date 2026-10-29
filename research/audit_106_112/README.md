# Independent audit fixtures for the seven-PR SymQ research stack

Source under review: PR #112 HEAD `9a1825da91d2811e1f53c73bee398ca3a41507f3`.
This branch adds **only** a strict-expected-failure test file and an audit workflow;
none of PRs #106--#112 is modified or merged by publishing these fixtures.

Six strict xfails are grouped as:
- **P1** `VerificationSession` / `check_equivalence_by_blocks`: inherited remaining duration loses elapsed time twice;
- **P1** `classical_transcript.verify_transcript`: child clock re-anchors remaining seconds at parent epoch;
- **P1** `run_isolated`: blocking parent `recv()`/pickle reconstruction can exceed the advertised hard whole-call wall duration;
- **P2** `affine_event_factor`: sparse nonlinear event term whose coefficient is 0 modulo 8 causes `KeyError` instead of vanishing (two concrete values);
- **P2** `inspect` for `hybrid-exact`: width 7 is advertised supported even though public `verify` refuses it at the oracle's default width 6.

Two positive controls preserve correctly supported exact cases.

A CI run showing **6 xfailed, 2 passed** confirms the defects remain;
this is not a successful soundness run. After fixes, remove the strict
xfail decorators and require all eight ordinary tests to pass.
`test_hard_wall_binds_parent_result_decoding` may skip if a very slow
CI runner prevents the worker from delivering before the deadline;
if so, rerun isolated with a more generous wall and a proportionately
slower parent decoder.

Do not use this audit as evidence of false quantum-channel EQUIVALENT
results; the reproduced problems are deadline coverage, error handling
and capability reporting. Complete the physical coherent-domain tests
and native fuzz separately before any promotion.
