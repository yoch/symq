"""Factored phase semantics and a channel-equivalence criterion for the HMR fragment.

Two structural properties of the fragment accepted by :mod:`symq.phase` are proved in
``INVARIANT.md`` and checked exhaustively in ``tests/test_factored.py``:

* **F1 (outcome-free wires).** Every wire value ``f_w`` is a function of the data inputs only.
* **F2 (phase affine in outcomes).** ``phi(x, m) = phi0(x) XOR sum_j m_j g_j(x)``.

With ``K_m = 2^{-M/2} (-1)^{phi(x,m)} |f(x)><x|`` and ``E(rho) = sum_m K_m rho K_m^dagger``,
the sum over outcomes collapses to

    E(|x><y|) = (-1)^{phi0(x)+phi0(y)} [g(x) = g(y)] |f(x)><f(y)|,          (CH)

because ``sum_{m_j} (-1)^{m_j (g_j(x)+g_j(y))}`` is ``2`` when ``g_j(x)=g_j(y)`` and ``0``
otherwise; the ``2^M`` from the sum cancels ``2^{-M}`` exactly.

So the channel never needs the ``2^M`` outcome sequences. The comparison of two programs is a
statement about two Boolean functions of the ``2n`` pair variables ``(x, y)``, decided with the
same exact ZDD machinery that decides circuit equivalence -- and, crucially, with a
representation whose size is governed by the *pair* function, not by ``M``.
"""
from __future__ import annotations

from dataclasses import dataclass

from symq.anf import ANF
from symq.backends import make_algebra
from symq.phase import PhaseProgram, UnsupportedOperation
from symq.resources import Budget, Guard


@dataclass(frozen=True)
class FactoredPhase:
    """A program in the factored normal form ``(f, phi0, g)`` of F1 and F2."""

    data: int
    ancillas: int
    measurements: int
    outputs: tuple[ANF, ...]
    """``f_w`` for every wire, data wires first; F1 says these contain no outcome variable."""
    phi0: ANF
    """The outcome-free part of the phase."""
    g: tuple[ANF, ...]
    """``g_j``: the outcome coefficient of measurement ``j``."""

    @property
    def width(self) -> int:
        return self.data + self.ancillas

    def unclean_ancillas(self) -> list[int]:
        return [w for w in range(self.data, self.width) if self.outputs[w].terms]

    def outcome_dependent(self) -> tuple[int, ...]:
        """Indices ``j`` with ``g_j != 0``: exactly what the strict O2 obligation rejects."""
        return tuple(j for j, value in enumerate(self.g) if value.terms)

    def constant_outcomes(self) -> bool:
        """True iff every ``g_j`` is a *constant* Boolean, i.e. ``0`` or ``1``.

        A coefficient with a single monomial is not constant: ``g_j = x_0`` depends on the input
        and therefore restricts the kernel. Only the empty family and the family ``{1}`` (the
        monomial with mask 0) are constants.
        """
        return all(not value.terms or value.terms == frozenset({0}) for value in self.g)

    def phase_terms(self) -> int:
        """Total number of monomials kept, the memory the factorisation actually uses."""
        return len(self.phi0.terms) + sum(len(value.terms) for value in self.g)


def factor(program: PhaseProgram, budget: Budget | None = None) -> FactoredPhase:
    """Compute ``(f, phi0, g)`` by running the fragment and keeping the coefficients apart.

    The factorisation is exact ANF arithmetic on the reference representation, so it carries the
    same monomial budget as any other ANF computation: ``max_terms`` is checked after every
    instruction, and ``max_seconds`` between instructions. Without a budget it is unbounded,
    which is what the tests use on small programs.
    """
    if not isinstance(program, PhaseProgram):
        raise TypeError("a PhaseProgram is required")
    program.validate()
    guard = Guard(budget) if budget is not None else None
    state = [ANF.variable(w) if w < program.data else ANF() for w in range(program.width)]
    phi0 = ANF()
    coefficients: list[ANF] = []

    def product(qubits: tuple[int, ...]) -> ANF:
        value = ANF.constant(1)
        for qubit in qubits:
            value = value * state[qubit]
        return value

    for op in program.ops:
        if guard is not None:
            guard.check_time()
        if op.kind == "mcx":
            *controls, target = op.qubits
            state[target] = state[target] ^ product(tuple(controls))
        elif op.kind == "mcz":
            phi0 = phi0 ^ product(op.qubits)
        elif op.kind == "hmr":
            (qubit,) = op.qubits
            if op.outcome != len(coefficients):
                raise UnsupportedOperation("hmr outcome indices must be consecutive")
            coefficients.append(state[qubit])
            state[qubit] = ANF()
        elif op.kind == "mcz_if":
            index = op.outcome
            while len(coefficients) <= index:
                coefficients.append(ANF())
            coefficients[index] = coefficients[index] ^ product(op.qubits)
        else:
            raise UnsupportedOperation(op.kind)
        if guard is not None:
            guard.check_terms(sum(len(value.terms) for value in state) + len(phi0.terms)
                              + sum(len(value.terms) for value in coefficients))
    return FactoredPhase(program.data, program.ancillas, program.measurements, tuple(state),
                         phi0, tuple(coefficients))


@dataclass(frozen=True)
class ChannelVerdict:
    equivalent: bool
    reason: str
    outputs_differ_on: int | None = None
    kernel_differs: bool = False
    phase_witness: tuple[int, int] | None = None
    pairs: int = 0
    """Size of the pair space the criterion actually built (``2**width``)."""


def _pair_algebra(data: int, budget: Budget | None):
    """The pair space of the **data** variables: ``phi0`` and every ``g_j`` are functions of the
    data inputs, so a phase never needs a variable that names an ancilla."""
    return make_algebra("zdd", 2 * data, budget)


def _embed(algebra, anf: ANF, width: int, shift: int = 0):
    """``anf`` over the ``2 * width`` pair variables, optionally shifted onto the ``y`` half.

    ``shift = width`` produces ``anf(y)``; ``shift = 0`` produces ``anf(x)``.
    """
    if algebra.width != 2 * width:
        raise ValueError("the algebra must hold 2 * width pair variables")
    if any(mask >> width for mask in anf.terms):
        raise ValueError("polynomial uses variables outside the data width")
    return algebra.from_anf(ANF(frozenset(mask << shift for mask in anf.terms)))


def equivalent_channel(left: PhaseProgram, right: PhaseProgram, *,
                       budget: Budget | None = None) -> ChannelVerdict:
    """Decide ``E_left = E_right`` exactly, without enumerating measurement outcomes.

    By (CH) the two channels agree iff, for every pair ``(x, y)``,

      1. the output maps agree: ``f_L = f_R`` (the diagonal ``x = y`` forces this, since the
         kernel of a pair with ``x = y`` is always 1);
      2. the measurement kernels agree: ``[g_L(x)=g_L(y)] = [g_R(x)=g_R(y)]``;
      3. on that common kernel, ``phi0_L + phi0_R`` is constant, so the surviving coherences
         carry the same sign.

    All three are Boolean-function comparisons over ``2 * width`` pair variables, decided by
    ZDD equality. Nothing is formed in the ``M`` outcome variables.
    """
    if left.data != right.data:
        raise ValueError("programs must have the same number of data wires")
    if left.width != right.width:
        raise ValueError("programs must have the same number of ancillas to compare channels")
    a, b = factor(left, budget=budget), factor(right, budget=budget)
    width = a.width

    for wire in range(width):
        if a.outputs[wire] != b.outputs[wire]:
            return ChannelVerdict(False, f"output wire {wire} differs",
                                  outputs_differ_on=wire)

    # The phase is a function of the data inputs only (F2), so the pair space has 2 * data
    # variables and does not grow with the number of ancillas.
    algebra = _pair_algebra(a.data, budget)
    one = algebra.one()

    kernel_left = one
    for coefficient in a.g:
        kernel_left = algebra.product(
            [kernel_left, _kernel_factor(algebra, coefficient, a.data)])
    kernel_right = one
    for coefficient in b.g:
        kernel_right = algebra.product(
            [kernel_right, _kernel_factor(algebra, coefficient, a.data)])
    if not algebra.equal(kernel_left, kernel_right):
        return ChannelVerdict(False, "the measurement kernels differ", kernel_differs=True,
                              pairs=1 << (2 * a.data))

    h = a.phi0 ^ b.phi0
    difference = algebra.xor(_embed(algebra, h, a.data),
                             _embed(algebra, h, a.data, a.data))
    if difference == algebra.zero():
        return ChannelVerdict(True, "same kernel, phases agree in every class",
                              pairs=1 << (2 * a.data))
    violation = algebra.product([kernel_left, difference])
    if not algebra.is_zero(violation):
        witness = algebra.min_monomial(violation)
        return ChannelVerdict(
            False, "phases differ inside a kernel class",
            phase_witness=None if witness is None else (witness & ((1 << width) - 1),
                                                        (witness >> width) & ((1 << width) - 1)),
            pairs=1 << (2 * a.data))
    return ChannelVerdict(True, "same kernel, phases agree in every class",
                          pairs=1 << (2 * a.data))


def _kernel_factor(algebra, coefficient: ANF, width: int):
    """``[g_j(x) = g_j(y)] = 1 XOR g_j(x) XOR g_j(y)`` over the pair variables."""
    if not coefficient.terms:
        # g_j == 0: the outcome multiplies a zero phase, so the kernel factor is 1.
        return algebra.one()
    if coefficient.terms == frozenset({0}):
        # g_j == 1: m_j contributes the same (-1) to every x, so the kernel factor is 1 too.
        return algebra.one()
    value = _embed(algebra, coefficient, width)
    mirrored = _embed(algebra, coefficient, width, width)
    return algebra.xor(algebra.one(), algebra.xor(value, mirrored))
