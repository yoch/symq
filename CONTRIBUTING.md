# Contributing to SymQ

SymQ is an experimental scientific codebase. Contributions are welcome through
reviewable pull requests; no frozen API, automatic merge or publication claim
is promised.

For orientation, read the [architecture map](docs/architecture.md),
[public demo](docs/demo.md), [theorem/API boundaries](docs/guide/experimental.md)
and [repository agent rules](AGENTS.md).

## Before opening a PR

1. **State the exact theorem and input contract.** Is this a Boolean
   permutation, selected-output SAT relation, strict HMR branch proof, full
   channel, reduced channel or observed instrument? Define preparation,
   outputs, supported operations, budgets and failure statuses.
2. **Keep implementation and experiments separate.** Maintained package code
   belongs in `src/symq/`; research code without an API promise in
   `src/symq/labs/` (nothing outside it may import it, except the labs commands
   of the CLI); new benchmark results
   are published as CI artifacts, not committed. Never depend on external
   private repositories.
3. **Add independent tests.** Include positive and adversarial cases, a
   simple scalar or Kraus oracle when feasible, and replayed counterexamples.
   For native C changes include ownership, abort paths and sanitizer checks.
4. **Pin provenance before benchmarking.** Record commit SHA, source/binary
   hashes, compiler, dependency versions, machine, resource ceilings, failed
   and unsupported trials. Preserve explored/holdout distinctions and
   negative results; no inferred performance advantage from toy cases.
5. **Check third-party rights.** Preserve source commit and license for
   imported circuits, datasets and derivative fixtures. Do not upload
   credentials, private programs or personally identifying paths.

## Local checks

```bash
python -m pip install -e ".[dev]"
ruff check .
mypy
python -m pytest -q
```

`ruff` and `mypy` are held to one minor series in the `dev` extra, so the rules
that CI enforces are the ones you run locally. Native C is optional. `python tools/build_native.py --diagnose` explains the
toolchain; `python tools/build_native.py --require` fails rather than silently
skipping. Optional external comparisons require `.[dev,external]`.

Tests that need the native core or the SAT solver carry the `native` or `sat`
marker (see `tests/conftest.py`); use the marker for new tests instead of an
ad-hoc `skipif`. `SYMQ_TEST_REQUIRE=native,sat` turns their skips into errors.
A test that reads `benchmarks/corpus/bilinear_kmb` needs the `corpus_bilinear`
marker: that corpus is not in the source distribution, and CI runs the suite
inside one.
Independent oracles and test-only helpers live in `tests/testkit/`.

Every test also gets one tier marker automatically, from what its module
imports: `core`, `experimental` or `labs`. `python -m pytest -m core` runs the
tests of the maintained package only, and
`python -m pytest -m core --cov` reports its branch coverage (the opt-in
experimental layer, the research modules and the external adapters are left out
of that report). CI fails when that figure drops under its floor.

The public surface of the core is recorded in `tests/data/api_snapshot.json`
and governed by the [stability policy](docs/stability.md). A change to an
exported name, a signature, a stable command or a JSON output fails
`tests/test_api_snapshot.py`; if it is intended and allowed by the policy, run
`python tools/api_snapshot.py --write` and add a `CHANGELOG.md` line.

A test that asserts a ceiling on real elapsed time (a hard wall-clock limit, an
interrupt that must stop a solver) carries `@pytest.mark.timing`; CI runs these
in a serial step, because under `pytest -n auto` the other workers decide
whether the ceiling holds. Prefer an injected clock when the property is not
about real time; `tests/test_timing_marker.py` fails for an unmarked ceiling.

Run `python examples/public_demo.py` if a user-facing example or entry point
changes, and record notable changes in `CHANGELOG.md`. The GitHub CI covers
Python 3.11–3.14, pure-Python operation, native and pure wheels and C
sanitizers (`ci.yml`, whose `ci-ok` job is the required check), plus optional
external engines and regenerated research evidence (`research.yml`).

For a reported vulnerability, follow [SECURITY.md](SECURITY.md) rather than
posting a sensitive exploit publicly.

## Review expectations

A PR description should include: scope, expected SHA, file list, tests/CI
actually executed, data source and license, known limitations, and an explicit
merge/release recommendation. A green CI job is neither a mathematical proof
nor permission to publish a paper. Do not change stable or experimental
theorem claims, merge or announce external publication without the respective
review/approval.
