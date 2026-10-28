"""Cuccaro adders, the family where the identity order is known to fail.

Reproduced here (not copied from the experimental branch) so the order campaign on `main` runs
against a circuit family whose structure is documented: wires are ``c0, b[0..n-1], a[0..n-1],
z, [ctl]`` and the carry chain runs ``c0 -> a[0] -> a[1] -> ... -> z``. That chain is exactly the
structure a good order should follow, which is what makes this family the discriminating test.
"""
from __future__ import annotations

from symq.circuit import Circuit


def maj(circuit: Circuit, x: int, y: int, z: int, ctl: tuple[int, ...] = ()) -> None:
    """``maj(x, y, z)``: the 3-control majority used by Cuccaro's adder."""
    circuit.mcx(*ctl, x, y)
    circuit.mcx(*ctl, x, y, z)
    circuit.mcx(*ctl, y, z)


def uma(circuit: Circuit, x: int, y: int, z: int, ctl: tuple[int, ...] = ()) -> None:
    circuit.mcx(*ctl, y, z)
    circuit.mcx(*ctl, x, y, z)
    circuit.mcx(*ctl, x, y)


def cuccaro(circuit: Circuit, a: list[int], b: list[int], carry_in: int, carry_out: int,
            ctl: tuple[int, ...] = ()) -> None:
    """``b <- a + b (mod 2^n)``, ``carry_out ^= carry``; ``carry_in`` must be 0 and is restored."""
    n = len(a)
    maj(circuit, carry_in, b[0], a[0], ctl)
    for index in range(1, n):
        maj(circuit, a[index - 1], b[index], a[index], ctl)
    circuit.mcx(*ctl, a[n - 1], carry_out)
    for index in range(n - 1, 0, -1):
        uma(circuit, a[index - 1], b[index], a[index], ctl)
    uma(circuit, carry_in, b[0], a[0], ctl)


def normalise(circuit: Circuit) -> Circuit:
    """Rename every gate after its control count, as the corpus generator does."""
    out = Circuit(circuit.width)
    for gate in circuit.gates:
        out.append({1: "x", 2: "cx", 3: "ccx"}.get(len(gate.qubits), "mcx"), *gate.qubits)
    return out


def adder(n: int, controlled: bool = False) -> Circuit:
    """Cuccaro adder of ``n`` bits; ``controlled`` adds one control wire."""
    circuit = Circuit(2 * n + 2 + int(controlled))
    b = list(range(1, n + 1))
    a = list(range(n + 1, 2 * n + 1))
    ctl = (2 * n + 2,) if controlled else ()
    cuccaro(circuit, a, b, 0, 2 * n + 1, ctl)
    return normalise(circuit)
