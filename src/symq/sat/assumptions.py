"""A tiny, closed, validated Boolean expression IR, and its exact Tseitin encoding.

Issue #71 asks for quantifier-free assumptions such as ``a[3] = a[1] XOR a[2]`` over existing
input wires, with a **closed** grammar: anything outside it is rejected rather than approximated,
and no free-form Python callable can ever become an assumption (it would be neither reproducible
nor encodable).

Grammar (everything else raises):

    Expr := const(bool)
          | var(name)                    a declared variable of the expression
          | NOT(Expr)
          | XOR(Expr, Expr)              binary, so the shape is unambiguous
          | AND(Expr, Expr)
          | EQ(Expr, Expr)

Variables are *named* rather than numbered because the same expression is used over two different
circuits: in ``P(x)`` a name refers to the shared input wire of both, and in a cut relation ``R``
two names ``u.3`` and ``u'.3`` refer to the same wire of the two candidates. That naming is what
makes a *relational* interface expressible at all -- blind wire-by-wire equality cannot say
``u' = u XOR mask``.
"""
from __future__ import annotations

from dataclasses import dataclass

MAX_DEPTH = 24
"""Depth bound: an assumption is a small formula, not a program. Checked, not documented only."""


class ExprError(ValueError):
    """The expression is outside the closed grammar, or malformed."""


@dataclass(frozen=True)
class Const:
    value: bool

    def __post_init__(self) -> None:
        if not isinstance(self.value, bool):
            raise ExprError(f"Const takes a bool, not {type(self.value).__name__}")


@dataclass(frozen=True)
class Var:
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ExprError("Var takes a non-empty string name")
        if not all(character.isalnum() or character in "._'" for character in self.name):
            raise ExprError(f"Var name {self.name!r} has characters outside [A-Za-z0-9._']")


@dataclass(frozen=True)
class Not:
    operand: Expr


@dataclass(frozen=True)
class Xor:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class And:
    left: Expr
    right: Expr


@dataclass(frozen=True)
class Eq:
    left: Expr
    right: Expr


Expr = Const | Var | Not | Xor | And | Eq


def depth(expression: Expr) -> int:
    if isinstance(expression, (Const, Var)):
        return 1
    if isinstance(expression, Not):
        return 1 + depth(expression.operand)
    return 1 + max(depth(expression.left), depth(expression.right))


def variables(expression: Expr) -> frozenset[str]:
    if isinstance(expression, Const):
        return frozenset()
    if isinstance(expression, Var):
        return frozenset({expression.name})
    if isinstance(expression, Not):
        return variables(expression.operand)
    return variables(expression.left) | variables(expression.right)


def validate(expression: Expr, declared: frozenset[str] | set[str]) -> None:
    """Check the grammar, the depth bound and that every variable is declared.

    Called by every entry point: an assumption that mentions an undeclared variable could be
    silently dropped by an encoder, which is exactly the kind of vacuous certificate the issue
    forbids.
    """
    if not isinstance(expression, (Const, Var, Not, Xor, And, Eq)):
        raise ExprError(f"{type(expression).__name__} is outside the closed grammar")
    if depth(expression) > MAX_DEPTH:
        raise ExprError(f"expression depth {depth(expression)} exceeds the bound {MAX_DEPTH}")
    used = variables(expression)
    if isinstance(declared, (set, frozenset)):
        unknown = used - set(declared)
    else:  # pragma: no cover - defensive
        raise ExprError("declared variables must be a set or frozenset")
    if unknown:
        raise ExprError(f"undeclared variables: {sorted(unknown)}")


class CnfSink:
    """The three operations the emitter needs, adapted to an existing encoder.

    ``symq.sat.encoding.Encoder`` allocates variables and clauses but has no ``true`` or XOR
    helper, and the archived XAG encoder is off-limits (negative pilot, #76), so this adapter adds
    them on top of ``new``/``add`` rather than duplicating a second clause builder.
    """

    def __init__(self, encoder) -> None:
        self._encoder = encoder
        self._true: int | None = None
        self._xor_cache: dict[tuple[int, int], int] = {}

    def new(self) -> int:
        return self._encoder.new()

    def add(self, *literals: int) -> None:
        self._encoder.add(*literals)

    def true(self) -> int:
        if self._true is None:
            self._true = self.new()
            self.add(self._true)
        return self._true

    def xor_literal(self, left: int, right: int) -> int:
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


def tseitin(expression: Expr, encoder, literal_of) -> int:
    """Emit exact clauses for ``expression`` and return a literal that is true iff it holds.

    ``literal_of(name)`` maps a variable name to a positive CNF literal, so the same expression can
    be instantiated over two circuits by passing a different mapping. Every connective is a
    biconditional, so no model can satisfy the clauses while the formula is false.
    """
    return _emit(expression, CnfSink(encoder), literal_of, 0)


def _emit(expression: Expr, encoder, literal_of, level: int) -> int:
    if level > MAX_DEPTH:
        raise ExprError(f"expression depth exceeds the bound {MAX_DEPTH}")
    if isinstance(expression, Const):
        return encoder.true() if expression.value else -encoder.true()
    if isinstance(expression, Var):
        return literal_of(expression.name)
    if isinstance(expression, Not):
        return -_emit(expression.operand, encoder, literal_of, level + 1)
    if isinstance(expression, Xor):
        left = _emit(expression.left, encoder, literal_of, level + 1)
        right = _emit(expression.right, encoder, literal_of, level + 1)
        return encoder.xor_literal(left, right)
    if isinstance(expression, And):
        left = _emit(expression.left, encoder, literal_of, level + 1)
        right = _emit(expression.right, encoder, literal_of, level + 1)
        out = encoder.new()
        encoder.add(-out, left)
        encoder.add(-out, right)
        encoder.add(out, -left, -right)
        return out
    if isinstance(expression, Eq):
        left = _emit(expression.left, encoder, literal_of, level + 1)
        right = _emit(expression.right, encoder, literal_of, level + 1)
        out = encoder.new()
        # out <-> (left == right)
        encoder.add(-out, -left, right)
        encoder.add(-out, left, -right)
        encoder.add(out, left, right)
        encoder.add(out, -left, -right)
        return out
    raise ExprError(f"{type(expression).__name__} is outside the closed grammar")
