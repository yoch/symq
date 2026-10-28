"""Variable-order heuristics derived from the circuit, not from trials.

The previous variable-order experiments established the problem: on the blind adders the identity
order fails while a *random* order succeeds, and choosing the best of seven trials is not an
algorithm. This module proposes orders that are computed from the circuit alone, so they can be
used before any simulation and their cost can be charged to the run.

Three heuristics, each cheap and deterministic:

``reverse``
    the identity reversed (the baseline the archive used).
``degree``
    most interactive wire first: sort by the number of gates touching the wire, descending.
    Rationale: a wire that appears in many gates is the one whose elimination splits the diagram
    soonest, so it belongs near the root.
``dfs_cone``
    a depth-first order over the interaction graph, starting from the most-connected wire and
    following the most-connected unvisited neighbour. Rationale: adjacent wires in the graph
    become adjacent levels in the diagram, which keeps the support of each intermediate
    polynomial contiguous.
``bfs``
    breadth-first over the same graph from the most-connected wire.
``level``
    sort by the *last* gate that touches the wire, descending: a wire whose final use is early is
    forgotten early, so it belongs near the leaf.

Every heuristic is O(gates + wires log wires) or O(gates + wires^2) for BFS/DFS over a dense
graph, i.e. negligible next to the simulation on every circuit measured.
"""
from __future__ import annotations

from collections import deque

from symq.circuit import Circuit


def interaction_graph(circuit: Circuit) -> list[set[int]]:
    """Wires adjacent when one is a control of a gate targeting the other."""
    graph: list[set[int]] = [set() for _ in range(circuit.width)]
    for gate in circuit.gates:
        *controls, target = gate.qubits
        for control in controls:
            graph[control].add(target)
            graph[target].add(control)
    return graph


def identity(circuit: Circuit) -> tuple[int, ...]:
    return tuple(range(circuit.width))


def reverse(circuit: Circuit) -> tuple[int, ...]:
    return tuple(reversed(range(circuit.width)))


def by_degree(circuit: Circuit) -> tuple[int, ...]:
    """Most interactive wire first; ties broken by index so the order is deterministic."""
    graph = interaction_graph(circuit)
    order = sorted(range(circuit.width), key=lambda wire: (-len(graph[wire]), wire))
    return tuple(order)


def by_last_use(circuit: Circuit) -> tuple[int, ...]:
    """Wires whose final use comes last, first: they stay live longest."""
    last = [0] * circuit.width
    for position, gate in enumerate(circuit.gates):
        for qubit in gate.qubits:
            last[qubit] = position
    return tuple(sorted(range(circuit.width), key=lambda wire: (-last[wire], wire)))


def dfs_cone(circuit: Circuit) -> tuple[int, ...]:
    """Depth-first walk of the interaction graph from the most connected wire."""
    graph = interaction_graph(circuit)
    start = max(range(circuit.width), key=lambda wire: (len(graph[wire]), -wire))
    seen = [False] * circuit.width
    order: list[int] = []
    stack = [start]
    while stack:
        wire = stack.pop()
        if seen[wire]:
            continue
        seen[wire] = True
        order.append(wire)
        neighbours = sorted(graph[wire], key=lambda w: (-len(graph[w]), w))
        for neighbour in reversed(neighbours):
            if not seen[neighbour]:
                stack.append(neighbour)
    # Wires with no interaction at all keep their natural relative order.
    order.extend(wire for wire in range(circuit.width) if not seen[wire])
    return tuple(order)


def bfs(circuit: Circuit) -> tuple[int, ...]:
    graph = interaction_graph(circuit)
    start = max(range(circuit.width), key=lambda wire: (len(graph[wire]), -wire))
    seen = [False] * circuit.width
    order: list[int] = []
    queue = deque([start])
    while queue:
        wire = queue.popleft()
        if seen[wire]:
            continue
        seen[wire] = True
        order.append(wire)
        for neighbour in sorted(graph[wire], key=lambda w: (-len(graph[w]), w)):
            if not seen[neighbour]:
                queue.append(neighbour)
    order.extend(wire for wire in range(circuit.width) if not seen[wire])
    return tuple(order)


def greedy_min_frontier(circuit: Circuit) -> tuple[int, ...]:
    """Greedy elimination by smallest frontier growth, the classic min-fill idea.

    Builds the order level by level: at each step, take the unplaced wire whose removal leaves
    the smallest number of *new* adjacencies among the remaining wires. This is the textbook
    min-fill heuristic, included because it is the natural baseline a reviewer would ask for.
    """
    graph = [set(neighbours) for neighbours in interaction_graph(circuit)]
    remaining = set(range(circuit.width))
    order: list[int] = []
    while remaining:
        best = None
        best_cost = None
        for wire in sorted(remaining):
            neighbours = graph[wire] & remaining
            missing = 0
            listed = sorted(neighbours)
            for index, first in enumerate(listed):
                for second in listed[index + 1:]:
                    if second not in graph[first]:
                        missing += 1
            cost = (missing, len(neighbours), wire)
            if best_cost is None or cost < best_cost:
                best_cost, best = cost, wire
        order.append(best)
        remaining.discard(best)
        neighbours = sorted(graph[best] & remaining)
        for index, first in enumerate(neighbours):
            for second in neighbours[index + 1:]:
                graph[first].add(second)
                graph[second].add(first)
    return tuple(reversed(order))


HEURISTICS = {
    "identity": identity,
    "reverse": reverse,
    "degree": by_degree,
    "last_use": by_last_use,
    "dfs": dfs_cone,
    "bfs": bfs,
    "min_fill": greedy_min_frontier,
}


def order_of(circuit: Circuit, name: str) -> tuple[int, ...]:
    try:
        heuristic = HEURISTICS[name]
    except KeyError:
        raise ValueError(f"unknown order heuristic {name!r}") from None
    order = heuristic(circuit)
    if sorted(order) != list(range(circuit.width)):
        raise AssertionError(f"{name} did not produce a permutation")
    return order
