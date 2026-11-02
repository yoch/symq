# Phase discovery: first installed-package checkpoint

Checkpoint HEAD `3b893281eafed9f2ec184899fda14b31c6cdd2e0`, tree
`3e0463094836f67a183b1bbafaee9deea71b9b1b`, based on #161 at
`2f992a61a0cf0a60a9e1204ccb2c4c4cd79384d2`.
CI synthetic merge: `319ddc5a19d1dfbed61301a31fdd61c7a035b95e`.

[Dedicated qualification](https://github.com/yoch/symq/actions/runs/41479219888)
passed Ruff, source-bound discovery tests and the unchanged phase-bit checker tests,
then the full 512-row development campaign. Artifact 13158198026 was downloaded;
ZIP SHA-256 `896fef8c843a7f2429094ce13ec2f989e44d2565faad659be0b297e4ecc2c56b`
matches the GitHub API. Its commit/tree match the values above.
Engine SHA-256 `70a2d715b6d680f7e99246414592a8eedf0f1c2959fc7c18dcc7f1ccefd52fe5`
and harness SHA-256 `6e6f0694cfd01183de5f77ec400c234dc93b49cfe547cee188c9fca95229fa08`
match the exact local/published bytes. The five inherited source/oracle digests
match #161's downloaded artifact; the new diff leaves all five files unchanged.

## Outcomes actually checked

For every one of 256 functions h=(ab,bc)->Z/4, test the degree1 and degree2
dictionaries. All 512 rows qualify against independent exact channel checks:

- Degree2: 256 discovered certificates, internally freshly checked and externally
  rechecked with the unchanged #161 checker; at most5 refinement/verifier rounds.
- Degree1: 64 discovered certificates; 192 exact finite dictionary obstructions.
  The 192 cases are nevertheless equivalent channels and become proofs at degree2.
  Each obstruction is checked against literal sample signatures/phase table and
  the zero-row/nonzero-label XOR identity, not by trusting the learner's status.

The combined development campaign took3.558 seconds on the recorded CI runner.
This is not a paired speed comparison or a holdout. The JSON retains every row,
source identity, result, fresh recheck and any failure; there were no failures.

Three deliberately sparse phase families with8,24,48 input/signature bits each
needed4 source counterexamples,4 SAT calls and5 rounds, including fresh success.
For48 bits:54 graph nodes,16 clauses, approximately0.00391 seconds including the
fresh check. Those inputs were quantified symbolically, not enumerated. The
family only uses three simple phase bits; this is not a general48-bit benchmark.

Unit tests also require real same-signature/different-phase refutations, output
mismatch, closed option types, absent SAT, shared caps, refused/forged fresh checks
and mutation of caller objects after snapshot. Additional three-signature, offset,
unreachable-word and late-deadline regressions are added in a later commit and
must receive their own exact-head CI validation, not inherit this checkpoint.

The pure interpolation kernel was additionally checked locally on5760 seeded
systems. No local installed SymQ/PySAT/full-suite result is claimed. The new work
stays outside the independent audit batch #159–#162, and no branch is merged.
