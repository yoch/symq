"""Ancilla obligations whose target or classical slots are not prepared by the program.

The clean-ancilla engines (``backward_ancilla.check_clean_ancilla`` and
``shift_diagonal_ancilla.check_shift_diagonal``) take a ``HybridProgram``: arbitrary
coherent data, every ancilla initially |0>, every classical slot written before it is
read. A program cut out of a larger computation often violates the last two: the wire to
clear holds whatever an earlier stage left there, and conditions read slots measured
earlier. A ``HybridProgram`` with such reads cannot even be built.

``with_inputs`` builds, from the raw operation list, the exact program in which those
inputs are produced by the program itself, from fresh data wires:

* ``initial_target="arbitrary"``: a hidden data wire is swapped into the target first, so
  the target starts with arbitrary content, possibly entangled with anything;
* ``classical_inputs=("b3", ...)``: each listed slot is first set by a Z measurement of its
  own hidden data wire, so it can take either value.

The engines then decide the usual theorem on that program, which covers every data state,
hence every initial target content and every value of the listed slots. Nothing about the
engines changes; this is the adapter a caller would otherwise write by hand, with its
layout recorded so that witnesses can be read back in the caller's terms.

``clean`` remains a statement about the final value of one wire. It is not equality of
the data channel and does not authorise removing a reset, a wire or a correction.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from symq.experimental.hybrid import HOp, HybridProgram

_SLOT = re.compile(r"b(0|[1-9][0-9]*)\Z")
_INITIAL = ("clean", "arbitrary")


@dataclass(frozen=True)
class InputLayout:
    """Where the inputs of ``with_inputs`` live in the program it returns.

    ``data`` and ``ancillas`` are the caller's counts and ``target`` the caller's target
    wire. In the returned program, the caller's data wires keep their indices, hidden wires
    follow them, and the caller's ancillas are shifted by ``hidden``.
    """

    data: int
    ancillas: int
    target: int
    initial_target: str
    target_wire: int | None
    classical_inputs: tuple[tuple[str, int], ...]

    @property
    def hidden(self) -> int:
        """Number of hidden data wires added in front of the ancillas."""
        return (self.target_wire is not None) + len(self.classical_inputs)

    @property
    def reduced_target(self) -> int:
        """The caller's target wire in the returned program."""
        return self.target + self.hidden

    def explain(self, assignment: int) -> dict:
        """Read a basis witness of the returned program in the caller's terms.

        ``data`` is the caller's data input, ``initial_target`` the target's initial basis
        value (``None`` when the target starts clean) and ``classical_inputs`` the value of
        each listed slot.
        """
        if type(assignment) is not int or not 0 <= assignment < 1 << (self.data + self.hidden):
            raise ValueError("assignment outside the returned program's data width")
        return {
            "data": assignment & ((1 << self.data) - 1),
            "initial_target": (None if self.target_wire is None
                               else assignment >> self.target_wire & 1),
            "classical_inputs": {slot: assignment >> wire & 1
                                 for slot, wire in self.classical_inputs},
        }

    def to_dict(self) -> dict:
        return {"data": self.data, "ancillas": self.ancillas, "target": self.target,
                "initial_target": self.initial_target, "target_wire": self.target_wire,
                "classical_inputs": [list(item) for item in self.classical_inputs],
                "reduced_target": self.reduced_target}


def with_inputs(data: int, ancillas: int, ops, target: int, *,
                initial_target: str = "clean",
                classical_inputs: tuple[str, ...] | list[str] = ()) -> tuple[HybridProgram, InputLayout]:
    """Return the program that prepares the declared inputs, and its layout.

    ``ops`` is the caller's operation list over ``data + ancillas`` wires, in which the
    slots of ``classical_inputs`` may be read before they are written. ``target`` must be
    one of the caller's ancillas. Pass ``program`` and ``layout.reduced_target`` to a
    clean-ancilla engine; read its witness with ``layout.explain``.

    A slot listed in ``classical_inputs`` that ``ops`` never mentions is refused, as is a
    slot that is not in canonical ``b<n>`` form or listed twice. Everything else about the
    operations is validated by ``HybridProgram`` itself, on the returned program.
    """
    for name, value in (("data", data), ("ancillas", ancillas)):
        if type(value) is not int or value < (1 if name == "data" else 0):
            raise ValueError(f"{name} must be an exact {'positive' if name == 'data' else 'nonnegative'} integer")
    if type(target) is not int or not data <= target < data + ancillas:
        raise ValueError("target must be one of the declared ancillas")
    if type(initial_target) is not str or initial_target not in _INITIAL:
        raise ValueError("initial_target must be 'clean' or 'arbitrary'")
    if type(classical_inputs) not in (tuple, list):
        raise TypeError("classical_inputs must be a tuple or list of slot names")
    slots = tuple(classical_inputs)
    if any(type(slot) is not str or _SLOT.fullmatch(slot) is None for slot in slots):
        raise ValueError("classical inputs must be canonical b0, b1, ... slot names")
    if len(set(slots)) != len(slots):
        raise ValueError("a classical input is listed twice")
    if type(ops) not in (tuple, list) or any(type(op) is not HOp for op in ops):
        raise TypeError("ops must be a list of exact HOp instances")
    mentioned = {name.removeprefix("!") for op in ops
                 for name in (op.slot, op.source, op.condition) if type(name) is str}
    unused = [slot for slot in slots if slot not in mentioned]
    if unused:
        raise ValueError(f"classical inputs never used by the program: {', '.join(unused)}")

    hidden = (initial_target == "arbitrary") + len(slots)
    width = data + ancillas

    def moved(wire):
        if type(wire) is not int or not 0 <= wire < width:
            raise ValueError("operation wire outside the declared width")
        return wire if wire < data else wire + hidden

    next_wire = data
    prefix: list[HOp] = []
    target_wire = None
    if initial_target == "arbitrary":
        target_wire = next_wire
        next_wire += 1
        prefix.append(HOp("swap", (target_wire, target + hidden)))
    placed = []
    for slot in slots:
        placed.append((slot, next_wire))
        prefix.append(HOp("measure_z", (next_wire,), slot=slot))
        next_wire += 1
    body = [HOp(op.kind, tuple(moved(q) for q in op.wires) if type(op.wires) is tuple else op.wires,
                op.slot, op.condition, op.source, op.value) for op in ops]
    program = HybridProgram(data + hidden, ancillas, prefix + body)
    layout = InputLayout(data, ancillas, target, initial_target, target_wire, tuple(placed))
    return program, layout
