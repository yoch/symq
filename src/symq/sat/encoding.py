"""Tseitin encoding of the reversible fragment, one variable per (wire, time step).

A gate ``(C, t)`` computes ``q = AND(C)`` and flips ``t`` when ``q`` holds. The encoding must say
exactly that and nothing else, so the relation is written as a biconditional on the *next* value:

    next_t <-> (t xor q)          and          next_w <-> w  for w != t

The first version of this file wrote the biconditional only in one direction
(``q -> (next_t == t xor 1)``) and then reused the old variable for the target, which is not a
definition and lets the solver choose ``next_t`` freely when ``q`` is false. The tests caught it on
a three-gate circuit; the definition below is total, so every model is a real execution.

`q` itself is a fresh variable per gate, defined by the three standard AND clauses, and
``AND(())`` is a fresh variable forced true, which is how a bare ``X`` becomes an unconditional
flip.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from symq.circuit import Circuit


class SatUnavailable(RuntimeError):
    """No SAT solver is installed; the caller must fall back or fail, never guess."""


def solver_available() -> bool:
    return _solver_factory() is not None


# Solvers that implement ``interrupt()``. CaDiCaL (every version) and Kissat raise
# ``NotImplementedError`` from it, so a wall-clock timeout cannot be enforced with them: a
# watchdog would raise in its own thread while the solver keeps running. The first submission used
# Cadical195 and advertised a timeout it could not deliver; the audit caught it.
_INTERRUPTIBLE = ("glucose42", "glucose4", "glucose3", "minisat22", "maplesat")


def _compiled_solvers() -> frozenset[str]:
    """Names this ``python-sat`` wheel actually contains.

    ``SolverNames`` is a class whose attributes are strings only for some builds, so the reliable
    test is to construct the solver: a name the wheel lacks raises at construction.
    """
    try:
        from pysat.solvers import Solver
    except Exception:  # noqa: BLE001
        return frozenset()
    found = []
    for candidate in _INTERRUPTIBLE:
        try:
            with Solver(name=candidate, bootstrap_with=[[1]]):
                found.append(candidate)
        except Exception:  # noqa: BLE001 - probe only; a missing solver is not an error
            pass  # the name is simply not offered by this build
    return frozenset(found)


_COMPILED = _compiled_solvers()


class SolverFactory:
    """A solver constructor that remembers which solver it builds.

    ``functools.partial`` cannot carry the attribute, and the verdict must name the engine that
    produced it -- a result attributed to "unknown" is not reproducible.
    """

    def __init__(self, solver_class, name: str) -> None:
        self._class = solver_class
        self.name = name

    def __call__(self, **kwargs):
        return self._class(name=self.name, **kwargs)

    def __repr__(self) -> str:
        return f"SolverFactory({self.name!r})"


def _solver_factory(name: str | None = None) -> SolverFactory | None:
    """The solver to use, preferring one whose ``interrupt()`` actually works.

    ``python-sat`` ships CaDiCaL and Glucose; only the latter can be interrupted. CaDiCaL's
    ``interrupt`` raises ``NotImplementedError``, so a watchdog built on it would raise in its own
    thread while the solver kept running -- which is exactly the defect the audit found. The choice
    is made once and reported in the verdict.
    """
    try:
        from pysat.solvers import Solver
    except Exception:  # noqa: BLE001
        return None
    wanted = [name] if name else list(_INTERRUPTIBLE)
    for candidate in wanted:
        if candidate not in _COMPILED:
            continue
        return SolverFactory(Solver, candidate)
    return None


def interruptible_solvers() -> tuple[str, ...]:
    """The solvers this installation can actually interrupt, in preference order."""
    available = []
    for name in _INTERRUPTIBLE:
        try:
            from pysat.solvers import Solver

            with Solver(name=name, bootstrap_with=[[1]]) as solver:
                solver.interrupt()
                available.append(name)
        except Exception:  # noqa: BLE001 - probe only; an unimplemented interrupt is expected
            pass
    return tuple(available)


def solver_name(factory) -> str:
    """The solver a factory will instantiate."""
    return str(getattr(factory, "name", "unknown"))


@dataclass
class Encoder:
    """Accumulates CNF clauses and allocates variables."""

    clauses: list[list[int]] = field(default_factory=list)
    next_variable: int = 1

    def new(self) -> int:
        variable = self.next_variable
        self.next_variable += 1
        return variable

    def add(self, *literals: int) -> None:
        self.clauses.append(list(literals))

    def equiv(self, left: int, right: int) -> None:
        self.add(-left, right)
        self.add(left, -right)

    def and_gate(self, left: int, right: int) -> int:
        """``out <-> left AND right``."""
        out = self.new()
        self.add(-out, left)
        self.add(-out, right)
        self.add(out, -left, -right)
        return out

    def conjunction(self, literals: list[int]) -> int:
        """``AND`` of positive literals; an empty conjunction is a variable forced true."""
        if not literals:
            out = self.new()
            self.add(out)
            return out
        result = literals[0]
        for literal in literals[1:]:
            result = self.and_gate(result, literal)
        return result

    def xor_gate(self, left: int, right: int) -> int:
        """``out <-> left XOR right`` for two variables."""
        out = self.new()
        self.add(-out, left, right)
        self.add(-out, -left, -right)
        self.add(out, -left, right)
        self.add(out, left, -right)
        return out


@dataclass
class Transitions:
    """``layers[t][wire]`` is the variable holding wire ``wire`` after the first ``t`` gates."""

    layers: list[list[int]]

    @property
    def inputs(self) -> list[int]:
        return self.layers[0]

    @property
    def outputs(self) -> list[int]:
        return self.layers[-1]


def encode_circuit(encoder: Encoder, circuit: Circuit) -> Transitions:
    """Encode the gate list; every gate defines the next layer completely.

    The IR is validated first, for the same reason every other entry point validates it: the gate
    list is public and mutable, and an unknown operation must be refused rather than encoded as a
    flip.
    """
    if not isinstance(circuit, Circuit):
        raise TypeError("a Circuit is required")
    circuit.validate()
    current = [encoder.new() for _ in range(circuit.width)]
    layers = [current]
    for gate in circuit.gates:
        *controls, target = gate.qubits
        active = encoder.conjunction([current[control] for control in controls])
        flipped = encoder.xor_gate(current[target], active)
        following = list(current)
        following[target] = flipped
        # The flip variable *is* the next value; all other wires are carried over unchanged. No
        # separate copy is made, so no variable can be left unconstrained.
        current = following
        layers.append(list(current))
    return Transitions(layers)


@dataclass
class Contract:
    """What a verification may assume and must observe.

    * ``input_constants``: wires forced to a value on both circuits (the domain restriction);
    * ``observed_outputs``: wires whose final value must agree; ``None`` means all;
    * ``restored_wires``: wires that must return to their input value (clean ancilla, borrowed
      wire);
    * ``output_map``: ``{left_wire: right_wire}`` when a wire permutation is allowed.
    """

    input_constants: dict[int, int] = field(default_factory=dict)
    observed_outputs: tuple[int, ...] | None = None
    restored_wires: tuple[int, ...] = ()
    output_map: dict[int, int] = field(default_factory=dict)

    def validate(self, width: int) -> None:
        for wire, value in self.input_constants.items():
            if not isinstance(wire, int) or isinstance(wire, bool) or not 0 <= wire < width:
                raise ValueError(f"input_constants: wire {wire!r} outside width {width}")
            if value not in (0, 1):
                raise ValueError(f"input_constants: wire {wire} must be 0 or 1")
        if self.observed_outputs is not None:
            for wire in self.observed_outputs:
                if not isinstance(wire, int) or isinstance(wire, bool) or not 0 <= wire < width:
                    raise ValueError(f"observed_outputs: wire {wire!r} outside width {width}")
            if len(set(self.observed_outputs)) != len(self.observed_outputs):
                raise ValueError("observed_outputs must not repeat a wire")
        for wire in self.restored_wires:
            if not isinstance(wire, int) or isinstance(wire, bool) or not 0 <= wire < width:
                raise ValueError(f"restored_wires: wire {wire!r} outside width {width}")
        if self.output_map:
            for left, right in self.output_map.items():
                if not isinstance(left, int) or not 0 <= left < width:
                    raise ValueError(f"output_map: wire {left!r} outside width {width}")
                if not isinstance(right, int) or not 0 <= right < width:
                    raise ValueError(f"output_map: wire {right!r} outside width {width}")
            if len(set(self.output_map.values())) != len(self.output_map):
                raise ValueError("output_map must be injective")
            if set(self.restored_wires) & set(self.output_map.keys()):
                raise ValueError("a restored wire cannot also be mapped")
            if set(self.restored_wires) & set(self.output_map.values()):
                raise ValueError("a restored wire cannot also be mapped")
            if self.observed_outputs is not None:
                raise ValueError("observed_outputs and output_map are mutually exclusive")


@dataclass
class SatVerdict:
    """``outcome`` is ``equivalent``, ``different`` or ``inconclusive``.

    Only the first two carry a claim; ``different`` always carries a witness that was replayed
    through ``Circuit.run`` and really differs.
    """

    outcome: str
    witness: int | None = None
    witness_checked: bool | None = None
    first_differing_output: int | None = None
    seconds: float = 0.0
    clauses: int = 0
    variables: int = 0
    detail: str = ""
    solver: str = ""

    @property
    def equivalent(self) -> bool | None:
        return {"equivalent": True, "different": False}.get(self.outcome)
