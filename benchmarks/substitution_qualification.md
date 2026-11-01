# Substitution qualification matrix (existing public + synthetic)

The standalone [runner](substitution_qualification.py) evaluates the existing
classical transcript, relational SAT and restricted coherent-channel
composition theorems on **28 explicitly labeled tasks**. It is not yet a
benchmark of an automatically discovered optimization pipeline, and it is not
an external comparison with QCEC or PyZX.

## Data taxonomy

- **Synthetic**: controlled substitutions, invalid restoration assumptions,
  missing phase feedback and incorrect classical measurement records.
- **Existing QCEC source + synthetic rewrite**: pinned QASM files are a
  common unchanged prefix; the local inserted gates are authored here. These
  are NOT independently optimized compiler source/destination pairs.
- **Existing public Qualtran decompositions**: source-pinned Apache-2.0
  GF2MulMBUC m=1/m=2 fixtures. Both their source and their prior
  qualification were already published in the repository. They are NOT fresh
  or previously untouched holdout data.
- **Different GF(2ⁿ) arithmetic decompositions**: schoolbook, Karatsuba and
  coordinate-rank synthesis from the same SymQ generator. Their full reversible
  behavior is independently evaluated against a separate integer convolution
  and polynomial reduction oracle, for all inputs at n=2,3,4 (including mutants).
  This is not independently authored external compiler output or a holdout.
- **QCEC admissibility control**: a QASM file with unsupported gates is a
  strict importer test, and is not counted as a substitution verdict.

The [manifest](substitution_manifest.json) declares each case's theorem,
provenance, and expected result, including negative decisions. The existing
QCEC and Qualtran manifests contain upstream commit, file SHA-256 and
license information. The runner rechecks the QCEC bytes and delegates
Qualtran validation to the pinned fixture loader.

## Run

From a clean checkout with the package installed and SAT available:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q tests/test_substitution_qualification.py
python -m benchmarks.substitution_qualification \
  --output /tmp/symq-substitution-qualification.json --repetitions 3
```

CI also runs the one-repetition matrix in a dedicated blocking job and uploads
its complete JSON and SHA-256 checksum as a GitHub Actions artifact. The
one-repetition CI campaign is a **correctness/coverage smoke test**, not a
performance significance study. For the full comparative protocol, select
15 or more repetitions. Each
observation gets a fresh spawned worker with hard CPU/wall/address-space
limits. The output includes actual and expected result, errors, unsupported
counts, whole-worker CPU/RSS, wall, source fingerprints, git identity if
available, environment, raw rows and a JSON checksum sidecar. The
qualification table reports **matched semantics and coverage**, not pooled
speed ratios between unrelated theorem classes.

Neither a JSON hash nor a shared hybrid-oracle rerun independently certifies
the underlying theorem. Small classical cases have a separate concrete
global-state oracle; all hybrid/coherence cases use the repository's already
qualified but still experimental exact hybrid semantics. The public
Qualtran channel equations are on the prepared coherent input frame.
A failed local lemma might be a cut state unreachable globally; it is
recorded as not_proved rather than inventing a global counterexample.

## Matched full-function QCEC and SAT checks

The separate [QCEC/SAT baseline runner](substitution_crosscheck.py) is executed
by the external CI job. It checks the **same six GF(2ⁿ) whole-circuit pairs**
through two genuinely comparable proof questions: all-input reversible-Boolean
SAT equivalence and full-unitary MQT QCEC alternating checking. It records
exact program SHA-256 on each engine; a mismatch in circuit input hashes
invalidates the campaign. The QCEC call includes conversion overhead and its
strict alternating proof-only configuration, not probabilistic simulation.
Engine import and circuit synthesis are now timed separately from the public
verification calls. The initial 12-cell pilot on HEAD `0837ff69` incorrectly
included the heavy optional MQT import inside its timed QCEC cell. Its verdicts
were valid but its QCEC wall times must **not** be used for performance ratios.

This is **not** a contextual-cut or HMR-instrument baseline, nor two unrelated
compiler implementations. Any inconclusive result is counted explicitly.
One CI repetition is only a coverage crosscheck, not a performance ranking.

## Adoption gate

After review and merge of the separate research API candidates, add an
adapter comparison against those user-facing entry points on matching
frozen cases. Then develop a fresh independently synthesized source/destination
corpus with cleared licenses and fair Boolean SAT/AIG, MQT QCEC and PyZX
baseline comparisons **only where the requested theorem matches**.
Do not call these previously explored cases an untouched holdout.

## Separate bilinear GF(64) evidence

The new [rank-15 GF(64) reconstruction and borrowed-scratch proof](bilinear_rank15_gf64.md)
provides a separately labeled external-method mathematical witness, exhaustive
integer oracles, negative mutants and exact CCX/CX counts. It does **not**
expand the 28-case manifest or claim any downloaded Kaggle evaluation fixture.


## Additional independent public starts (different protocol)

The [James Barlow / Kaggle bilinear KMB agent-evaluation corpus](corpus/kaggle_bilinear/SOURCE.md)
is imported separately with original byte SHA-256 checks, Apache-2.0 attribution and
reconstructed GF(16)/GF(64) candidates reaching 9/15 CCX on all 14 original starts.
Those data **do not alter the 28-case count**, provide no sealed independent
holdout, and test a specialized full dirty-target bilinear multiplication
contract rather than contextual SAT or hybrid HMR obligations.
