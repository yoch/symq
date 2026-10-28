"""Affine XAG encoder: wires as affine GF(2) forms over inputs and AND nodes.

The hypothesis of issue #69 is that reversible circuits are mostly linear (X/CX) with comparatively
few nonlinearities (CCX/MCX), and that the transition-based encoder wastes variables on every
intermediate step. Here each wire is an *expression*

    wire = const XOR (XOR of input variables) XOR (XOR of AND variables)

and a Boolean variable appears only when a nonlinearity does, i.e. when a gate has two or more
controls. ``X`` toggles the constant, ``CX`` XORs one affine form into another, and a gate with
``k >= 2`` controls introduces the chain of AND variables for the product of its controls.

Two encoding choices matter for size, and both are measured rather than assumed:

* an **AND** is a biconditional ``v <-> (a AND b)``: three clauses, exact;
* an **XOR** of ``k`` literals is a chain of ``k - 1`` auxiliary variables, four clauses each.
  Expanding an XOR into its ``2^(k-1)`` forbidden assignments is exact too, but a 40-term affine
  form would then need 2^39 clauses; the chain is linear and equally exact.

What this module does **not** do: it does not claim XAG novelty (the representation is standard in
quantum compilation), it does not replace the transition encoder, and it is not a default.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from symq.circuit import Circuit


class XagUnavailable(RuntimeError):
    """The XAG encoder cannot express this request; the caller must fall back, never guess."""


@dataclass(frozen=True)
class Affine:
    """``const xor (xor of inputs) xor (xor of AND variables)``, as three integer bitsets."""

    const: int
    inputs: int
    ands: int

    def xor(self, other: Affine) -> Affine:
        return Affine(self.const ^ other.const, self.inputs ^ other.inputs, self.ands ^ other.ands)

    def is_constant(self) -> bool:
        return not self.inputs and not self.ands

    def constant_value(self) -> int | None:
        return self.const if self.is_constant() else None

    @property
    def support_size(self) -> int:
        """Distinct variables the form depends on; the XOR-length metric the issue asks for."""
        return self.inputs.bit_count() + self.ands.bit_count()


@dataclass(frozen=True)
class AndNode:
    """``variable <-> left AND right``, with affine operands."""

    variable: int
    left: Affine
    right: Affine


@dataclass
class XagCircuit:
    """The intermediate form: affine wire values plus the AND definitions they reference."""

    width: int
    inputs: list[int]
    wires: list[Affine]
    ands: list[AndNode] = field(default_factory=list)
    variables: int = 0
    xor_lengths: list[int] = field(default_factory=list)

    def and_variable(self, left: Affine, right: Affine) -> Affine:
        """Define ``v = left AND right`` once, with constant folding, and return ``v``."""
        constant = left.constant_value()
        if constant is not None:
            return right if constant else Affine(0, 0, 0)
        constant = right.constant_value()
        if constant is not None:
            return left if constant else Affine(0, 0, 0)
        if left == right:
            return left
        for node in self.ands:
            if {node.left, node.right} == {left, right}:
                return Affine(0, 0, 1 << (node.variable - 1))
        self.variables += 1
        node = AndNode(self.variables, left, right)
        self.ands.append(node)
        return Affine(0, 0, 1 << (node.variable - 1))


def build_xag(circuit: Circuit, reserved: int = 0) -> XagCircuit:
    """Translate a circuit into affine forms; no clause is emitted here.

    ``reserved`` shifts every variable of this model above variables already used by another
    model. Two circuits compared in one miter must not share AND variables: they compute different
    products, and reusing a number would make the solver equate two unrelated functions. The
    *input* variables are shifted by the same amount and then tied together by the miter, which is
    what makes both circuits see one assignment.
    """
    if not isinstance(circuit, Circuit):
        raise TypeError("a Circuit is required")
    circuit.validate()
    inputs = [reserved + index + 1 for index in range(circuit.width)]
    model = XagCircuit(circuit.width, inputs,
                       [Affine(0, 1 << index, 0) for index in range(circuit.width)],
                       variables=reserved + circuit.width)
    for gate in circuit.gates:
        *controls, target = gate.qubits
        if not controls:
            model.wires[target] = model.wires[target].xor(Affine(1, 0, 0))
            continue
        product = model.wires[controls[0]]
        for control in controls[1:]:
            product = model.and_variable(product, model.wires[control])
        model.wires[target] = model.wires[target].xor(product)
    model.xor_lengths = [wire.support_size for wire in model.wires]
    return model


class XagEncoder:
    """CNF builder for two XAG models sharing one input assignment.

    ``new()`` allocates a variable; ``literal(form, model)`` returns one literal equal to the form,
    creating the AND definitions and XOR chains that form needs. Everything is emitted lazily, so a
    form that is never compared costs nothing.
    """

    def __init__(self, reserved: int = 0) -> None:
        """``reserved`` variables are already used by the models' inputs and AND definitions.

        The models number their AND variables from ``width + 1`` upwards, so the CNF encoder must
        start after the largest of them; otherwise ``new()`` would hand out a number that already
        means an input or an AND, and two unrelated things would share a variable.
        """
        self.clauses: list[list[int]] = []
        self.next_variable: int = reserved + 1
        self._true: int | None = None
        self._and_literals: dict[int, int] = {}
        self._xor_cache: dict[tuple[int, int], int] = {}

    def new(self) -> int:
        variable = self.next_variable
        self.next_variable += 1
        return variable

    def add(self, *literals: int) -> None:
        self.clauses.append(list(literals))

    def true(self) -> int:
        if self._true is None:
            self._true = self.new()
            self.add(self._true)
        return self._true

    def xor_literal(self, left: int, right: int) -> int:
        """``out <-> left XOR right``, memoised so a repeated chain is not rebuilt."""
        key = (min(left, right), max(left, right))
        cached = self._xor_cache.get(key)
        if cached is not None:
            return cached
        out = self.new()
        self.add(-out, left, right)
        self.add(-out, -left, -right)
        self.add(out, -left, right)
        self.add(out, left, -right)
        self._xor_cache[key] = out
        return out

    def literal(self, form: Affine, model: XagCircuit) -> int:
        """A single literal equal to ``form``, defining whatever it references on the way."""
        literals = self._operands(form, model)
        value = self._fold(literals)
        return -value if form.const else value

    def _operands(self, form: Affine, model: XagCircuit) -> list[int]:
        """The literals whose XOR is ``form`` with its constant ignored."""
        operands: list[int] = [model.inputs[index]
                               for index in range(form.inputs.bit_length())
                               if form.inputs >> index & 1]
        for node in model.ands:
            if form.ands >> (node.variable - 1) & 1:
                operands.append(self.and_literal(node, model))
        return operands

    def and_literal(self, node: AndNode, model: XagCircuit) -> int:
        """The literal of ``node``, emitting ``v <-> left AND right`` on first request.

        The model's own variable number for the AND is used as the CNF variable, so the
        intermediate form and the CNF share one numbering instead of drifting apart.
        """
        cached = self._and_literals.get(node.variable)
        if cached is not None:
            return cached
        left = self.literal(node.left, model)
        right = self.literal(node.right, model)
        variable = node.variable
        self.add(-variable, left)
        self.add(-variable, right)
        self.add(variable, -left, -right)
        self._and_literals[node.variable] = variable
        return variable

    def _fold(self, literals: list[int]) -> int:
        if not literals:
            return self.true()
        result = literals[0]
        for literal in literals[1:]:
            result = self.xor_literal(result, literal)
        return result
