"""Typed proof certificates with an explicit, immutable physical frame.

**Research adapter, not a production API.** Nothing here changes `symq.verification`, `symq.circuit`
or any default backend.

## Why a verdict and a theorem label are not enough

A first version of this module stored only ``(verdict, theorem)``. That is unsound: the same pair
``EQUIVALENT / CLASSICAL_OUTPUT_INSTRUMENT`` describes two different physical statements depending
on whether the ancillas were retained or traced out. Concretely, with one data bit and one clean
ancilla:

    L = store(b0, 0)
    R = x(ancilla); store(b0, 0)

The observed instruments agree **after the partial trace** and differ **with the ancilla kept**;
the quantum channels behave the same way. Relabelling the first fact as
``EQUIVALENT(FULL_QUANTUM_CHANNEL)`` is a false theorem about a frame nobody proved.

So a :class:`ProofResult` now carries the :class:`PhysicalFrame` it was obtained under: the two
programs and their digests, the coherent input domain, the ancilla preparation, which quantum
outputs were retained and which were traced, and which classical slots were observed. Conversions
consume that frame and produce a *narrower* one; they never invent one.

## The classes are not a strength ladder

``FULL_QUANTUM_CHANNEL`` and ``CLASSICAL_OUTPUT_INSTRUMENT`` are incomparable questions: the channel
is outcome-averaged, an instrument is a family of conditioned maps. ``FULL_CLASSICAL`` does not
imply ``FULL_QUANTUM_CHANNEL``: matching truth tables say nothing about coherence. ``RESTRICTED_HMR_BRANCH``
keeps outcomes symbolic and is not comparable either. Only one edge is recorded, in
:data:`IMPLICATIONS`.

## Two architectures, and the one chosen

The mission allowed (A) a certificate transformation with a proof that the implication is valid
under the retained contract, or (B) recomputation through a channel oracle. This module implements
**A**, because it is the smaller honest thing:

* :func:`restate` states "equal full states have equal partial traces" and rewrites the frame's
  output partition accordingly. It performs no linear algebra.
* :func:`forget_instrument` states "if every conditioned map agrees, their sum agrees" and clears
  the observed slots. It performs no Kraus sum.

Neither function may be read as having *computed* a trace or a sum. A caller that wants the sum
checked must run the oracle (``research.hybrid_channel.oracle``) or the independent kit in PR #101.
Both functions refuse every verdict except ``EQUIVALENT``, and both refuse to widen the frame.

## What is refused, and why

* ``DIFFERENT(FULL_QUANTUM_CHANNEL)`` does **not** give ``DIFFERENT(TRACED_CHANNEL)``: ``X`` on a
  clean ancilla is visible in the full state and invisible after the trace.
* ``DIFFERENT(CLASSICAL_OUTPUT_INSTRUMENT)`` does **not** give a differing channel: overwriting a
  slot changes the record and leaves the CPTP map intact.
* ``INCONCLUSIVE``, ``UNSUPPORTED`` and ``INTERNAL_ERROR`` are not mathematical statements and are
  never carried across any conversion.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from enum import Enum

from symq.circuit import UnsupportedOperation
from symq.resources import ResourceLimitExceeded

_DIGEST = re.compile(r"[0-9a-f]{64}\Z")


class TheoremClass(Enum):
    """The kind of statement a verdict supports. Deliberately **not** totally ordered."""

    FULL_CLASSICAL = "full_classical"
    RESTRICTED_HMR_BRANCH = "restricted_hmr_branch"
    FULL_QUANTUM_CHANNEL = "full_quantum_channel"
    TRACED_CHANNEL = "traced_channel"
    CLASSICAL_OUTPUT_INSTRUMENT = "classical_output_instrument"


IMPLICATIONS: frozenset[tuple[TheoremClass, TheoremClass]] = frozenset(
    {
        # A full-state channel equality survives tracing the ancillas out on both sides. The
        # converse (traced => full) does NOT hold, which is why this is a one-way edge.
        (TheoremClass.FULL_QUANTUM_CHANNEL, TheoremClass.TRACED_CHANNEL),
    }
)
"""Sound one-directional implications between classes. Nothing else is implied."""


def implies(stronger: TheoremClass, weaker: TheoremClass) -> bool:
    """Whether a result of class ``stronger`` establishes class ``weaker``.

    Only the recorded edges count. ``implies(a, a)`` is true because a result establishes itself.
    """
    return stronger is weaker or (stronger, weaker) in IMPLICATIONS


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

    A list of classical basis inputs is **not** a coherent-subspace theorem. For any restricted
    domain the caller must state whether coherences inside the span were checked; otherwise the
    result is only about those basis vectors, and ``coherent_span`` must stay ``False``.
    """

    points: tuple[int, ...]
    coherent_span: bool
    """True only when every ``|x><y|`` with x, y in the span of ``points`` was compared."""

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not self.points:
            raise ValueError("an empty domain makes every implication vacuous")
        if len(set(self.points)) != len(self.points):
            raise ValueError("domain points must be distinct")
        if any(type(point) is not int or point < 0 for point in self.points):
            raise ValueError("domain points must be nonnegative integers")
        if type(self.coherent_span) is not bool:
            raise ValueError("coherent_span must be an explicit bool")

    def matches(self, other: Domain) -> bool:
        return self.points == other.points and self.coherent_span is other.coherent_span


def _check_wire_labels(name: str, labels: tuple[str, ...]) -> None:
    if type(labels) is not tuple:
        raise ValueError(f"{name} must be a tuple")
    if any(type(label) is not str or not label for label in labels):
        raise ValueError(f"{name} entries must be nonempty strings")
    if len(set(labels)) != len(labels):
        raise ValueError(f"{name} entries must be distinct")


@dataclass(frozen=True)
class PhysicalFrame:
    """Exactly what a verdict is about. Immutable, comparable, and never widened by a conversion.

    ``retained_outputs`` and ``traced_outputs`` partition the quantum outputs. ``ancilla_outputs``
    names which of the retained outputs are ancillas, so a trace can move exactly those and leave the
    data outputs compared. ``observed_slots`` are the classical slots whose records were kept. Two
    frames are the same contract only when all eight fields agree; :func:`certifies` uses that.
    """

    programs: tuple[str, ...]
    program_sha256: tuple[str, ...]
    domain: Domain
    ancillas: AncillaContract
    retained_outputs: tuple[str, ...] = ()
    traced_outputs: tuple[str, ...] = ()
    ancilla_outputs: tuple[str, ...] = ()
    """The retained outputs that are ancillas: the only ones a trace may move."""

    observed_slots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if len(self.programs) not in (1, 2):
            raise ValueError("a physical frame names one or two programs")
        if len(self.program_sha256) != len(self.programs):
            raise ValueError("every program needs exactly one digest")
        if any(
            type(digest) is not str or _DIGEST.fullmatch(digest) is None
            for digest in self.program_sha256
        ):
            raise ValueError("program digests must be 64 lowercase hex characters")
        self.domain.validate()
        if type(self.ancillas) is not AncillaContract:
            raise ValueError("an explicit ancilla contract is required")
        _check_wire_labels("retained_outputs", self.retained_outputs)
        _check_wire_labels("traced_outputs", self.traced_outputs)
        _check_wire_labels("ancilla_outputs", self.ancilla_outputs)
        _check_wire_labels("observed_slots", self.observed_slots)
        overlap = set(self.retained_outputs) & set(self.traced_outputs)
        if overlap:
            raise ValueError(f"outputs cannot be both retained and traced: {sorted(overlap)}")
        stray = set(self.ancilla_outputs) - set(self.retained_outputs)
        if stray:
            raise ValueError(
                f"ancilla outputs must be retained while they are retained: {sorted(stray)}"
            )
        if self.ancillas.traced and not self.traced_outputs:
            raise ValueError(
                "the ancilla contract says the ancillas are traced, but no output was traced"
            )
        if not self.ancillas.traced and self.traced_outputs:
            raise ValueError(
                "the ancilla contract keeps the ancillas, but outputs were traced"
            )

    def check_class(self, class_: TheoremClass) -> None:
        """Refuse a theorem class the frame cannot support."""
        self.validate()
        self.ancillas.validate(class_)
        if class_ is TheoremClass.FULL_QUANTUM_CHANNEL:
            if self.observed_slots:
                raise ValueError(
                    "FULL_QUANTUM_CHANNEL forgets the classical records; "
                    f"observed slots {self.observed_slots} belong to an instrument claim"
                )
            if self.traced_outputs:
                raise ValueError("FULL_QUANTUM_CHANNEL must retain every quantum output")
            if not self.retained_outputs:
                raise ValueError("FULL_QUANTUM_CHANNEL must name the retained quantum outputs")
        elif class_ is TheoremClass.TRACED_CHANNEL:
            if self.observed_slots:
                raise ValueError("TRACED_CHANNEL forgets the classical records as well")
            if not self.retained_outputs:
                raise ValueError("TRACED_CHANNEL still needs the reduced outputs it compares")
        elif class_ is TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT:
            if not self.observed_slots:
                raise ValueError("an instrument claim must name the observed classical slots")
        elif class_ is TheoremClass.FULL_CLASSICAL:
            if self.observed_slots or self.traced_outputs:
                raise ValueError("a classical permutation claim has no records and no trace")
        elif class_ is TheoremClass.RESTRICTED_HMR_BRANCH:
            if self.traced_outputs:
                raise ValueError("a restricted branch claim keeps the measured wire")
        else:  # pragma: no cover - exhaustive over TheoremClass
            raise AssertionError(f"unhandled theorem class {class_!r}")

    def matches(self, other: PhysicalFrame) -> bool:
        """Same contract only when every field agrees. Digests are compared verbatim."""
        return (
            self.programs == other.programs
            and self.program_sha256 == other.program_sha256
            and self.domain.matches(other.domain)
            and self.ancillas == other.ancillas
            and self.retained_outputs == other.retained_outputs
            and self.traced_outputs == other.traced_outputs
            and self.ancilla_outputs == other.ancilla_outputs
            and self.observed_slots == other.observed_slots
        )

    def with_records_forgotten(self) -> PhysicalFrame:
        """Drop the observed classical records; the quantum output partition is untouched."""
        return replace(self, observed_slots=())

    def with_ancillas_traced(self) -> PhysicalFrame:
        """Trace exactly the retained ancilla outputs, keeping every data output compared.

        Refuses when there is no retained ancilla output to move: that would be a no-op dressed as a
        trace, or a request to trace the data itself, and neither is what a channel restatement means.
        """
        if not self.ancilla_outputs:
            raise ValueError(
                "no retained ancilla output to trace; a restatement cannot invent one"
            )
        kept = tuple(w for w in self.retained_outputs if w not in self.ancilla_outputs)
        if not kept:
            raise ValueError("tracing every retained output leaves nothing to compare")
        return replace(
            self,
            retained_outputs=kept,
            traced_outputs=self.traced_outputs + self.ancilla_outputs,
            ancilla_outputs=(),
            ancillas=AncillaContract(clean=self.ancillas.clean, traced=True),
        )


@dataclass(frozen=True)
class ProofRequest:
    """What to prove, under which physical contract, with which budgets."""

    frame: PhysicalFrame
    class_: TheoremClass
    max_seconds: float | None = None
    max_events: int | None = None
    max_width: int | None = None

    def validate(self) -> None:
        self.frame.check_class(self.class_)
        for name, value in (
            ("max_seconds", self.max_seconds),
            ("max_events", self.max_events),
            ("max_width", self.max_width),
        ):
            if value is not None and not value > 0:
                raise ValueError(f"{name} must be positive when given")


@dataclass(frozen=True)
class ProofResult:
    """A verdict, the theorem actually established, and the frame it was established under."""

    verdict: Verdict
    theorem: TheoremClass
    frame: PhysicalFrame
    detail: str = ""
    witness: tuple[int, ...] | None = None
    checked_pairs: int | None = None

    def __post_init__(self) -> None:
        if type(self.verdict) is not Verdict:
            raise ValueError("an explicit Verdict is required")
        if type(self.theorem) is not TheoremClass:
            raise ValueError("an explicit TheoremClass is required")
        if type(self.frame) is not PhysicalFrame:
            raise ValueError("an explicit PhysicalFrame is required")
        self.frame.check_class(self.theorem)
        if self.verdict is Verdict.EQUIVALENT and self.witness is not None:
            raise ValueError("an equivalent verdict cannot carry a counterexample witness")
        if self.verdict is Verdict.DIFFERENT and self.witness is None:
            raise ValueError("a different verdict must carry a witness")
        if self.verdict in (Verdict.UNSUPPORTED, Verdict.INTERNAL_ERROR) and self.checked_pairs:
            raise ValueError("a non-decision cannot claim to have checked pairs")

    @property
    def proved(self) -> bool:
        return self.verdict is Verdict.EQUIVALENT


def certifies(result: ProofResult, request: ProofRequest) -> bool:
    """Whether ``result`` is a certificate for exactly this request.

    Every frame field must agree: program labels, digests, coherent domain, ancilla preparation,
    retained and traced outputs, observed slots. Changing any of them makes the verdict a statement
    about a different experiment.
    """
    return result.frame.matches(request.frame) and result.theorem is request.class_


def require_certificate(result: ProofResult, request: ProofRequest) -> None:
    """:func:`certifies`, raising with the first field that disagrees."""
    if not result.frame.matches(request.frame):
        mine, theirs = result.frame, request.frame
        for name in (
            "programs",
            "program_sha256",
            "domain",
            "ancillas",
            "retained_outputs",
            "traced_outputs",
            "ancilla_outputs",
            "observed_slots",
        ):
            if getattr(mine, name) != getattr(theirs, name):
                raise ValueError(f"certificate does not cover the request: {name} differs")
        raise ValueError("certificate does not cover the request")
    if result.theorem is not request.class_:
        raise ValueError(
            f"certificate proves {result.theorem.value!r}, request asked {request.class_.value!r}"
        )


def _require_equivalent(result: ProofResult, operation: str) -> None:
    if result.verdict is not Verdict.EQUIVALENT:
        raise ValueError(
            f"{operation} refuses verdict {result.verdict.value!r}: only EQUIVALENT is preserved "
            "under a forgetful map, and a difference or a non-decision carries no consequence"
        )


def restate(result: ProofResult, *, as_: TheoremClass, reason: str) -> ProofResult:
    """Report an ``EQUIVALENT`` result at a class it already implies, narrowing the frame.

    This is a **certificate-level** implication. It does not compute a partial trace: it records
    that the claim is now about the reduced outputs, and moves the traced wires into
    ``traced_outputs``. ``DIFFERENT`` cannot travel this edge -- ``X`` on a clean ancilla is the
    counterexample -- and neither can a non-decision.
    """
    _require_equivalent(result, "restate")
    if not implies(result.theorem, as_):
        raise ValueError(
            f"{result.theorem.value!r} does not establish {as_.value!r}; "
            "the theorem classes are not a strength ladder"
        )
    frame = result.frame
    if as_ is TheoremClass.TRACED_CHANNEL and not frame.traced_outputs:
        frame = frame.with_ancillas_traced()
    frame.check_class(as_)
    return ProofResult(
        verdict=Verdict.EQUIVALENT,
        theorem=as_,
        frame=frame,
        detail=(
            f"{result.detail} (restated from {result.theorem.value} as {as_.value}: {reason}; "
            "the trace was not recomputed here)"
        ).strip(),
        checked_pairs=result.checked_pairs,
    )


def forget_instrument(result: ProofResult) -> ProofResult:
    """Sum the records away: an equal instrument gives an equal channel **of the same output frame**.

    The theorem class follows the frame, and that is the whole point. An instrument proved with the
    ancillas retained yields ``FULL_QUANTUM_CHANNEL``; an instrument proved after the partial trace
    yields ``TRACED_CHANNEL`` and never anything stronger.

    Like :func:`restate` this is a certificate-level implication: the Kraus sum is *not* evaluated
    here. A caller that wants the sum checked runs the oracle.
    """
    _require_equivalent(result, "forget_instrument")
    if result.theorem is not TheoremClass.CLASSICAL_OUTPUT_INSTRUMENT:
        raise ValueError("forget_instrument applies only to an instrument result")
    if not result.frame.observed_slots:
        raise ValueError("an instrument result must name the slots it observed")
    frame = result.frame.with_records_forgotten()
    theorem = (
        TheoremClass.TRACED_CHANNEL if result.frame.traced_outputs else TheoremClass.FULL_QUANTUM_CHANNEL
    )
    frame.check_class(theorem)
    return ProofResult(
        verdict=Verdict.EQUIVALENT,
        theorem=theorem,
        frame=frame,
        detail=(
            f"{result.detail} (records {result.frame.observed_slots} forgotten; "
            f"the output frame stays {theorem.value}; the sum was not recomputed here)"
        ).strip(),
        checked_pairs=result.checked_pairs,
    )


def classify_exception(exc: BaseException) -> Verdict:
    """Map a verifier exception onto a non-decisive verdict -- **never** ``DIFFERENT``.

    ``ResourceLimitExceeded``, timeouts and memory exhaustion mean the run did not decide anything.
    A gate or construct outside the accepted grammar is ``UNSUPPORTED``.

    Anything else is ``INTERNAL_ERROR``, deliberately distinct from ``INCONCLUSIVE``: an unexpected
    crash is a defect in the verifier, not a statement that the budget ran out, and collapsing the two
    would hide bugs behind a category that looks benign. The exception object is the diagnostic and
    callers must keep it.
    """
    if isinstance(exc, UnsupportedOperation):
        return Verdict.UNSUPPORTED
    if isinstance(exc, (ResourceLimitExceeded, TimeoutError, MemoryError)):
        return Verdict.INCONCLUSIVE
    return Verdict.INTERNAL_ERROR
