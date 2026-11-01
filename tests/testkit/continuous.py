"""Continuous symbolic simulation: apply fragments to the state the previous one produced.

``NativeZDDAlgebra.simulate(circuit)`` always starts from the identity state ``[x_0, ...,
x_{n-1}]``, so calling it once per fragment restarts the simulation each time. The native
manager accepts an explicit initial state (``simulate(state, indices, offsets, targets)``), and
this module exposes exactly that capability at the algebra level.

The correctness obligation is stated once, here, and checked in
``tests/test_continuous_simulation.py``: splitting a circuit at any point and simulating the
pieces with this function must give, monomial for monomial, the same outputs as simulating the
whole circuit in one call.
"""
from __future__ import annotations

import array
import time

from symq.backends.zdd_native import NativeZDDAlgebra
from symq.circuit import Circuit


def compile_gates(circuit: Circuit) -> tuple[array.array, array.array, array.array]:
    """The three arrays the fused native loop takes, built outside any timed region."""
    indices: list[int] = []
    offsets = [0]
    targets: list[int] = []
    for gate in circuit.gates:
        qubits = gate.qubits
        indices.extend(qubits[:-1])
        offsets.append(len(indices))
        targets.append(qubits[-1])
    return (array.array("I", indices), array.array("I", offsets), array.array("I", targets))


def apply_fragment(algebra: NativeZDDAlgebra, state: tuple[int, ...], circuit: Circuit
                   ) -> tuple[int, ...]:
    """Run ``circuit`` on ``state`` and return the new wire values.

    ``state`` must have one node id per wire of ``algebra``; the returned tuple does too, and is
    the correct input for the next fragment.
    """
    if not isinstance(algebra, NativeZDDAlgebra):
        raise TypeError("a NativeZDDAlgebra is required")
    circuit.validate()
    if circuit.width != algebra.width:
        raise ValueError("circuit and algebra width differ")
    if len(state) != algebra.width:
        raise ValueError("state must have one node id per wire")
    if not circuit.gates:
        return tuple(state)
    indices, offsets, targets = compile_gates(circuit)
    roots, peak, products = algebra.manager.simulate(list(state), indices, offsets, targets)
    algebra.stats.gates += len(circuit.gates)
    algebra.stats.products += products
    if peak is not None:
        algebra.stats.observe_terms(peak)
    return tuple(roots)


def initial_state(algebra: NativeZDDAlgebra) -> tuple[int, ...]:
    return tuple(algebra.variable(index) for index in range(algebra.width))


def chunks(circuit: Circuit, count: int) -> list[Circuit]:
    """``count`` consecutive fragments covering ``circuit`` in order, none of them empty."""
    if count < 1:
        raise ValueError("count must be positive")
    size = max(1, -(-len(circuit.gates) // count))
    parts = [Circuit(circuit.width, circuit.gates[start:start + size])
             for start in range(0, len(circuit.gates), size)]
    return [part for part in parts if part.gates] or [Circuit(circuit.width)]


def simulate_in_chunks(algebra: NativeZDDAlgebra, circuit: Circuit, count: int,
                       between=None) -> tuple[int, ...]:
    """Simulate ``circuit`` as ``count`` consecutive fragments, optionally calling ``between``.

    ``between(state)`` is invoked after each fragment (including the last) with the current wire
    values; it may return a replacement state, which lets a caller model a rebuild.
    """
    state = initial_state(algebra)
    for fragment in chunks(circuit, count):
        state = apply_fragment(algebra, state, fragment)
        if between is not None:
            replacement = between(state)
            if replacement is not None:
                state = tuple(replacement)
    return state


def timed(function, *args, **kwargs):
    started = time.perf_counter()
    value = function(*args, **kwargs)
    return value, time.perf_counter() - started
