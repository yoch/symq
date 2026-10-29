"""Thin, explicitly typed proof interface for the research verifiers.

**Research adapter, not a production API.** Nothing here changes `symq.verification`, `symq.circuit`
or any default backend. The point is to make the *theorem class* part of the type, so a caller cannot
silently upgrade a restricted result into a stronger claim.

## The classes do not form a strength hierarchy

An earlier draft of this file gave the classes a numeric ``rank`` and an ``at_least`` comparison. That
was wrong, and the reason is worth writing down: the classes are **different questions**, not rungs on
a ladder.

* ``FULL_QUANTUM_CHANNEL`` and ``CLASSICAL_OUTPUT_INSTRUMENT`` are **incomparable**. The channel is the
  outcome-averaged object; an instrument is a family of conditioned states. Equal unconditional
  channels can have different observed instruments (§`same_channel` vs `same_instrument` in #90).
* ``FULL_CLASSICAL`` does **not** imply ``FULL_QUANTUM_CHANNEL`` for arbitrary grammars: matching truth
  tables says nothing about coherence, and an HMR programme can match on every basis input while
  dephasing a superposition.
* ``RESTRICTED_HMR_BRANCH`` is about a conditioned unitary family on a restricted fragment. It is not
  comparable with ``FULL_QUANTUM_CHANNEL`` either: the former keeps the outcomes symbolic, the latter
  sums over them.

What *does* hold is a small set of **one-directional forgetful maps**, and only for an
``EQUIVALENT`` verdict. ``DIFFERENT`` does not survive them:

* :func:`forget_instrument` discards every observed classical record of an ``EQUIVALENT`` instrument
  and yields the unconditional channel. A differing instrument does **not** yield a differing channel:
  overwriting a slot can change the record while leaving the CPTP map unchanged.
* :func:`restate` along :data:`IMPLICATIONS` sends an ``EQUIVALENT`` full channel to the traced
  channel. A ``DIFFERENT`` full channel does **not** yield a ``DIFFERENT`` traced channel: ``X`` on a
  clean ancilla is visible in the full state and invisible after the partial trace.

So the API offers :func:`implies` for the edges that are actually sound, and refuses everything else
rather than guessing a total order.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from symq.circuit import UnsupportedOperation
from symq.resources import ResourceLimitExceeded


class TheoremClass(Enum):
    """The kind of statement a verdict supports. Deliberately **not** totally ordered."""

    FULL_CLASSICAL = "full_classical"
    RESTRICTED_HMR_BRANCH = "restricted_hmr_branch"
    FULL_QUANTUM_CHANNEL = "full_quantum_channel"
    TRACED_CHANNEL = "traced_channel"
    CLASSICAL_OUTPUT_INSTRUMENT = "classical_output_instrument"


IMPLICATIONS: frozenset[tuple[TheoremClass, TheoremClass]] = frozenset(
    {
        # A full-state channel equality survives tracing the ancillas out on both sides. The converse
        # (traced ⇒ full) does NOT hold, which is why this is a one-way edge and not a ranking.
        (TheoremClass.FULL_QUANTUM_CHANNEL, TheoremClass.TRACED_CHANNEL),
    }
)
"""Sound one-directional implications between classes. Nothing else is implied."""


def implies(stronger: TheoremClass, weaker: TheoremClass) -> bool:
    """Whether a result of class ``stronger`` establishes class ``weaker``.

    Only the recorded edges count. ``implies(a, a)`` is true because a result establishes itself.
    """
    return stronger is weaker or (stronger, weaker) in IMPLICATIONS


def forget_instrument(result: ProofResult) -> ProofResult:
    """Discard every observed classical record of an equivalent instrument.

    Summing an ``EQUIVALENT`` instrument over all outcomes gives the unconditional channel.
    This function does **not** perform that sum: it only admits a relabeling of a result the
    caller has already proved. The converse is false, and so is the same map on ``DIFFERENT``:
    two programmes can disagree on the observed record and still implement the same CPTP map
    (a later ``store`` can overwrite the slot). ``INCONCLUSIVE``, ``UNSUPPORTED`` and
    ``INTERNAL_ERROR`` are not decisions and are refused rather than rewritten.
    """
    if result.theorem is not TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT:
        raise ValueError("forget_instrument applies only to an instrument result")
    if result.verdict is not Verdict.EQUIVALENT:
        raise ValueError(
            f"cannot forget records of verdict {result.verdict.value!r}: "
            "only EQUIVALENT is preserved, and a differing record does not establish "
            "a differing channel"
        )
    return ProofResult(
        verdict=Verdict.EQUIVALENT,
        theorem=TheoremClass.FULL_QUANTUM_CHANNEL,
        detail=f"{result.detail} (instrument records forgotten)".strip(),
        checked_pairs=result.checked_pairs,
        source_sha256=result.source_sha256,
    )


class Verdict(Enum):
    """Outcome of one proof attempt.

    ``INCONCLUSIVE``, ``UNSUPPORTED`` and ``INTERNAL_ERROR`` are first-class and must never be folded
    into ``DIFFERENT``: an exhausted budget, a rejected input and a crashed verifier carry no
    mathematical content about the programmes.
    """

    EQUIVALENT = "equivalent"
    DIFFERENT = "different"
    INCONCLUSIVE = "inconclusive"
    UNSUPPORTED = "unsupported"
    INTERNAL_ERROR = "internal_error"

    @property
    def decided(self) -> bool:
        """Whether the run reached a mathematical conclusion about the programmes."""
        return self in (Verdict.EQUIVALENT, Verdict.DIFFERENT)

    @property
    def is_failure_to_decide(self) -> bool:
        """Whether the run ended without concluding -- never to be read as ``DIFFERENT``."""
        return self in (Verdict.INCONCLUSIVE, Verdict.UNSUPPORTED, Verdict.INTERNAL_ERROR)


@dataclass(frozen=True)
class AncillaContract:
    """What the proof assumes about wires that are not inputs.

    ``clean`` means every ancilla starts in ``|0>``. ``arbitrary`` (``clean=False``) is the stronger
    requirement: a proof that holds for arbitrary ancillas holds for clean ones, but not conversely.
    """

    clean: bool
    traced: bool = False
    """When true the ancillas are traced out of the comparison (a ``TRACED_CHANNEL`` claim)."""

    def validate(self, class_: TheoremClass) -> None:
        if class_ is TheoremClass.TRACED_CHANNEL and not self.traced:
            raise ValueError("TRACED_CHANNEL requires the ancillas to be traced")
        if class_ is TheoremClass.FULL_QUANTUM_CHANNEL and self.traced:
            raise ValueError("FULL_QUANTUM_CHANNEL must retain the ancillas, not trace them")


@dataclass(frozen=True)
class Domain:
    """An explicit, nonempty set of admitted inputs, plus what it does *not* claim.

    A list of classical basis inputs is **not** a coherent-subspace theorem. For any restricted domain
    the caller must state whether coherences inside the span were checked; otherwise the result is only
    about those basis vectors, and ``coherent_span`` must stay ``False``.
    """

    points: tuple[int, ...]
    coherent_span: bool
    """True only when every ``|x><y|`` with x, y in the span of ``points`` was compared."""

    def validate(self) -> None:
        if not self.points:
            raise ValueError("an empty domain makes every implication vacuous")
        if len(set(self.points)) != len(self.points):
            raise ValueError("domain points must be distinct")
        if any(type(p) is not int or p < 0 for p in self.points):
            raise ValueError("domain points must be nonnegative integers")


@dataclass(frozen=True)
class ProofRequest:
    """Everything a verifier needs, with the theorem class stated up front.

    ``programs`` are opaque labels. This module imports exception types used by
    :func:`classify_exception`, and no concrete checker.
    """

    class_: TheoremClass
    programs: tuple[str, ...]
    """Opaque labels; the concrete verifier resolves them. Two labels, or one for a self-check."""
    ancillas: AncillaContract
    domain: Domain | None = None
    observed_slots: tuple[str, ...] = ()
    max_seconds: float | None = None
    max_events: int | None = None
    max_width: int | None = None

    def validate(self) -> None:
        if len(self.programs) not in (1, 2):
            raise ValueError("a proof request names one or two programs")
        self.ancillas.validate(self.class_)
        if self.domain is not None:
            self.domain.validate()
        if self.class_ is TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT and not self.observed_slots:
            raise ValueError("an instrument claim must name the observed classical slots")
        if self.class_ is not TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT and self.observed_slots:
            raise ValueError("observed slots are only meaningful for an instrument claim")
        for name, value in (
            ("max_seconds", self.max_seconds),
            ("max_events", self.max_events),
            ("max_width", self.max_width),
        ):
            if value is not None and not value > 0:
                raise ValueError(f"{name} must be positive when given")


@dataclass(frozen=True)
class ProofResult:
    """A verdict plus the exact evidence that supports it.

    ``theorem`` records what was *actually* established, which may be weaker than the request: a
    verifier that can only decide the classical permutation says so, and the caller sees it in the
    type rather than inferring it from prose.
    """

    verdict: Verdict
    theorem: TheoremClass
    detail: str = ""
    witness: tuple[int, ...] | None = None
    checked_pairs: int | None = None
    source_sha256: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.verdict is Verdict.EQUIVALENT and self.witness is not None:
            raise ValueError("an equivalent verdict cannot carry a counterexample witness")
        if self.verdict is Verdict.DIFFERENT and self.witness is None:
            raise ValueError("a different verdict must carry a witness")
        if self.verdict in (Verdict.UNSUPPORTED, Verdict.INTERNAL_ERROR) and self.checked_pairs:
            raise ValueError("a non-decision cannot claim to have checked pairs")

    @property
    def proved(self) -> bool:
        return self.verdict is Verdict.EQUIVALENT


def restate(result: ProofResult, *, as_: TheoremClass, reason: str) -> ProofResult:
    """Re-label an ``EQUIVALENT`` result as a class that it *actually implies*.

    A full-channel equality may be reported as a traced-channel equality. This function does
    **not** compute the partial trace; it only admits the relabeling. The same edge does not
    carry ``DIFFERENT``: partial trace is forgetful, so a difference can disappear. Sideways moves
    (channel to instrument, classical to quantum) are refused because :func:`implies` has no such
    edge. Non-decisions are refused too: they are not mathematical statements about the programmes.
    """
    if result.verdict is not Verdict.EQUIVALENT:
        raise ValueError(
            f"cannot restate verdict {result.verdict.value!r}: "
            "only EQUIVALENT is preserved under forgetful maps"
        )
    if not implies(result.theorem, as_):
        raise ValueError(
            f"{result.theorem.value!r} does not establish {as_.value!r}; "
            "the theorem classes are not a strength ladder"
        )
    return ProofResult(
        verdict=result.verdict,
        theorem=as_,
        detail=f"{result.detail} (restated from {result.theorem.value}: {reason})",
        witness=result.witness,
        checked_pairs=result.checked_pairs,
        source_sha256=result.source_sha256,
    )


def classify_exception(exc: BaseException) -> Verdict:
    """Map a verifier exception onto a non-decisive verdict -- **never** ``DIFFERENT``.

    ``ResourceLimitExceeded``, timeouts and memory exhaustion mean the run did not decide anything.
    A gate or construct outside the accepted grammar is ``UNSUPPORTED``.

    Anything else is ``INTERNAL_ERROR``, deliberately distinct from ``INCONCLUSIVE``: an unexpected
    crash is a defect in the verifier, not a statement that the budget ran out, and collapsing the two
    would hide bugs behind a category that looks benign.
    """
    if isinstance(exc, UnsupportedOperation):
        return Verdict.UNSUPPORTED
    if isinstance(exc, (ResourceLimitExceeded, TimeoutError, MemoryError)):
        return Verdict.INCONCLUSIVE
    return Verdict.INTERNAL_ERROR
