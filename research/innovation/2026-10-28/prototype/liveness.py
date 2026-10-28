"""Exact liveness measurement for the native ZDD manager.

``manager.size(root)`` walks one DAG, so summing it over the wires counts every shared node once
per root: it is a *lower* bound on the live population, and the previous pilot's dead-node figure
was computed from it and is therefore an over-estimate of the garbage.

The exact union is obtained without any new C accessor. ZDDs are canonical, so for a family ``U``
every node of ``ZDD(F)`` with ``F ⊆ U`` is a node of ``ZDD(U)`` and conversely; hence building
``U = union of the root families`` in a scratch manager yields a DAG whose node count is exactly
the number of nodes reachable from the roots. The cost is one explicit expansion per root, which
is why this is a measurement tool and never a production path.

Both numbers are reported with their bound direction so no reader can mistake one for the other.
"""
from __future__ import annotations

from symq.backends.zdd_native import NativeZDDAlgebra


def sum_of_sizes(algebra: NativeZDDAlgebra, roots) -> int:
    """Sum of the per-root DAG sizes: a **lower** bound on the live population."""
    return sum(algebra.manager.size(root) for root in roots)


def union_node_count(algebra: NativeZDDAlgebra, roots) -> tuple[int, int]:
    """``(exact live nodes, monomials in the union)``, via the canonical ZDD of the union.

    A scratch manager of the same width and order is used, so the node count is directly
    comparable with ``algebra.node_count`` on the original manager.
    """
    families = [frozenset(algebra.manager.anf(root)) for root in roots]
    union: set[int] = set()
    for family in families:
        union |= family
    scratch = NativeZDDAlgebra(algebra.width)
    if union:
        scratch.manager.from_terms(sorted(union))
    return scratch.node_count, len(union)


def memory_report(algebra: NativeZDDAlgebra, roots) -> dict:
    """Node counts with their bounds, the root volume, and the cache state."""
    created = algebra.node_count
    lower = sum_of_sizes(algebra, roots)
    exact, union_terms = union_node_count(algebra, roots)
    return {
        "nodes_created": created,
        "reachable_lower_bound": lower,
        "reachable_exact": exact,
        "union_monomials": union_terms,
        "dead_exact": created - exact,
        "dead_fraction": (created - exact) / created if created else 0.0,
        "dead_upper_bound": created - lower,
        "cache": algebra.cache_info(),
    }
