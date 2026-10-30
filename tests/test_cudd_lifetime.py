"""Adapter-owned memoized nodes must be released before CUDD manager disposal."""
from __future__ import annotations

import gc
import sys

import pytest

from symq import ANF, Budget, ResourceLimitExceeded, external


@pytest.mark.parametrize("backend", ("cudd-bdd", "cudd-zdd"))
@pytest.mark.parametrize("reordering", (False, True))
@pytest.mark.parametrize("limited", (False, True))
def test_repeated_transform_and_disposal_releases_manager_nodes(
        monkeypatch, backend, reordering, limited):
    if backend not in external.EXTERNAL_BACKENDS:
        pytest.skip(f"optional {backend} unavailable: {external.UNAVAILABLE.get(backend)}")
    failures = []
    # Do not let a finalizer's unraisable error be mistaken for a passing
    # transform. Save only text, which cannot retain the failed manager itself.
    monkeypatch.setattr(sys, "unraisablehook", lambda error: failures.append(str(error.exc_value)))

    def exercise():
        algebra = external.EXTERNAL_BACKENDS[backend](5, reordering=reordering)
        expected = ANF(frozenset((0, 1, 2, 3, 9, 17, 31)))
        value = algebra.from_anf(expected)
        assert algebra.to_anf(value) == expected
        assert algebra.manager.configure()["reordering"] is reordering
        if limited:
            algebra.guard = Budget(max_terms=1).start()
            with pytest.raises(ResourceLimitExceeded, match="terms"):
                algebra.to_anf(value)
            assert algebra.manager.configure()["reordering"] is reordering
        else:
            # A second call must not use memoized handles from the first call.
            assert algebra.to_anf(value) == expected

    for _ in range(20):
        exercise()
        gc.collect()
    assert not failures, failures
