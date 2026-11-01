"""Importable spawn target for the substitution qualification CLI.

Never pickle a function defined in __main__ when the runner is launched via
python -m: the child import identity must be the installed benchmarks package.
"""


def substitution_trial(case: dict) -> dict:
    from .substitution_qualification import _trial

    return _trial(case)
