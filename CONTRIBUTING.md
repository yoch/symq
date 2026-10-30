# Contributing to SymQ

SymQ is an experimental scientific codebase. Contributions are welcome through
reviewable pull requests; no frozen API, automatic merge or publication claim
is promised.

For orientation, read the [architecture map](docs/ARCHITECTURE.md),
[public demo](docs/PUBLIC_DEMO.md), [theorem/API boundaries](docs/experimental.md)
and [repository agent rules](AGENTS.md).

## Before opening a PR

1. **State the exact theorem and input contract.** Is this a Boolean
   permutation, selected-output SAT relation, strict HMR branch proof, full
   channel, reduced channel or observed instrument? Define preparation,
   outputs, supported operations, budgets and failure statuses.
2. **Keep implementation and experiments separate.** Maintained package code
   belongs in `src/symq/`; exploratory prototypes and old measurements in
   `research/` and `benchmarks/`. Do not silently add runtime imports of
   research modules or external private repositories.
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
python -m pytest -q
```

Native C is optional. `python tools/build_native.py --diagnose` explains the
toolchain; `python tools/build_native.py --require` fails rather than silently
skipping. Optional external comparisons require `.[dev,external]`.

Run `python examples/public_demo.py` if a user-facing example or entry point
changes. The standard GitHub CI covers three Python versions, both native/pure
wheels, optional external engines and C sanitizers; additional targeted
research workflows may be conditional on changed paths.

For a reported vulnerability, follow [SECURITY.md](SECURITY.md) rather than
posting a sensitive exploit publicly.

## Review expectations

A PR description should include: scope, expected SHA, file list, tests/CI
actually executed, data source and license, known limitations, and an explicit
merge/release recommendation. A green CI job is neither a mathematical proof
nor permission to publish a paper. Do not change stable or experimental
theorem claims, merge or announce external publication without the respective
review/approval.
