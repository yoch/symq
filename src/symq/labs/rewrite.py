"""Shared pieces of the contextual-rewrite research APIs (no API promise).

The classical (:mod:`symq.labs.contextual_substitution`) and coherent
(:mod:`symq.labs.hybrid_substitution`) checkers prove different theorems but share the same
bookkeeping, kept here once:

* a declared integer cost proxy keyed by gate *name and arity* (:class:`Weights`), so a
  three-wire ``mcx`` is weighted as a ``ccx``;
* :class:`CostReport`, the exact before/after counts under those weights;
* :func:`call_budget`, which starts the whole-call deadline once, on entry;
* the outcome vocabulary and the :class:`VerdictFields` mixin that makes every result satisfy
  :class:`symq.facade.Verdict`;
* a proof seal: an ``equivalent`` result, and any applicable candidate it carries, can only be
  built by the checker in the call that proved it (the private :func:`_proved`), and the seal
  pins every compared field of that result, so ``dataclasses.replace`` cannot turn a negative
  result into a positive one or reuse a proof for another rewrite;
* :class:`ReceiptMismatch`, :func:`compare_pins` and :func:`check_receipt` for replay.

Trust boundary. Through the public API, a result is ``equivalent`` and carries a candidate only
if a checker proved it in this process, on a frozen snapshot of its inputs; stored reports
authorize nothing until they are replayed. This is not cryptography: code running in the same
process can import private names or call ``object.__setattr__`` and forge anything. SymQ does
not defend against hostile code in its own interpreter.

The proxy weights are caller-declared units. They are not a T-count, a depth, a hardware cost
or any competition score, and they never change a proof decision.
"""
from __future__ import annotations

import weakref
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import MISSING, dataclass, fields
from typing import Any

from symq.errors import SymqError
from symq.resources import Budget, Guard

__all__ = [
    "DECISIVE",
    "OUTCOMES",
    "WEIGHTABLE",
    "CostReport",
    "ReceiptMismatch",
    "VerdictFields",
    "Weights",
    "call_budget",
    "check_receipt",
    "check_span",
    "compare_pins",
    "cost_report",
    "gate_key",
    "refused_by_cost",
    "withhold_without_saving",
]

OUTCOMES = frozenset({"equivalent", "not_proved", "precondition_failed", "inconclusive",
                      "unsupported"})
"""``not_proved``: a sufficient local obligation failed. A local counterexample need not be
reachable from the global input, so it is never reported as ``different``."""
DECISIVE = frozenset({"equivalent", "not_proved", "precondition_failed"})
"""Outcomes a replay reproduces exactly. ``inconclusive`` and ``unsupported`` depend on the
budget or the installation, so a replay that ends there reverifies nothing."""

_ARITY_NAMES = {"mcx": {1: "x", 2: "cx", 3: "ccx"}, "mcz": {1: "z", 2: "cz", 3: "ccz"}}
WEIGHTABLE = frozenset({
    "x", "cx", "ccx", "mcx", "swap", "cswap", "z", "cz", "ccz", "mcz", "neg",
    "hmr", "measure_z", "reset", "store", "invert", "oxor",
})
"""Operation names a :class:`Weights` model may price."""


class ReceiptMismatch(SymqError, ValueError):
    """A receipt does not describe the supplied source, replacement, contract or costs."""


def gate_key(kind: str, arity: int) -> str:
    """The priced name of an operation: ``mcx``/``mcz`` are named by their wire count."""
    return _ARITY_NAMES.get(kind, {}).get(arity, kind)


@dataclass(frozen=True)
class Weights:
    """Declared integer price per operation name; unlisted names cost ``default``."""

    by_kind: tuple[tuple[str, int], ...] = ()
    unit: str = "declared_units"
    default: int = 1

    def __post_init__(self) -> None:
        if type(self.unit) is not str or not self.unit.strip():
            raise ValueError("a nonempty unit label is required")
        if type(self.default) is not int or self.default < 0:
            raise ValueError("the default weight must be a nonnegative integer")
        if type(self.by_kind) is not tuple:
            raise TypeError("by_kind must be an immutable tuple of (name, weight) pairs")
        seen: set[str] = set()
        for pair in self.by_kind:
            if (type(pair) is not tuple or len(pair) != 2 or pair[0] not in WEIGHTABLE
                    or type(pair[1]) is not int or pair[1] < 0):
                raise ValueError("weights must be (operation name, nonnegative int) pairs; "
                                 f"names are {sorted(WEIGHTABLE)}")
            if pair[0] in seen:
                raise ValueError(f"duplicate weight for operation {pair[0]!r}")
            seen.add(pair[0])

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, int], *, unit: str = "declared_units",
                     default: int = 1) -> Weights:
        return cls(tuple(sorted(mapping.items())), unit, default)

    def weight(self, key: str) -> int:
        return dict(self.by_kind).get(key, self.default)

    def to_dict(self) -> dict[str, Any]:
        return {"by_kind": [list(pair) for pair in self.by_kind], "unit": self.unit,
                "default": self.default}


@dataclass(frozen=True)
class CostReport:
    """Exact operation counts and declared weighted totals, before and after."""

    reference_counts: tuple[tuple[str, int], ...]
    candidate_counts: tuple[tuple[str, int], ...]
    reference_weighted: int
    candidate_weighted: int
    weights: Weights

    @property
    def reference_ops(self) -> int:
        return sum(count for _, count in self.reference_counts)

    @property
    def candidate_ops(self) -> int:
        return sum(count for _, count in self.candidate_counts)

    @property
    def weighted_delta(self) -> int:
        return self.candidate_weighted - self.reference_weighted

    def to_dict(self) -> dict[str, Any]:
        return {"reference_counts": [list(p) for p in self.reference_counts],
                "candidate_counts": [list(p) for p in self.candidate_counts],
                "reference_ops": self.reference_ops, "candidate_ops": self.candidate_ops,
                "reference_weighted": self.reference_weighted,
                "candidate_weighted": self.candidate_weighted,
                "weighted_delta": self.weighted_delta, "weights": self.weights.to_dict()}


def cost_report(reference: Iterable[str], candidate: Iterable[str], weights: Weights) -> CostReport:
    """Price two streams of operation keys (see :func:`gate_key`)."""
    if type(weights) is not Weights:
        raise TypeError("weights must be Weights")
    before, after = Counter(reference), Counter(candidate)
    return CostReport(tuple(sorted(before.items())), tuple(sorted(after.items())),
                      sum(weights.weight(k) * n for k, n in before.items()),
                      sum(weights.weight(k) * n for k, n in after.items()), weights)


def call_budget(budget: Budget | None, *, default_seconds: float = 30.0) -> Budget:
    """The whole-call budget: one absolute deadline started now, never restarted later."""
    if budget is not None and not isinstance(budget, Budget):
        raise TypeError("budget must be Budget or None")
    guard = Guard(budget if budget is not None else Budget(max_seconds=default_seconds))
    # Not ``inherited_budget()``: that checks the clock now, and an already exhausted budget
    # must surface as an ``inconclusive`` result from the checker, not as an exception here.
    return Budget(guard.budget.max_terms, guard.budget.max_nodes,
                  absolute_deadline=guard.deadline, max_bytes=guard.budget.max_bytes)


def check_span(span: Any, length: int) -> tuple[int, int]:
    if (type(span) is not tuple or len(span) != 2 or any(type(v) is not int for v in span)
            or not 0 <= span[0] <= span[1] <= length):
        raise ValueError("span must be a valid [start, stop) operation interval")
    return span


class _Proof:
    """Private seal of one proved result. It carries nothing: the pinned field values live in
    the module-private registry :data:`_ISSUED`, filled only by :func:`_proved`, so a fresh
    ``_Proof()`` (for example ``type(result._token)()``) is not a seal."""

    __slots__ = ("__weakref__",)

    def __copy__(self) -> _Proof:
        return self

    def __deepcopy__(self, memo: dict) -> _Proof:
        return self


_ISSUED: weakref.WeakKeyDictionary[_Proof, tuple[tuple[str, Any], ...]] = \
    weakref.WeakKeyDictionary()


def _pin_values(result: Any) -> tuple[tuple[str, Any], ...]:
    return tuple((f.name, getattr(result, f.name)) for f in fields(result) if f.compare)


def _proved(cls: type, candidate: Any, **values: Any) -> Any:
    """An ``equivalent`` result sealed at construction. Only the checkers call this, in the call
    that ran the proof; it is private on purpose (see the trust boundary above)."""
    values = {**values, "outcome": "equivalent"}
    pins = []
    for f in fields(cls):
        if not f.compare:
            continue
        if f.name in values:
            pins.append((f.name, values[f.name]))
        elif f.default is not MISSING:
            pins.append((f.name, f.default))
        else:
            raise TypeError(f"{cls.__name__}: missing field {f.name}")
    seal = _Proof()
    _ISSUED[seal] = tuple(pins)
    return cls(**values, candidate=candidate, _token=seal)


def refused_by_cost(result: Any, require_saving: bool) -> bool:
    """True for a proved result that ``require_saving`` refuses: no strict weighted saving."""
    return result.candidate is not None and require_saving and result.cost.weighted_delta >= 0


def withhold_without_saving(result: Any, require_saving: bool) -> Any:
    """``result`` without its candidate when :func:`refused_by_cost`; the proof is kept."""
    if not refused_by_cost(result, require_saving):
        return result
    values = {f.name: getattr(result, f.name) for f in fields(result)
              if f.init and f.name not in ("outcome", "candidate", "_token")}
    values["reason"] = result.reason + "; not applied: no saving under the declared weights"
    return _proved(type(result), None, **values)


class VerdictFields:
    """Read-only :class:`symq.facade.Verdict` fields shared by the rewrite results.

    Subclasses are frozen dataclasses with ``outcome``, ``candidate`` (``None`` unless proved
    in the same call) and ``_token`` fields, and define :meth:`_candidate_digest`.
    """

    outcome: str
    candidate: Any
    _token: Any
    candidate_sha256: str

    def _candidate_digest(self, candidate: Any) -> str:
        raise NotImplementedError

    def _check_fields(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"unknown rewrite outcome {self.outcome!r}")
        token = self._token
        if token is not None:
            if type(token) is not _Proof or self.outcome != "equivalent":
                raise ValueError("a proof seal belongs only to a result its checker proved")
            if _ISSUED.get(token) != _pin_values(self):
                raise ValueError("this is not the result the checker proved")
        elif self.outcome == "equivalent":
            raise ValueError("an equivalent outcome is only issued by the checker that proved it")
        if self.candidate is not None and (
                self.outcome != "equivalent"
                or self._candidate_digest(self.candidate) != self.candidate_sha256):
            raise ValueError("only the proved stream can be attached, by the checker that proved it")

    @property
    def equivalent(self) -> bool:
        return self.outcome == "equivalent"

    @property
    def certified(self) -> bool:
        """A decisive exact computation in this process, not a portable certificate."""
        return self.equivalent

    @property
    def different(self) -> bool:
        # Local failures are not global counterexamples.
        return False

    @property
    def witness(self) -> None:
        return None

    @property
    def witness_kind(self) -> None:
        return None


def check_receipt(receipt: Any, fresh: Any, input_pins: Iterable[str]) -> None:
    """Bind a typed receipt to a fresh result of the same checker.

    The inputs named by ``input_pins`` must always agree. When the fresh outcome is decisive, the
    receipt must also equal the fresh result on every compared field: a stored negative result
    cannot hide behind a fresh positive proof, nor the reverse.
    """
    compare_pins(receipt, fresh, input_pins)
    if fresh.outcome in DECISIVE:
        differing = [f.name for f in fields(fresh)
                     if f.compare and getattr(receipt, f.name) != getattr(fresh, f.name)]
        if differing:
            raise ReceiptMismatch("the receipt contradicts the recomputed result: "
                                  + ", ".join(differing))


def compare_pins(receipt: Any, fresh: Any, names: Iterable[str]) -> None:
    """Raise :class:`ReceiptMismatch` unless ``receipt`` and ``fresh`` agree on ``names``."""
    differing = [name for name in names if getattr(receipt, name) != getattr(fresh, name)]
    if differing:
        raise ReceiptMismatch("the receipt does not describe the supplied inputs: "
                              + ", ".join(differing))
