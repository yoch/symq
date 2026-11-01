"""Reversible arithmetic circuits with exact integer reference semantics.

Every generator comes with a plain-integer reference (``*_expected_output``) and its legal input
domain, so a test can check the circuit exhaustively instead of trusting the construction.
"""
from __future__ import annotations

from ..circuit import Circuit

__all__ = [
    "cuccaro",
    "cuccaro_adder",
    "cuccaro_expected_output",
    "cuccaro_legal_inputs",
    "normalise",
]


def _maj(circuit: Circuit, x: int, y: int, z: int, ctl: tuple[int, ...] = ()) -> None:
    """``MAJ(x, y, z)``: ``z`` receives the majority, ``x`` and ``y`` take ``z`` in."""
    circuit.mcx(*ctl, z, y)
    circuit.mcx(*ctl, z, x)
    circuit.mcx(*ctl, x, y, z)


def _uma(circuit: Circuit, x: int, y: int, z: int, ctl: tuple[int, ...] = ()) -> None:
    """The block that undoes :func:`_maj` **in the adder's context**, not in isolation."""
    circuit.mcx(*ctl, x, y, z)
    circuit.mcx(*ctl, z, x)
    circuit.mcx(*ctl, x, y)


def cuccaro(circuit: Circuit, a: list[int], b: list[int], carry_in: int, carry_out: int,
            ctl: tuple[int, ...] = ()) -> None:
    """Append ``b <- a + b (mod 2^n)``; ``carry_out ^= carry``; ``carry_in`` must be 0.

    ``carry_in`` is restored and ``a`` is preserved. With ``ctl`` every gate is additionally
    controlled, so the whole adder is conditional.
    """
    n = len(a)
    if n < 1 or len(b) != n:
        raise ValueError("a and b must be registers of the same positive length")
    _maj(circuit, carry_in, b[0], a[0], ctl)
    for index in range(1, n):
        _maj(circuit, a[index - 1], b[index], a[index], ctl)
    circuit.mcx(*ctl, a[n - 1], carry_out)
    for index in range(n - 1, 0, -1):
        _uma(circuit, a[index - 1], b[index], a[index], ctl)
    _uma(circuit, carry_in, b[0], a[0], ctl)


def normalise(circuit: Circuit) -> Circuit:
    """Rename every gate after its control count (``x``/``cx``/``ccx``/``mcx``)."""
    out = Circuit(circuit.width)
    for gate in circuit.gates:
        out.append({1: "x", 2: "cx", 3: "ccx"}.get(len(gate.qubits), "mcx"), *gate.qubits)
    return out


def _width(n: int, controlled: bool) -> int:
    if type(n) is not int or n < 1:
        raise ValueError("n must be a positive integer")
    return 2 * n + 2 + int(bool(controlled))


def cuccaro_adder(n: int, controlled: bool = False) -> Circuit:
    """Cuccaro ripple-carry adder of ``n`` bits.

    Wire layout: ``c0, b[0..n-1], a[0..n-1], z, [ctl]``. The circuit requires ``c0 = 0`` and
    restores it; afterwards ``b`` holds ``a + b mod 2^n``, ``z`` is XORed with the carry out and
    ``a`` is unchanged. ``controlled`` appends one control wire that makes the adder conditional.
    """
    circuit = Circuit(_width(n, controlled))
    b = list(range(1, n + 1))
    a = list(range(n + 1, 2 * n + 1))
    ctl = (2 * n + 2,) if controlled else ()
    cuccaro(circuit, a, b, 0, 2 * n + 1, ctl)
    return normalise(circuit)


def cuccaro_expected_output(n: int, x: int, controlled: bool = False) -> int:
    """The assignment ``x`` mapped through ``b <- a + b`` by plain integer arithmetic.

    Only ``carry_in = 0`` is a legal input; anything else is refused rather than given a value
    for a state the circuit is not specified on.
    """
    _width(n, controlled)
    if x & 1:
        raise ValueError("the Cuccaro adder requires carry_in = 0")
    b = [(x >> (1 + index)) & 1 for index in range(n)]
    a = [(x >> (1 + n + index)) & 1 for index in range(n)]
    total = sum(bit << index for index, bit in enumerate(a)) + sum(
        bit << index for index, bit in enumerate(b))
    if controlled and not ((x >> (2 * n + 2)) & 1):
        return x
    result = x & ~(((1 << n) - 1) << 1)
    result |= (total & ((1 << n) - 1)) << 1
    result ^= ((total >> n) & 1) << (2 * n + 1)
    return result


def cuccaro_legal_inputs(n: int, controlled: bool = False) -> list[int]:
    """Assignments with ``carry_in = 0``: the domain the adder is specified on."""
    return [x for x in range(1 << _width(n, controlled)) if not x & 1]
