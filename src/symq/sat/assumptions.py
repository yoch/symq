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
two names ``u.3`` and ``v.3`` refer to the same wire of the two candidates. That naming is what
makes a *relational* interface expressible at all -- blind wire-by-wire equality cannot say
``v = u XOR mask``.

Closure is enforced at **every node**, not only at the root. ``And(Var("x.0"), object())`` raises
:class:`ExprError` when it is built, rather than reaching :func:`depth` and failing with
``AttributeError``. :func:`validate` re-walks the tree anyway, because a tree can also be built by
unpickling or by bypassing ``__post_init__``, and because the depth bound has to be checked during
a bounded traversal rather than after an unbounded one.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

MAX_DEPTH = 24
"""Depth bound: an assumption is a small formula, not a program. Checked, not documented only."""


class ExprError(ValueError):
    """The expression is outside the closed grammar, or malformed."""


def _require_expr(value: object, where: str) -> None:
    """Reject anything that is not one of the five node types."""
    if not isinstance(value, (Const, Var, Not, Xor, And, Eq)):
        raise ExprError(f"{where} must be a grammar node, not {type(value).__name__}")


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

    def __post_init__(self) -> None:
        _require_expr(self.operand, "Not.operand")


@dataclass(frozen=True)
class Xor:
    left: Expr
    right: Expr

    def __post_init__(self) -> None:
        _require_expr(self.left, "Xor.left")
        _require_expr(self.right, "Xor.right")


@dataclass(frozen=True)
class And:
    left: Expr
    right: Expr

    def __post_init__(self) -> None:
        _require_expr(self.left, "And.left")
        _require_expr(self.right, "And.right")


@dataclass(frozen=True)
class Eq:
    left: Expr
    right: Expr

    def __post_init__(self) -> None:
        _require_expr(self.left, "Eq.left")
        _require_expr(self.right, "Eq.right")


Expr = Const | Var | Not | Xor | And | Eq


def _walk(expression: object, level: int, used: set[str]) -> None:
    """Bounded structural walk: type-check every node and collect variable names.

    The depth bound is enforced *during* the walk, so an over-deep tree raises instead of driving
    the Python stack to its limit. ``level`` counts nodes on the path, the root being 1, matching
    :func:`depth`'s convention.
    """
    if level > MAX_DEPTH:
        raise ExprError(f"expression depth exceeds the bound {MAX_DEPTH}")
    _require_expr(expression, f"depth {level}")
    if isinstance(expression, Const):
        if not isinstance(expression.value, bool):
            raise ExprError(f"Const holds {type(expression.value).__name__}, not bool")
        return
    if isinstance(expression, Var):
        if not isinstance(expression.name, str) or not expression.name:
            raise ExprError("Var holds a non-string or empty name")
        used.add(expression.name)
        return
    if isinstance(expression, Not):
        _walk(expression.operand, level + 1, used)
        return
    # Xor, And, Eq: binary nodes. ``isinstance`` narrowed by _require_expr above.
    if isinstance(expression, (Xor, And, Eq)):
        _walk(expression.left, level + 1, used)
        _walk(expression.right, level + 1, used)
        return
    raise ExprError(
        f"{type(expression).__name__} is outside the closed grammar"
    )  # pragma: no cover


def depth(expression: Expr) -> int:
    """Longest root-to-leaf node count, validated first so the walk cannot hit a non-node."""
    used: set[str] = set()
    _walk(expression, 1, used)
    return _depth_unchecked(expression)


def _depth_unchecked(expression: Expr) -> int:
    if isinstance(expression, (Const, Var)):
        return 1
    if isinstance(expression, Not):
        return 1 + _depth_unchecked(expression.operand)
    return 1 + max(_depth_unchecked(expression.left), _depth_unchecked(expression.right))


def variables(expression: Expr) -> frozenset[str]:
    """Every variable mentioned, validated on the way so a malformed node cannot be skipped."""
    used: set[str] = set()
    _walk(expression, 1, used)
    return frozenset(used)


def validate(expression: Expr, declared: frozenset[str] | set[str]) -> None:
    """Check the grammar, the depth bound and that every variable is declared.

    Called by every entry point: an assumption that mentions an undeclared variable could be
    silently dropped by an encoder, which is exactly the kind of vacuous certificate the issue
    forbids. Sub-expressions are checked recursively, so an unknown node type anywhere in the tree
    raises :class:`ExprError` here rather than surfacing as an ``AttributeError`` later.
    """
    used: set[str] = set()
    _walk(expression, 1, used)
    if not isinstance(declared, (set, frozenset)):
        raise ExprError("declared variables must be a set or frozenset")
    unknown = used - set(declared)
    if unknown:
        raise ExprError(f"undeclared variables: {sorted(unknown)}")


def evaluate(expression: Expr, assignment: Mapping[str, int]) -> bool:
    """Concrete semantics of the IR, independent of any CNF encoding.

    This is the oracle a witness is replayed against: a SAT model is only reported as a certified
    counterexample once these functions agree with it. Raises :class:`ExprError` for a name that the
    assignment does not bind, so a caller cannot silently treat a missing wire as zero.
    """
    used: set[str] = set()
    _walk(expression, 1, used)
    for name in used:
        if name not in assignment:
            raise ExprError(f"assignment does not bind {name!r}")
    return _evaluate_unchecked(expression, assignment)


def _evaluate_unchecked(expression: Expr, assignment: Mapping[str, int]) -> bool:
    if isinstance(expression, Const):
        return expression.value
    if isinstance(expression, Var):
        return bool(assignment[expression.name])
    if isinstance(expression, Not):
        return not _evaluate_unchecked(expression.operand, assignment)
    left = _evaluate_unchecked(expression.left, assignment)
    right = _evaluate_unchecked(expression.right, assignment)
    if isinstance(expression, Xor):
        return left != right
    if isinstance(expression, And):
        return left and right
    return left == right


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
    _require_expr(expression, "expression")
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
    raise ExprError(
        f"{type(expression).__name__} is outside the closed grammar"
    )  # pragma: no cover
