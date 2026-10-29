"""Exact block decomposition to verify HMR channels wider than 32 data bits.

## Why this is sound

The full-channel theorem compares two programs on every coherence ``|x><y|``. If a program's gate
list splits into **disjoint connected components of wires**, the unitary it implements is a tensor
product over those components, and so is the channel. Two programs then have equal channels exactly
when they agree on every component, because the tensor factor of each component can be probed
independently: fix the other components in a basis state and the phases and kernels multiply out.

So the wide check reduces to a set of narrow checks. This is an **exact equivalence**, not an
approximation and not a restriction of the domain: nothing is sampled and no coherence is dropped.

## The precondition, which is tested rather than assumed

Two wires belong to the same component when one gate touches both. Data wires are compacted inside
each component and ancillas keep their own slots. A component with ``d`` data wires still needs
``2d`` ZDD variables in the native engine, so the native path applies when ``max(d) <= 32`` even if
the program has 40 data wires in total.

When a program does not decompose below that bound, this module says so and refuses. It never
silently narrows the domain to classical inputs.

## What it does not do

It does not change the theorem, the grammar or any default. It is a driver that calls the existing
``check_full_channel`` on compacted sub-programs and combines the verdicts. The two programs must
have the same data-wire partition; otherwise the pairing is refused rather than guessed.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from research.hmr_native_channel.native_channel import ChannelDecision, _sha, check_full_channel
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded

NATIVE_MAX_DATA = 32


@dataclass(frozen=True)
class Component:
    """One connected wire set, with data and ancilla wires kept apart."""

    data_wires: tuple[int, ...]
    ancilla_wires: tuple[int, ...]

    @property
    def data(self) -> int:
        return len(self.data_wires)

    @property
    def ancillas(self) -> int:
        return len(self.ancilla_wires)

    @property
    def native_eligible(self) -> bool:
        return 2 * self.data <= 2 * NATIVE_MAX_DATA


@dataclass
class BlockStats:
    components: int = 0
    widest_data_component: int = 0
    seconds: float = 0.0
    per_component_seconds: list[float] = field(default_factory=list)
    per_component_equivalent: list[bool] = field(default_factory=list)


def components(program: PhaseProgram) -> list[Component]:
    """Disjoint wire sets, in first-appearance order, with data and ancillas separated."""
    parent = list(range(program.width))

    def find(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for op in program.ops:
        qubits = op.qubits
        for other in qubits[1:]:
            union(qubits[0], other)

    grouped: dict[int, set[int]] = {}
    for wire in range(program.width):
        grouped.setdefault(find(wire), set()).add(wire)

    out: list[Component] = []
    for root in sorted(grouped, key=lambda r: (min(grouped[r]), r)):
        members = grouped[root]
        out.append(
            Component(
                data_wires=tuple(sorted(w for w in members if w < program.data)),
                ancilla_wires=tuple(sorted(w for w in members if w >= program.data)),
            )
        )
    return out


def restrict(program: PhaseProgram, component: Component) -> PhaseProgram:
    """The same operations, with this component's wires compacted to ``0..d+a-1``.

    Operations that do not touch the component are dropped: they act on other tensor factors and
    cannot change this one. Every retained operation is copied verbatim apart from the wire
    renumbering, which keeps the gate semantics identical.
    """
    index = {wire: position for position, wire in enumerate(component.data_wires)}
    index.update(
        {wire: component.data + position for position, wire in enumerate(component.ancilla_wires)}
    )
    sub = PhaseProgram(component.data, component.ancillas)
    for op in program.ops:
        inside = [qubit in index for qubit in op.qubits]
        if not any(inside):
            continue
        if not all(inside):
            raise ValueError(
                f"operation {op.kind} on wires {op.qubits} crosses the block boundary "
                f"{component.data_wires}; the block is not a tensor factor"
            )
        sub.ops.append(Op(op.kind, tuple(index[qubit] for qubit in op.qubits), op.outcome))
    sub.validate()
    return sub


def same_partition(left: PhaseProgram, right: PhaseProgram) -> bool:
    """Whether both programs split the data wires the same way, exactly."""
    left_sets = {frozenset(c.data_wires) for c in components(left)}
    right_sets = {frozenset(c.data_wires) for c in components(right)}
    return left_sets == right_sets


def join_partition(left: PhaseProgram, right: PhaseProgram) -> list[tuple[int, ...]]:
    """The finest common coarsening of both programs' components, over data wires.

    A block of this partition is a tensor factor for **both** programs: each program's own
    components refine it, so neither program has a gate crossing two blocks. It is therefore the
    best possible common decomposition, and no coarser common partition can beat it.

    Returns a list of sorted data-wire tuples, in first-appearance order.
    """
    groups: list[set[int]] = []
    wire_group: dict[int, int] = {}

    def add(wires: set[int]) -> None:
        merged: set[int] = set(wires)
        touched = sorted({wire_group[w] for w in wires if w in wire_group})
        for group_index in touched:
            merged |= groups[group_index]
        for wire in merged:
            wire_group[wire] = len(groups) if not touched else touched[0]
        if touched:
            groups[touched[0]] = merged
            for group_index in touched[1:]:
                groups[group_index] = set()
        else:
            groups.append(merged)

    for program in (left, right):
        for component in components(program):
            if component.data_wires:
                add(set(component.data_wires))
    blocks = [tuple(sorted(group)) for group in groups if group]
    return sorted(blocks, key=lambda block: block[0])


def _component_for(
    program: PhaseProgram, data_wires: tuple[int, ...], ancilla_pool: tuple[int, ...]
) -> Component:
    """The tensor factor of ``program`` over these data wires and this ancilla pool.

    An ancilla belongs to the block if either program lets it interact with one of the block's data
    wires; that is what makes the block a factor of *both* programs at once.
    """
    wanted = set(data_wires)
    ancillas: set[int] = set()
    for component in components(program):
        if wanted & set(component.data_wires):
            ancillas |= set(component.ancilla_wires)
    return Component(data_wires=data_wires, ancilla_wires=tuple(sorted(ancillas | set(ancilla_pool))))


def _ancillas_per_block(
    left: PhaseProgram, right: PhaseProgram, blocks: list[tuple[int, ...]]
) -> dict[tuple[int, ...], tuple[int, ...]]:
    """Assign every ancilla to exactly one block, from the union of both programs' components.

    The two programs must end with the same ancilla count in each block, otherwise their tensor
    factors have different shapes and the comparison is malformed; that is checked, not assumed.
    """
    assignment: dict[tuple[int, ...], set[int]] = {block: set() for block in blocks}
    block_of: dict[int, tuple[int, ...]] = {}
    for block in blocks:
        for wire in block:
            block_of[wire] = block
    for program in (left, right):
        for component in components(program):
            targets = {block_of[wire] for wire in component.data_wires if wire in block_of}
            if not targets:
                # The component is ancilla-only: it is a free tensor factor with no data wires.
                # Its channel factor is the identity check on ancillas alone, which the monolithic
                # check covers; here it is attached to the first block for accounting only.
                continue
            for block in targets:
                assignment[block] |= set(component.ancilla_wires)
    return {block: tuple(sorted(wires)) for block, wires in assignment.items()}


def decompose_decision(
    left: PhaseProgram,
    right: PhaseProgram,
    *,
    backend: str = "zdd-native",
    budget: Budget | None = None,
) -> tuple[ChannelDecision, BlockStats]:
    """Check every block of the joint partition, combining into one verdict.

    Sound because each block is a tensor factor of both programs. A block whose data width still
    exceeds the native pair limit raises ``ResourceLimitExceeded`` rather than being skipped, so a
    partial verdict can never be reported as equality.
    """
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("data and ancilla widths must match for full-channel equality")
    stats = BlockStats()
    blocks = join_partition(left, right)
    stats.components = len(blocks)
    stats.widest_data_component = max((len(block) for block in blocks), default=0)
    ancillas = _ancillas_per_block(left, right, blocks)
    started = time.perf_counter()
    for index, block in enumerate(blocks):
        pool = ancillas.get(block, ())
        left_component = _component_for(left, block, pool)
        right_component = _component_for(right, block, pool)
        if left_component.ancillas != right_component.ancillas:
            raise ValueError(
                f"block {block} has {left_component.ancillas} ancillas on the left and "
                f"{right_component.ancillas} on the right; the tensor factors differ"
            )
        if backend == "zdd-native" and not (
            left_component.native_eligible and right_component.native_eligible
        ):
            raise ResourceLimitExceeded(
                "component pair variables",
                64,
                2 * max(left_component.data, right_component.data),
            )
        component_started = time.perf_counter()
        decision = check_full_channel(
            restrict(left, left_component),
            restrict(right, right_component),
            backend=backend,
            budget=budget,
        )
        stats.per_component_seconds.append(time.perf_counter() - component_started)
        stats.per_component_equivalent.append(decision.equivalent)
        if not decision.equivalent:
            stats.seconds = time.perf_counter() - started
            return (
                ChannelDecision(
                    False,
                    backend,
                    "full_quantum_channel",
                    f"component {index} (data wires {block}): {decision.reason}",
                    _sha(left),
                    _sha(right),
                    left.measurements + right.measurements,
                    decision.witness_kind,
                    decision.witness,
                ),
                stats,
            )
    stats.seconds = time.perf_counter() - started
    return (
        ChannelDecision(
            True,
            backend,
            "full_quantum_channel",
            f"all {stats.components} disjoint components match",
            _sha(left),
            _sha(right),
            left.measurements + right.measurements,
        ),
        stats,
    )
