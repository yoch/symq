"""Exact block decomposition of the HMR full-channel check.

## The theorem this driver uses

If a program's gate list splits into **disjoint sets of quantum wires** such that no gate and no
measurement-feedback edge crosses between them, then the unitary (and, for measured wires, the whole
Kraus family) is a tensor product over those sets. Writing the outcome tuple as one outcome per
block, the channel factorizes exactly:

    E = sum_m (K^(1)_{m_1} ⊗ ... ⊗ K^(k)_{m_k}) rho (K^(1)dagger_{m_1} ⊗ ...)
      = (sum_{m_1} K^(1) rho_1 K^(1)dagger) ⊗ ... ⊗ (sum_{m_k} K^(k) rho_k K^(k)dagger)
      = E_1 ⊗ ... ⊗ E_k

The sum over the tuple splits into a product of sums, so **forgetting outcomes block by block is the
same as forgetting them globally**. Two programs therefore have equal full channels exactly when every
block pair does.

## Three corrections that a first version of this module got wrong

**Ancilla-only blocks are factors too.** A block with no data wire still carries a CP map applied to
the prepared ``|0...0>`` ancillas, and the full channel retains those ancillas. Dropping such a block
made ``identity`` and ``X`` on a clean ancilla compare equal -- a false EQUIVALENT. They are now
merged into a data-bearing block, which is free in the native variable count (``2 * n_data``) and is
proved exact by :func:`restrict`: the merged set is a union of components, so it is still a tensor
factor, and the data inputs of the host block range over every basis value, so the ancilla factor is
compared exhaustively.

**Measurement feedback couples blocks.** ``mcz_if(e)`` applies a diagonal phase conditioned on the
outcome of event ``e``. If ``e`` was measured on a wire in another block, the Kraus operator is no
longer a product and the factorization fails. The conditioning wire of ``e`` is unioned with every
qubit of the conditional gate, so a cross-block dependency becomes one block instead of a wrong
verdict. If it somehow survives to :func:`restrict`, that function raises.

**HMR events must be renumbered locally.** ``PhaseProgram`` requires event indices to be ``0, 1, 2,
...`` in order of appearance, while the global program may have interleaved events across blocks.
:func:`restrict` builds a bijection from global event ids to local ones and remaps every ``mcz_if``
through it; an outcome with no local producer is refused rather than silently dropped.

## Witnesses are global

A local witness lives in compacted coordinates. :func:`decompose_decision` lifts it to the original
data-bit indices (non-block data wires are set to 0, which leaves every other block's factor at its
``|0><0|`` input) and then **replays it against the two whole programs** with an exact scalar
comparison of the channel images. A witness that does not reproduce is a defect, not a verdict.

## Scope

Opt-in research driver. No default backend is touched, and the monolithic checker remains the
reference it is differentially tested against.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from research.hmr_native_channel.native_channel import (
    ChannelDecision,
    _scalar,
    _scalar_kernel,
    _sha,
    check_full_channel,
)
from symq.phase import Op, PhaseProgram
from symq.resources import Budget, ResourceLimitExceeded

NATIVE_MAX_DATA = 32
"""``2 * n_data <= 64`` native pair variables. Ancillas add no variables."""


@dataclass(frozen=True)
class Component:
    """One connected wire set of a program, data and ancilla wires kept apart."""

    data_wires: tuple[int, ...]
    ancilla_wires: tuple[int, ...]

    @property
    def data(self) -> int:
        return len(self.data_wires)

    @property
    def ancillas(self) -> int:
        return len(self.ancilla_wires)

    @property
    def wires(self) -> tuple[int, ...]:
        return tuple(sorted(self.data_wires + self.ancilla_wires))

    @property
    def native_eligible(self) -> bool:
        return 2 * self.data <= 2 * NATIVE_MAX_DATA


@dataclass
class BlockStats:
    components: int = 0
    widest_data_component: int = 0
    ancilla_only_merged: int = 0
    seconds: float = 0.0
    per_block_seconds: list[float] = field(default_factory=list)
    per_block_equivalent: list[bool] = field(default_factory=list)
    blocks: list[tuple[int, ...]] = field(default_factory=list)


class _Union:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, node: int) -> int:
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra

    def union_all(self, nodes: tuple[int, ...]) -> None:
        for other in nodes[1:]:
            self.union(nodes[0], other)


def _couple(union: _Union, program: PhaseProgram) -> None:
    """Add this program's edges: gate support, and measurement feedback.

    ``event_wire[e]`` is the wire measured by the ``e``-th HMR. A conditional gate on outcome ``e``
    is unioned with that wire, because its diagonal phase depends on the outcome recorded there.
    """
    event_wire: dict[int, int] = {}
    for op in program.ops:
        union.union_all(op.qubits)
        if op.kind == "hmr":
            if op.outcome is not None:
                event_wire[op.outcome] = op.qubits[0]
        elif op.kind == "mcz_if":
            if op.outcome is None or op.outcome not in event_wire:
                raise ValueError(
                    f"instruction on wires {op.qubits} references measurement outcome "
                    f"{op.outcome!r} with no producing event"
                )
            union.union_all(op.qubits + (event_wire[op.outcome],))


def components(program: PhaseProgram) -> list[Component]:
    """Connected wire sets of one program, over **all** quantum wires."""
    program.validate()
    union = _Union(program.width)
    _couple(union, program)
    grouped: dict[int, list[int]] = {}
    for wire in range(program.width):
        grouped.setdefault(union.find(wire), []).append(wire)
    out: list[Component] = []
    for root in sorted(grouped, key=lambda r: min(grouped[r])):
        members = sorted(grouped[root])
        out.append(
            Component(
                data_wires=tuple(w for w in members if w < program.data),
                ancilla_wires=tuple(w for w in members if w >= program.data),
            )
        )
    return out


def common_blocks(left: PhaseProgram, right: PhaseProgram) -> list[Component]:
    """The finest wire partition that is a tensor factor for **both** programs.

    Built as the connected components of the union of both programs' edges. Every such component is
    a union of each program's own components, hence a tensor factor of each -- which is exactly what
    allows one block pair to be compared on its own.
    """
    left.validate()
    right.validate()
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("data and ancilla widths must match for full-channel equality")
    union = _Union(left.width)
    _couple(union, left)
    _couple(union, right)
    grouped: dict[int, list[int]] = {}
    for wire in range(left.width):
        grouped.setdefault(union.find(wire), []).append(wire)
    out: list[Component] = []
    for root in sorted(grouped, key=lambda r: min(grouped[r])):
        members = sorted(grouped[root])
        out.append(
            Component(
                data_wires=tuple(w for w in members if w < left.data),
                ancilla_wires=tuple(w for w in members if w >= left.data),
            )
        )
    return out


def plan_blocks(left: PhaseProgram, right: PhaseProgram) -> tuple[list[Component], int]:
    """Common blocks with every ancilla-only block merged into one data-bearing block.

    Returns the blocks and how many ancilla-only blocks were merged. Merging is exact: a union of
    tensor factors is still a tensor factor, and the host block's data inputs range over every basis
    value, so the merged ancilla factor is compared on its prepared ``|0...0>`` input exhaustively.
    Merging costs no native variables, because the engine allocates ``2 * n_data`` only.
    """
    blocks = common_blocks(left, right)
    data_blocks = [block for block in blocks if block.data_wires]
    if not data_blocks:
        raise ValueError("no data-bearing block: a full-channel check needs one data wire")
    ancilla_only = [block for block in blocks if not block.data_wires]
    if not ancilla_only:
        return data_blocks, 0
    host = min(data_blocks, key=lambda block: block.data_wires[0])
    merged = Component(
        data_wires=host.data_wires,
        ancilla_wires=tuple(
            sorted(
                host.ancilla_wires
                + tuple(wire for block in ancilla_only for wire in block.ancilla_wires)
            )
        ),
    )
    ordered = [merged if block is host else block for block in data_blocks]
    ordered.sort(key=lambda block: block.data_wires[0])
    return ordered, len(ancilla_only)


def restrict(program: PhaseProgram, block: Component) -> PhaseProgram:
    """The block's own sub-program, with wires compacted and HMR events renumbered.

    Raises when an operation touches the block and the outside at once: that means the block is not a
    tensor factor and renumbering it would compare the wrong thing. A conditional gate whose event
    producer was dropped also raises, because a local program cannot express a cross-block outcome.
    """
    index = {wire: position for position, wire in enumerate(block.data_wires)}
    index.update(
        {wire: block.data + position for position, wire in enumerate(block.ancilla_wires)}
    )
    sub = PhaseProgram(block.data, block.ancillas)
    event_map: dict[int, int] = {}
    for op in program.ops:
        inside = [qubit in index for qubit in op.qubits]
        if not any(inside):
            continue
        if not all(inside):
            raise ValueError(
                f"operation {op.kind} on wires {op.qubits} crosses the block boundary "
                f"{block.wires}; the block is not a tensor factor"
            )
        wires = tuple(index[qubit] for qubit in op.qubits)
        if op.kind == "hmr":
            if op.outcome is None:
                raise ValueError("an HMR instruction must carry an event index")
            local = len(event_map)
            event_map[op.outcome] = local
            sub.ops.append(Op("hmr", wires, local))
        elif op.kind == "mcz_if":
            if op.outcome not in event_map:
                raise ValueError(
                    f"conditional gate on wires {op.qubits} depends on measurement outcome "
                    f"{op.outcome!r} produced outside this block"
                )
            sub.ops.append(Op("mcz_if", wires, event_map[op.outcome]))
        else:
            sub.ops.append(Op(op.kind, wires, op.outcome))
    sub.validate()
    return sub


def lift_witness(witness: tuple[int, int], block: Component) -> tuple[int, int]:
    """Compacted data-bit coordinates to the original data-bit indices.

    A data wire outside the block is fixed to 0. Every other block is then compared at its
    ``|0><0|`` input, where its kernel is 1 and its relative phase is 0, so a difference inside this
    block survives the embedding.
    """
    x_local, y_local = witness

    def embed(local: int) -> int:
        return sum(1 << wire for position, wire in enumerate(block.data_wires) if local >> position & 1)

    return embed(x_local), embed(y_local)


def channels_differ_at(
    left: PhaseProgram, right: PhaseProgram, x: int, y: int
) -> bool | None:
    """Exact comparison of the two full-channel images at one coherence ``|x><y|``.

    ``True`` means the images differ. ``False`` means they agree **and** both are nonzero. ``None``
    means at least one image is zero, so the pair cannot witness a difference.

    ## The order of the checks is the whole point

    For a coherence ``|x><y|`` the channel image is

        E(|x><y|) = (-1)^(phi0(x) + phi0(y)) * [g(x) = g(y)] * |F(x)><F(y)|

    so a kernel factor of zero annihilates the image **whatever** ``F`` is. Comparing ``F`` first and
    returning a difference is therefore wrong: two programs that both fully dephase this pair have
    two zero images, and ``identity`` versus ``X`` on the data is invisible. A first version of this
    function did exactly that and reported a witness the physical oracle contradicts.

    The checks are ordered accordingly:

    1. both kernels zero -> both images are the zero matrix, ``None``;
    2. exactly one kernel zero -> one image is zero and the other is not, a real difference;
    3. both kernels nonzero -> compare ``F``, then the relative phase.

    ``False`` is only returned when both images are demonstrably equal and nonzero, which is what
    makes the return value usable as a proof rather than as an absence of evidence.
    """
    kernel_left = _scalar_kernel(left, x, y)
    kernel_right = _scalar_kernel(right, x, y)
    if not kernel_left and not kernel_right:
        return None
    if kernel_left != kernel_right:
        return True
    # Both survive: the images are nonzero, so the output functions and phases decide.
    left_x, right_x = _scalar(left, x), _scalar(right, x)
    left_y, right_y = _scalar(left, y), _scalar(right, y)
    if left_x[0] != right_x[0] or left_y[0] != right_y[0]:
        return True
    return (left_x[1] ^ left_y[1]) != (right_x[1] ^ right_y[1])


def decompose_decision(
    left: PhaseProgram,
    right: PhaseProgram,
    *,
    backend: str = "zdd-native",
    budget: Budget | None = None,
) -> tuple[ChannelDecision, BlockStats]:
    """Check every block pair, then lift and replay the first witness globally."""
    left.validate()
    right.validate()
    if left.data != right.data or left.ancillas != right.ancillas:
        raise ValueError("data and ancilla widths must match for full-channel equality")
    blocks, merged = plan_blocks(left, right)
    stats = BlockStats(
        components=len(blocks),
        widest_data_component=max((block.data for block in blocks), default=0),
        ancilla_only_merged=merged,
        blocks=[block.wires for block in blocks],
    )
    started = time.perf_counter()
    for index, block in enumerate(blocks):
        if backend == "zdd-native" and not block.native_eligible:
            raise ResourceLimitExceeded(
                "component pair variables", 64, 2 * block.data
            )
        block_started = time.perf_counter()
        decision = check_full_channel(
            restrict(left, block), restrict(right, block), backend=backend, budget=budget
        )
        stats.per_block_seconds.append(time.perf_counter() - block_started)
        stats.per_block_equivalent.append(decision.equivalent)
        if decision.equivalent:
            continue
        stats.seconds = time.perf_counter() - started
        if decision.witness is None:
            raise RuntimeError(
                f"block {index} on wires {block.wires} reported a difference with no witness"
            )
        x_global, y_global = lift_witness(decision.witness, block)
        replay = channels_differ_at(left, right, x_global, y_global)
        if not replay:
            raise RuntimeError(
                f"block {index} witness {decision.witness} lifted to {(x_global, y_global)} "
                "does not distinguish the original programs"
            )
        return (
            ChannelDecision(
                False,
                backend,
                "full_quantum_channel",
                f"block {index} on wires {block.wires}: {decision.reason}",
                _sha(left),
                _sha(right),
                left.measurements + right.measurements,
                decision.witness_kind,
                (x_global, y_global),
            ),
            stats,
        )
    stats.seconds = time.perf_counter() - started
    return (
        ChannelDecision(
            True,
            backend,
            "full_quantum_channel",
            f"all {stats.components} disjoint blocks match "
            f"({merged} ancilla-only block(s) merged into a data block)",
            _sha(left),
            _sha(right),
            left.measurements + right.measurements,
        ),
        stats,
    )
