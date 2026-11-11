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
   `src/symq/labs/` (nothing outside it may import it); new benchmark results
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
Independent oracles and test-only helpers live in `tests/testkit/`.

Every test also gets one tier marker automatically, from what its module
imports: `core`, `experimental` or `labs`. `python -m pytest -m core` runs the
tests of the maintained package only, and
`python -m pytest -m core --cov` reports its branch coverage (the opt-in
experimental layer, the research modules and the external adapters are left out
of that report).

Run `python examples/public_demo.py` if a user-facing example or entry point
changes, and record notable changes in `CHANGELOG.md`. The GitHub CI covers
Python 3.10–3.14, pure-Python operation, native and pure wheels and C
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
