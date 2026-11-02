# Nonlinear phase-bit certificate: initial installed-package qualification

Exact research checkpoint: `d2f1f410feb76f605f589eaf9a103e6cea11f5b0`, stacked on
#160 at `9fb2996dcde790bb6ce5bdc64b4d1a40fb132cbb`.
Synthetic merge: `e4bb6511f491017d687c579abb4c3ff5dc5dc3a0`;
Git tree: `b92e1e98075a9d11505590cee8a83743fc6e641f`.

[Dedicated CI](https://github.com/yoch/symq/actions/runs/41461851534) passed lint,
the source-bound tests and graph tests, then the public development campaign.
Downloaded artifact 13148424404 has SHA-256
`67b8f7eef501294dc973c9299a1049c48e027d0a2e4ad8d5c8311d14086fb333`, equal to the API
digest. The archive records the commit/tree above and source identities.
Engine SHA-256: `5f0c2df30a089d9d256d15dc707c4d1a40b093bdd76d48c5ac67f95635a5f08c`.
Harness SHA-256: `e786a609212b36733828a2b0c74ad04cfce0b19dd040a1af3e308933b1e9f35b`.

Python 3.12.15. All 256 functions from the two-coordinate effective signature
h=(ab,bc) to Z/4 are certified, and all 64 coherent matrix units per function
are confirmed by the independent exact Kraus/cyclotomic oracle: 16,384 positive
matrix-unit comparisons. Four additional source-phase mutations are refused and
confirmed different by the oracle; their short-circuited negative searches are
not counted as 64 completed matrix units each. The campaign took 2.972 seconds
on the recorded CI runner; this is not a scaling or comparative-speed claim.

Unit tests additionally cover aggregate cancellation (neither individual predicate
factors), wrong candidates for channels that actually ARE equivalent, output
mismatches, effective signature changes after feedback, mixed precision and
negative angles, invalid certificate types, shared budget refusals and explicit
absence of the integer modular-lifting helper.

The implementation checks a supplied witness; it does not synthesize one and
must never interpret candidate failure as inequivalence. Certificate and sources
are hashed but no portable proof-kernel/replay guarantee is claimed. Extraction
can still expand Boolean ANFs; SAT UNSAT relies on the encoder/solver.

See [the contract and algorithm](../labs/nonlinear-phase-bits.md). Independent
semantic/adversarial audit remains necessary before integration; no stable API
or default engine changed. Later documentation-only commits retain the executable
source hashes, but their own CI status must still be checked separately.
