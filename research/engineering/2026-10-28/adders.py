"""Cuccaro ripple-carry adder, verified against arithmetic on every legal input.

The previous version of this file was **wrong** and the audit found it: ``maj`` and ``uma`` were the
same three gates in reverse order, so the circuit computed something that is not addition, and 13
of the 19 circuits in the order campaign were built from it. The gate list below is the one of the
corpus generator that had been validated by concrete execution, and ``tests/test_adders.py`` checks
the arithmetic exhaustively for 1-4 bits against integer addition.

Wire layout: ``c0, b[0..n-1], a[0..n-1], z, [ctl]``. The circuit requires ``c0 = 0`` and restores
it; afterwards ``b`` holds ``a + b mod 2^n``, ``z`` is XORed with the carry out, and ``a`` is
destroyed. ``ctl`` (when present) makes the whole adder conditional.
"""
from __future__ import annotations

from symq.circuit import Circuit


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
    """``b <- a + b (mod 2^n)``; ``carry_out ^= carry``; ``carry_in`` must be 0 and is restored."""
    n = len(a)
    _maj(circuit, carry_in, b[0], a[0], ctl)
    for index in range(1, n):
        _maj(circuit, a[index - 1], b[index], a[index], ctl)
    circuit.mcx(*ctl, a[n - 1], carry_out)
    for index in range(n - 1, 0, -1):
        _uma(circuit, a[index - 1], b[index], a[index], ctl)
    _uma(circuit, carry_in, b[0], a[0], ctl)


def normalise(circuit: Circuit) -> Circuit:
    """Rename every gate after its control count, as the corpus generator does."""
    out = Circuit(circuit.width)
    for gate in circuit.gates:
        out.append({1: "x", 2: "cx", 3: "ccx"}.get(len(gate.qubits), "mcx"), *gate.qubits)
    return out


def adder(n: int, controlled: bool = False) -> Circuit:
    """Cuccaro adder of ``n`` bits; ``controlled`` adds one control wire at the end."""
    circuit = Circuit(2 * n + 2 + int(controlled))
    b = list(range(1, n + 1))
    a = list(range(n + 1, 2 * n + 1))
    ctl = (2 * n + 2,) if controlled else ()
    cuccaro(circuit, a, b, 0, 2 * n + 1, ctl)
    return normalise(circuit)


def expected_output(n: int, x: int, controlled: bool = False) -> int:
    """The assignment ``x`` mapped through ``b <- a + b``, by plain integer arithmetic.

    Only ``carry_in = 0`` is a legal input; the function refuses anything else rather than
    computing a value for a state the circuit is not defined on.
    """
    if (x >> 0) & 1:
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


def legal_inputs(n: int, controlled: bool = False) -> list[int]:
    """Assignments with ``carry_in = 0``: the domain the circuit is defined on."""
    circuit = adder(n, controlled)
    return [x for x in range(1 << circuit.width) if not x & 1]
