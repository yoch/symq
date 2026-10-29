"""Native rename must propagate resource-budget failures, not swallow C error flags."""
from __future__ import annotations

import pytest

from symq.backends import make_algebra
from symq.resources import Budget, ResourceLimitExceeded


@pytest.mark.xfail(strict=True, reason="rename_rec error path returns NULL without calling handle_manager_error")
def test_native_rename_node_budget_raises_explicit_resource_limit():
    algebra = make_algebra("zdd-native", 4, Budget(max_nodes=1))
    x0 = algebra.variable(0)
    with pytest.raises(ResourceLimitExceeded):
        algebra.manager.rename(x0, [2, 1, 0, 3])


def test_native_manager_refuses_a_node_budget_when_building_algebra():
    algebra = make_algebra("zdd-native", 4, Budget(max_nodes=1))
    algebra.variable(0)
    with pytest.raises(ResourceLimitExceeded):
        algebra.variable(1)
