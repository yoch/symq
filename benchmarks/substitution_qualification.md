# Substitution qualification matrix (existing public + synthetic)

The standalone [runner](substitution_qualification.py) evaluates the existing
classical transcript, relational SAT and restricted coherent-channel
composition theorems on **22 explicitly labeled tasks**. It is not yet a
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

For the full comparative protocol, select 15 or more repetitions. Each
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

## Adoption gate

After review and merge of the separate research API candidates, add an
adapter comparison against those user-facing entry points on matching
frozen cases. Then develop a fresh independently synthesized source/destination
corpus with cleared licenses and fair Boolean SAT/AIG, MQT QCEC and PyZX
baseline comparisons **only where the requested theorem matches**.
Do not call these previously explored cases an untouched holdout.
