"""Liveness of the native ZDD manager -- uses the correct definition.

**Superseded implementation, kept with its history.** The first version of this file claimed that
the diagram of the *union of the root families* is the set of nodes reachable from the roots, and
used its node count as the live population. That is false: with ``A = {x}`` and ``B = {x, y}`` the
union is ``B``, whose diagram has two nodes, while ``A``'s node is not among them and the reachable
union has three. The audit found it, and the direction of the bound was wrong as well: summing
``size(root)`` counts a shared node once per root, so it is an **upper** bound, not a lower one.

This module now delegates to ``NativeZDDManager.reachable_union``, which marks identifiers while
walking and is exact. The old function is gone rather than left as a trap: a script that imports
this module gets the correct count.

Provenance of the figures produced by the old version: any number computed before 28 October 2026
that came from ``union_node_count`` must be recomputed. The pilots that matter were re-run; see
``RESULTS_C6.json`` (sealed with a truth-table oracle) and ``PILOT_C_CORRECTED.md``.
"""
from __future__ import annotations

from symq.backends.zdd_native import NativeZDDAlgebra


def live_nodes(algebra: NativeZDDAlgebra, roots) -> dict[str, int]:
    """The exact live-node count: distinct internal nodes reachable from ``roots``.

    ``live`` is the size of the union of the DAGs; ``created`` is the whole unique table;
    ``garbage`` is the difference, i.e. the nodes a collector could reclaim.
    """
    payload = algebra.manager.reachable_union(list(roots))
    return {"live": payload["live"], "created": payload["created"],
            "garbage": payload["created"] - payload["live"],
            "edges": payload["edges"], "roots": payload["roots"]}


def memory_report(algebra: NativeZDDAlgebra, roots) -> dict:
    """Node counts with their bounds and the cache state, for the pilots."""
    payload = live_nodes(algebra, roots)
    summed = sum(algebra.manager.size(root) for root in roots)
    payload["summed_size_upper_bound"] = summed
    payload["cache"] = algebra.cache_info()
    payload["dead_fraction"] = (payload["garbage"] / payload["created"]
                                if payload["created"] else 0.0)
    return payload
