# Contributing

symq is an experimental scientific codebase. Contributions are welcome through pull requests.

1. State the contract and supported semantics of a change.
2. Include deterministic unit tests and, for algebraic transformations, property/differential tests.
3. Report the exact environment and commit used for performance results. Record slowdowns and failures.
4. Avoid adding external corpus copies without checking licensing and provenance.
5. Run `python -m pip install -e ".[dev]"`, `ruff check .`, and `pytest -q`.

No stable API is promised yet. Research datasets and optional backends belong in isolated, documented modules.
