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

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from symq.circuit import Circuit
from symq.errors import SatUnavailable  # noqa: F401 - re-exported for compatibility


def solver_available() -> bool:
    return _solver_factory() is not None


# Solvers that implement ``interrupt()``. CaDiCaL (every version) and Kissat raise
# ``NotImplementedError`` from it, so a wall-clock timeout cannot be enforced with them: a
# watchdog would raise in its own thread while the solver keeps running. The first submission used
# Cadical195 and advertised a timeout it could not deliver; the audit caught it.
_INTERRUPTIBLE = ("glucose42", "glucose4", "glucose3", "minisat22", "maplesat")


def _can_interrupt(name: str) -> bool:
    """True if this build offers ``name`` and its ``interrupt()`` is implemented.

    A single predicate keeps the two failure modes -- "not compiled" and "interrupt not
    implemented" -- out of the caller, so no ``except`` block has to decide anything.
    """
    try:
        from pysat.solvers import Solver

        with Solver(name=name, bootstrap_with=[[1]]) as solver:
            solver.interrupt()
        return True
    except Exception:  # noqa: BLE001 - either mode means "unusable for a timed run"
        return False


@cache
def _compiled_solvers() -> frozenset[str]:
    """Names this ``python-sat`` wheel offers *and* can interrupt (probed once, on first use)."""
    return frozenset(name for name in _INTERRUPTIBLE if _can_interrupt(name))


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
        if candidate not in _compiled_solvers():
            continue
        return SolverFactory(Solver, candidate)
    return None


def interruptible_solvers() -> tuple[str, ...]:
    """The solvers this installation can actually interrupt, in preference order."""
    return tuple(name for name in _INTERRUPTIBLE if name in _compiled_solvers())


def solver_name(factory) -> str:
    """The solver a factory will instantiate."""
    return str(getattr(factory, "name", "unknown"))


@dataclass
class Encoder:
    """Accumulates CNF clauses and allocates variables.

    Gate definitions are *structurally hashed*: asking twice for ``a AND b`` or ``a XOR b`` returns
    the same literal, so identical sub-circuits (for example a common prefix of two circuits that
    share their inputs) are encoded once. Constants are folded through a single variable forced
    true. Reusing a Tseitin variable for the same function of the same literals preserves
    satisfiability exactly.
    """

    clauses: list[list[int]] = field(default_factory=list)
    next_variable: int = 1
    _true: int | None = None
    _gates: dict[tuple[str, int, int], int] = field(default_factory=dict)

    def new(self) -> int:
        """Allocate and return a fresh variable (a positive integer)."""
        variable = self.next_variable
        self.next_variable += 1
        return variable

    def add(self, *literals: int) -> None:
        """Add one clause: the disjunction of ``literals`` (negative means negated)."""
        self.clauses.append(list(literals))

    def equiv(self, left: int, right: int) -> None:
        """Constrain the two literals to be equal."""
        self.add(-left, right)
        self.add(left, -right)

    def true(self) -> int:
        """A literal forced true (allocated once)."""
        if self._true is None:
            self._true = self.new()
            self.add(self._true)
        return self._true

    def and_gate(self, left: int, right: int) -> int:
        """A literal equivalent to ``left AND right``."""
        true = self.true()
        if left == true:
            return right
        if right == true:
            return left
        if left == -true or right == -true or left == -right:
            return -true
        if left == right:
            return left
        key = ("and", min(left, right), max(left, right))
        out = self._gates.get(key)
        if out is None:
            out = self.new()
            self.add(-out, left)
            self.add(-out, right)
            self.add(out, -left, -right)
            self._gates[key] = out
        return out

    def conjunction(self, literals: list[int]) -> int:
        """``AND`` of literals; the empty conjunction is the true literal."""
        result = self.true()
        for literal in literals:
            result = self.and_gate(result, literal)
        return result

    def xor_gate(self, left: int, right: int) -> int:
        """A literal equivalent to ``left XOR right``; negations are pushed onto the result."""
        true = self.true()
        negate = (left < 0) != (right < 0)
        left, right = abs(left), abs(right)
        if left == right:
            out = true  # x XOR x is false, x XOR NOT x is true
            return out if negate else -out
        if left == true or right == true:
            out = right if left == true else left  # x XOR true is NOT x
            return out if negate else -out
        key = ("xor", min(left, right), max(left, right))
        cached = self._gates.get(key)
        if cached is None:
            cached = self.new()
            self.add(-cached, left, right)
            self.add(-cached, -left, -right)
            self.add(cached, -left, right)
            self.add(cached, left, -right)
            self._gates[key] = cached
        return -cached if negate else cached


@dataclass
class Transitions:
    """Input variables and output literals of one encoded circuit.

    ``inputs[wire]`` is always a positive variable (witnesses are read from it); ``outputs[wire]``
    is a literal and may be negative, for example after an X gate.
    """

    inputs: list[int]
    outputs: list[int]


def _poll_gates(gates, checkpoint: Callable[[], None]):
    """Call ``checkpoint`` every 64 gates and once after the last one.

    Used only when a caller supplies a checkpoint: ``check_sat_equivalence`` does so when its
    budget has a deadline, and bounded research encodings do so for their own caps. Without a
    checkpoint the gate loop is the plain one.
    """
    for index, gate in enumerate(gates):
        if index % 64 == 0:
            checkpoint()
        yield gate
    checkpoint()


def encode_circuit(encoder: Encoder, circuit: Circuit,
                   inputs: list[int] | None = None, *,
                   checkpoint: Callable[[], None] | None = None) -> Transitions:
    """Encode the gate list; every gate defines the next value of its target completely.

    ``inputs`` reuses existing input variables (for example those of the other side of a miter),
    so two circuits over the same inputs need no tying clauses and share every identical
    sub-circuit through structural hashing.

    The IR is validated first, for the same reason every other entry point validates it: the gate
    list is public and mutable, and an unknown operation must be refused rather than encoded as a
    flip.
    """
    if not isinstance(circuit, Circuit):
        raise TypeError("a Circuit is required")
    circuit.validate()
    return _encode_validated(encoder, circuit, inputs, checkpoint)


def _encode_validated(encoder: Encoder, circuit: Circuit, inputs: list[int] | None,
                      checkpoint: Callable[[], None] | None) -> Transitions:
    """``encode_circuit`` for a circuit the caller has just validated in the same call."""
    if inputs is None:
        current = [encoder.new() for _ in range(circuit.width)]
    else:
        if len(inputs) != circuit.width or any(type(v) is not int or v < 1 for v in inputs):
            raise ValueError("inputs must be one positive variable per wire")
        current = list(inputs)
    initial = list(current)
    # Without a checkpoint this is the original plain gate loop.
    gates = circuit.gates if checkpoint is None else _poll_gates(circuit.gates, checkpoint)
    for gate in gates:
        *controls, target = gate.qubits
        active = encoder.conjunction([current[control] for control in controls])
        current[target] = encoder.xor_gate(current[target], active)
    return Transitions(initial, current)


@dataclass
class Contract:
    """What a verification may assume and must observe.

    * ``input_constants``: wires forced to a value on both circuits (the domain restriction);
    * ``observed_outputs``: wires whose final value must agree; ``None`` means all;
    * ``restored_wires``: wires that must return to their input value (clean ancilla, borrowed
      wire);
    * ``output_map``: ``{left_wire: right_wire}`` when a wire permutation is allowed. When it is
      given, ONLY the listed pairs are compared: unmapped wires are not observed at all, so a
      partial map is a weaker contract than ``observed_outputs=None`` (all wires);
    * ``assumption``: a closed Boolean expression (``symq.sat.assumptions``) over the input names
      ``x.<wire>`` that every input must satisfy -- affine relations, finite domains, any predicate.
      Witnesses are replayed against it, and an assumption no input satisfies makes every check
      vacuously ``equivalent``, so callers should check satisfiability when that matters.
    """

    input_constants: dict[int, int] = field(default_factory=dict)
    observed_outputs: tuple[int, ...] | None = None
    restored_wires: tuple[int, ...] = ()
    output_map: dict[int, int] = field(default_factory=dict)
    assumption: Any = None

    def snapshot(self, *, check: Callable[[], None] | None = None) -> Contract:
        """A detached copy for analyses that must not trust the original objects.

        Every container is copied and every integer rebuilt as an exact ``int`` (``int.__int__``
        bypasses subclass overrides, so an ``int`` subclass cannot change its hash, equality or
        index after the copy); other values are kept for :meth:`validate` to refuse. The
        assumption is copied by :func:`symq.sat.assumptions.copy_expression`. ``check`` (for example a
        budget's time check) runs once per element and per assumption node: the copy precedes
        validation, so an oversized contract must be interruptible while it is copied.
        """
        from .assumptions import copy_expression

        def tick() -> None:
            if check is not None:
                check()

        def exact(value: Any) -> Any:
            tick()
            if isinstance(value, int) and not isinstance(value, bool):
                return int.__int__(value)
            return value

        tick()
        constants = {}
        for wire, bit in self.input_constants.items():
            constants[exact(wire)] = bit
        observed = (None if self.observed_outputs is None
                    else tuple(exact(wire) for wire in self.observed_outputs))
        restored = tuple(exact(wire) for wire in self.restored_wires)
        output_map = {}
        for left, right in self.output_map.items():
            output_map[exact(left)] = exact(right)
        assumption = None if self.assumption is None else copy_expression(self.assumption, check=check)
        return Contract(constants, observed, restored, output_map, assumption)

    def validate(self, width: int) -> None:
        """Raise ``ValueError`` unless the contract is well formed for circuits of ``width`` wires.

        Every named wire must exist, no wire may be listed twice in a field, and the fields must
        be compatible with one another (see the class docstring).
        """
        if self.assumption is not None:
            from .assumptions import validate

            validate(self.assumption, frozenset(f"x.{wire}" for wire in range(width)))
        for wire, value in self.input_constants.items():
            if not isinstance(wire, int) or isinstance(wire, bool) or not 0 <= wire < width:
                raise ValueError(f"input_constants: wire {wire!r} outside width {width}")
            if type(value) is not int or value not in (0, 1):
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
        if len(set(self.restored_wires)) != len(self.restored_wires):
            raise ValueError("restored_wires must not repeat a wire")
        if self.output_map:
            for left, right in self.output_map.items():
                if type(left) is not int or not 0 <= left < width:
                    raise ValueError(f"output_map: wire {left!r} outside width {width}")
                if type(right) is not int or not 0 <= right < width:
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
    ignored_limits: tuple[str, ...] = ()
    """Budget limits that were set but that this engine does not apply (``max_terms``,
    ``max_nodes``, ``max_bytes``): SAT applies only the deadline. Informative only; the
    verdict does not depend on them."""

    @property
    def equivalent(self) -> bool | None:
        """``True`` if proved equivalent, ``False`` if proved different, ``None`` if inconclusive."""
        return {"equivalent": True, "different": False}.get(self.outcome)
