"""Source-bound resource obligations for a bounded hybrid substitution.

This research adapter reuses the coherent transcript checker and the hybrid SSA
builder. It does not accept evidence receipts as proof inputs, infer an ancilla
from liveness, or authorize a candidate. A successful local theorem may remain
conditional when the actual prefix cannot establish its clean-input condition.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from symq.circuit import UnsupportedOperation
from symq.experimental.hybrid import HOp, HybridIR, HybridProgram, freeze_hybrid
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import (
    FrozenHybridProgram,
    HybridFragment,
    _advance_known,
    _live_before,
    _writes,
    hybrid_digest,
)
from symq.labs.hybrid_substitution import check_hybrid_substitution
from symq.labs.rewrite import call_budget, check_span
from symq.resources import Budget, ResourceLimitExceeded, VerificationSession

SCHEMA = "symq-site-resources-v2"


def _name(value: str, what: str) -> None:
    if type(value) is not str or not value or len(value) > 200:
        raise ValueError(f"{what} must be a nonempty bounded string")


def _indices(value: tuple[int, ...], what: str) -> None:
    if (type(value) is not tuple or len(set(value)) != len(value)
            or any(type(q) is not int or q < 0 for q in value)):
        raise ValueError(f"{what} must be unique nonnegative integer indices")


@dataclass(frozen=True)
class ResourceLease:
    """A local wire reserved over a half-open interval of the original source.

    Reservations may extend beyond the replaced window when every operation
    outside it is disjoint from this wire. Touches (including controls and
    phases) conservatively conflict; idleness does not prove cleanliness. ``clean_zero`` means zero at entry and at
    return; arbitrary temporary values and entanglement inside are permitted.
    ``borrowed`` requires the identity channel on the borrowed information.
    """

    name: str
    wire: int
    kind: str
    interval: tuple[int, int]

    def __post_init__(self) -> None:
        _name(self.name, "resource name")
        if type(self.wire) is not int or self.wire < 0:
            raise ValueError("resource wire must be a nonnegative local index")
        if type(self.kind) is not str or self.kind not in {"clean_zero", "borrowed"}:
            raise ValueError("resource kind must be clean_zero or borrowed")
        check_span(self.interval, self.interval[1] if type(self.interval) is tuple
                   and len(self.interval) == 2 and type(self.interval[1]) is int else -1)


@dataclass(frozen=True)
class EvidenceNote:
    """Caller-supplied metadata; neither origin is certification authority."""

    resource: str
    origin: str
    detail: str

    def __post_init__(self) -> None:
        _name(self.resource, "evidence resource")
        if type(self.origin) is not str or self.origin not in {"assumption", "observation"}:
            raise ValueError("caller evidence may be an assumption or observation, never a proof")
        if type(self.detail) is not str or not self.detail or len(self.detail) > 4096:
            raise ValueError("bounded evidence detail required")


@dataclass(frozen=True)
class CacheRequirement:
    """A requested relation with a dependency watch, not a supplied theorem.

    Positions are cuts BEFORE the indexed source operation. Quantum dependencies
    are global wire indices. Every touch conservatively changes their epoch;
    classical dependencies use actual SSA assignment versions. This adapter does
    not prove arbitrary cache relations, even if every dependency is unchanged.
    """

    name: str
    relation: str
    quantum_wires: tuple[int, ...]
    classical_slots: tuple[str, ...]
    established_at: int
    used_at: int

    def __post_init__(self) -> None:
        _name(self.name, "cache name")
        _name(self.relation, "cache relation")
        if (type(self.quantum_wires) is not tuple or type(self.classical_slots) is not tuple
                or len(self.quantum_wires) + len(self.classical_slots) > 1024):
            raise ValueError("cache dependencies must be immutable and bounded by 1024")
        _indices(self.quantum_wires, "cache quantum dependencies")
        if (type(self.classical_slots) is not tuple
                or len(set(self.classical_slots)) != len(self.classical_slots)
                or any(type(s) is not str for s in self.classical_slots)):
            raise ValueError("unique immutable classical cache dependencies required")
        # Reuse the installed slot grammar, without inventing values as proof.
        HybridFragment(1, (), self.classical_slots)
        if not self.quantum_wires and not self.classical_slots:
            raise ValueError("a cache watch needs explicit dependencies")
        if (type(self.established_at) is not int or type(self.used_at) is not int
                or not 0 <= self.established_at <= self.used_at):
            raise ValueError("ordered nonnegative cache cut positions required")


@dataclass(frozen=True)
class SiteResourceRequest:
    source: FrozenHybridProgram
    span: tuple[int, int]
    replacement: HybridFragment
    wires: tuple[int, ...]
    resources: tuple[ResourceLease, ...] = ()
    caches: tuple[CacheRequirement, ...] = ()
    notes: tuple[EvidenceNote, ...] = ()
    observed_slots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.source) is not FrozenHybridProgram or type(self.replacement) is not HybridFragment:
            raise TypeError("an immutable source and replacement fragment are required")
        check_span(self.span, len(self.source.ops))
        _indices(self.wires, "local-to-global wires")
        if (len(self.wires) != self.replacement.width
                or any(q >= self.source.width for q in self.wires)):
            raise ValueError("complete in-range local-to-global mapping required")
        for values, cls in ((self.resources, ResourceLease), (self.caches, CacheRequirement),
                            (self.notes, EvidenceNote)):
            if type(values) is not tuple or len(values) > 256 or any(type(v) is not cls for v in values):
                raise TypeError("bounded immutable typed resource inputs required")
            # Frozen dataclasses can still arrive from unpickling or a caller
            # bypassing their constructor. Exact type is not field validation.
            for value in values:
                cls.__post_init__(value)
        names = [r.name for r in self.resources] + [c.name for c in self.caches]
        if len(set(names)) != len(names):
            raise ValueError("resource and cache names must be unique")
        if len({r.wire for r in self.resources}) != len(self.resources):
            raise ValueError("a wire cannot have overlapping or conflicting resource leases")
        for resource in self.resources:
            if resource.wire >= self.replacement.width:
                raise ValueError("resource wire outside local frame")
            check_span(resource.interval, len(self.source.ops))
            if not resource.interval[0] <= self.span[0] <= self.span[1] <= resource.interval[1]:
                raise ValueError("resource interval must cover the complete replacement window")
        for cache in self.caches:
            if cache.used_at > len(self.source.ops) or any(q >= self.source.width for q in cache.quantum_wires):
                raise ValueError("cache dependency outside source")
        if any(note.resource not in names for note in self.notes):
            raise ValueError("evidence notes must name an existing resource or cache")
        HybridFragment(1, (), self.observed_slots)


@dataclass(frozen=True)
class ProofAttempt:
    outcome: str
    reason: str
    theorem: str = ""
    evidence_level: str = "none"


@dataclass(frozen=True)
class ResourceObligation:
    name: str
    resource: str
    statement: str
    status: str
    reason: str
    condition_used_by_local_proof: bool = False
    evidence_origin: str = "unproved_requirement"
    dependency_versions: tuple[tuple[str, int | None, int | None], ...] = ()


@dataclass(frozen=True)
class ClassicalRead:
    operation: int
    role: str
    slot: str
    version: int
    measurement_event_mask: int

    @property
    def measurement_events(self) -> tuple[int, ...]:
        return tuple(i for i in range(self.measurement_event_mask.bit_length())
                     if self.measurement_event_mask >> i & 1)


@dataclass(frozen=True)
class SiteResourceAssessment:
    """Inspection evidence only. No candidate or application method is provided."""

    source_sha256: str
    request_sha256: str
    source_span: tuple[int, int]
    replacement_span: tuple[int, int]
    local_equivalence: ProofAttempt
    contextual_equivalence: ProofAttempt
    obligations: tuple[ResourceObligation, ...]
    notes: tuple[EvidenceNote, ...]
    classical_reads: tuple[ClassicalRead, ...]
    interrupted: str | None = None

    @property
    def site_applicability(self) -> str:
        if self.interrupted is not None or any(
            p.outcome == "inconclusive" for p in (self.local_equivalence, self.contextual_equivalence)
        ) or any(o.status == "inconclusive" for o in self.obligations):
            return "inconclusive"
        if any(o.status == "not_satisfied" for o in self.obligations):
            return "not_applicable"
        if (self.local_equivalence.outcome == "equivalent"
                and self.contextual_equivalence.outcome == "equivalent"
                and all(o.status == "proved" for o in self.obligations)):
            return "established"
        return "conditional" if self.local_equivalence.outcome == "equivalent" else "not_established"

    def to_dict(self) -> dict:
        value = asdict(self)
        value.update({
            "kind": SCHEMA, "advisory_only": True, "candidate_authorized": False,
            "site_applicability": self.site_applicability,
            "evidence_level": "recomputed_engine_decisions_not_independent_certificates",
            "coherent_control_extension": "not_established",
        })
        value["notes"] = [dict(asdict(n), condition_used_by_local_proof=False) for n in self.notes]
        return value


def _attempt(function, *args, **kwargs) -> ProofAttempt:
    try:
        result = function(*args, **kwargs)
    except UnsupportedOperation as exc:
        return ProofAttempt("unsupported", str(exc))
    return ProofAttempt(result.outcome, result.reason, result.theorem,
                        "recomputed_engine_decision" if result.certified else "none")


def _mapped(op: HOp, wires: tuple[int, ...]) -> HOp:
    return HOp(op.kind, tuple(wires[q] for q in op.wires),
               op.slot, op.condition, op.source, op.value)


def _conditional_check(reference, candidate, clean, preserved, observed, budget):
    # The artificial preparation states the local theorem's hypotheses ONLY.
    # Its success is never used as evidence that the real prefix prepares them.
    order = tuple(q for q in range(reference.width) if q not in clean) + clean
    mapping = tuple(order.index(q) for q in range(reference.width))
    prefix = tuple(HOp("store", slot=s, value=0) for s in reference.classical_inputs)
    source = HybridProgram(reference.width - len(clean), len(clean),
                           list(prefix + tuple(_mapped(o, mapping) for o in reference.ops)))
    return check_hybrid_substitution(
        source, (len(prefix), len(prefix) + len(reference.ops)), candidate,
        wires=mapping, clean=clean, preserved=preserved,
        observed_slots=observed, budget=budget,
    )


def _classical_reads(ir: HybridIR, guard) -> tuple[ClassicalRead, ...]:
    current = {}
    reads = []
    for index, op in enumerate(ir.operations):
        guard.check_time()
        inputs = [("condition", op.condition), ("source", op.source)]
        if op.operation.kind in {"invert", "oxor"}:
            inputs.append(("previous_destination", current[op.operation.slot]))
        for role, value in inputs:
            if value is not None:
                # Keep the SSA bit mask shared instead of expanding the same
                # event set for every later read of a large classical parity.
                reads.append(ClassicalRead(index, role, value.slot, value.version, value.events))
        if op.output is not None:
            current[op.output.slot] = op.output
    return tuple(reads)


def _cache_obligations(request, ir, guard):
    if not request.caches:
        return
    queries = {}
    for cache in request.caches:
        for position in {cache.established_at, cache.used_at}:
            queries.setdefault(position, []).append(cache)
    quantum = {q: -1 for c in request.caches for q in c.quantum_wires}
    classical = {s: None for c in request.caches for s in c.classical_slots}
    snapshots = {}
    for index in range(len(ir.operations) + 1):
        guard.check_time()
        for cache in queries.get(index, ()):
            # Snapshot only this relation's dependencies, not every other watch.
            snapshots[cache.name, index] = (
                tuple(quantum[q] for q in cache.quantum_wires),
                tuple(classical[s] for s in cache.classical_slots),
            )
        if index == len(ir.operations):
            break
        op = ir.operations[index]
        for q in op.operation.wires:
            if q in quantum:
                quantum[q] = index
        if op.output is not None and op.output.slot in classical:
            classical[op.output.slot] = op.output.version
    for cache in request.caches:
        before = snapshots[cache.name, cache.established_at]
        after = snapshots[cache.name, cache.used_at]
        versions = tuple((f"q{q}", a, b) for q, a, b in zip(cache.quantum_wires, before[0], after[0]))
        versions += tuple((s, a, b) for s, a, b in zip(cache.classical_slots, before[1], after[1]))
        changed = any(a != b for _, a, b in versions)
        reason = ("dependencies changed; the earlier relation must be proved again"
                  if changed else "unchanged versions do not prove the requested cache relation")
        yield ResourceObligation("cache_relation", cache.name, cache.relation,
                                 "open", reason, dependency_versions=versions)


def _fingerprint(request, source_sha):
    return canonical_sha256({
        "kind": SCHEMA, "source_sha256": source_sha, "span": request.span,
        "replacement": asdict(request.replacement), "wires": request.wires,
        "resources": [asdict(r) for r in request.resources],
        "caches": [asdict(c) for c in request.caches],
        "notes": [asdict(n) for n in request.notes], "observed_slots": request.observed_slots,
    })


def assess_site_resources(
    request: SiteResourceRequest, *, budget: Budget | None = None,
    max_operations: int = 200_000,
    max_global_wires: int = 65_536,
    max_measurement_events: int = 1024,
) -> SiteResourceAssessment:
    """Recompute local, contextual and resource claims from immutable inputs.

    The local theorem retains every quantum output and uses the actual suffix
    to select live classical records. Clean return is checked by comparing the
    candidate channel with the same channel followed by reset. Borrowed return
    reuses the transcript checker's full identity-frame obligation. Neither is
    inferred from a gate count, a classical truth table, an observation or a hash.

    Outside-window reservations require every surrounding source operation to
    be disjoint from the leased wire. Arbitrary cache predicates remain open; their source epochs/SSA versions are diagnostic evidence. General
    allocation, source streaming and newly adding a coherent control are outside
    this adapter. The existing bounded coherent checker limits still apply.
    """
    budget = call_budget(budget)
    if type(request) is not SiteResourceRequest:
        raise TypeError("SiteResourceRequest required; reports are not proof inputs")
    request.__post_init__()
    if type(max_operations) is not int or not 1 <= max_operations <= 200_000:
        raise ValueError("max_operations must be an integer in 1..200000")
    if type(max_global_wires) is not int or not 1 <= max_global_wires <= 65_536:
        raise ValueError("max_global_wires must be an integer in 1..65536")
    if type(max_measurement_events) is not int or not 1 <= max_measurement_events <= 1024:
        raise ValueError("max_measurement_events must be an integer in 1..1024")
    if budget.max_nodes is not None or budget.max_bytes is not None:
        raise ValueError("the bounded hybrid checker cannot enforce node/byte budgets")
    pending = ProofAttempt("not_run", "not checked")
    local = context = pending
    obligations = []
    reads = ()
    source_sha = request_sha = ""
    interrupted = None
    try:
        with VerificationSession(budget) as session:
            if max(len(request.source.ops), len(request.replacement.ops)) > max_operations:
                raise ResourceLimitExceeded("site operations", max_operations,
                                            max(len(request.source.ops), len(request.replacement.ops)))
            if request.source.width > max_global_wires:
                raise ResourceLimitExceeded("site global wires", max_global_wires, request.source.width)
            events = 0
            for op in request.source.ops:
                session.check_time()
                events += op.kind in {"hmr", "measure_z"}
                if events > max_measurement_events:
                    raise ResourceLimitExceeded("site measurement events", max_measurement_events, events)
            # Revalidate the entire immutable source, not caller-reported identities.
            source = request.source.to_program()
            source.validate()
            source_sha = hybrid_digest(source)
            request_sha = _fingerprint(request, source_sha)
            session.check_time()
            start, stop = request.span
            inverse = {q: i for i, q in enumerate(request.wires)}
            if any(q not in inverse for op in request.source.ops[start:stop] for q in op.wires):
                raise ValueError("the source window touches a wire outside the declared local frame")
            reference = HybridFragment(request.replacement.width, tuple(
                HOp(op.kind, tuple(inverse[q] for q in op.wires),
                    op.slot, op.condition, op.source, op.value)
                for op in request.source.ops[start:stop]
            ), request.replacement.classical_inputs)
            clean = tuple(r.wire for r in request.resources if r.kind == "clean_zero")
            borrowed = tuple(r.wire for r in request.resources if r.kind == "borrowed")
            if len(clean) == reference.width:
                raise UnsupportedOperation("at least one arbitrary local quantum input is required")
            future = _live_before(request.source.ops[stop:], set(request.observed_slots))
            live = tuple(sorted((_writes(reference.ops) | _writes(request.replacement.ops)) & future))
            ir = freeze_hybrid(source, budget=budget)
            reads = _classical_reads(ir, session)
            known = [None] * source.data + [0] * source.ancillas
            initialized = set()
            for op in request.source.ops[:start]:
                session.check_time()
                _advance_known(known, (op,))
                initialized |= _writes((op,))
            missing = set(request.replacement.classical_inputs) - initialized
            obligations.append(ResourceObligation(
                "classical_inputs", "site", "incoming classical values have prior definitions",
                "open" if missing else "proved",
                f"uninitialized incoming slots: {sorted(missing)}" if missing
                else "definitions reconstructed from the complete source prefix",
                evidence_origin="unproved_requirement" if missing else "proof",
            ))
            local = _attempt(_conditional_check, reference, request.replacement,
                             clean, (), live, budget)
            for resource in request.resources:
                session.check_time()
                global_wire = request.wires[resource.wire]
                begin, end = resource.interval
                conflicts = []
                for index in range(begin, end):
                    session.check_time()
                    if not start <= index < stop and global_wire in request.source.ops[index].wires:
                        conflicts.append(index)
                obligations.append(ResourceObligation(
                    "reservation", resource.name,
                    "outside-window operations do not use the reserved wire over its full lease",
                    "not_satisfied" if conflicts else "proved",
                    f"outside-window touches at original source operations {conflicts}" if conflicts
                    else "complete window is owned; every surrounding lease operation is disjoint",
                    evidence_origin="proof",
                ))
                if resource.kind == "clean_zero":
                    value = known[request.wires[resource.wire]]
                    status = "proved" if value == 0 else "not_satisfied" if value == 1 else "open"
                    obligations.append(ResourceObligation(
                        "clean_input", resource.name, "wire is pure zero at the insertion cut",
                        status, "zero derived from the actual prefix" if value == 0
                        else "the actual prefix proves one" if value == 1
                        else "the actual prefix has not established zero preparation",
                        condition_used_by_local_proof=True,
                        evidence_origin="proof" if value in (0, 1) else "assumption",
                    ))
                    # If the reservation is disjoint outside the owned window,
                    # its entry agrees with insertion and its return agrees with
                    # the candidate exit. This is separate from reservation.
                    if resource.interval != request.span:
                        obligations.append(ResourceObligation(
                            "lease_entry_clean", resource.name,
                            "wire is pure zero at the beginning of the full reservation",
                            "proved" if not conflicts and value == 0 else
                            "not_satisfied" if not conflicts and value == 1 else "open",
                            "disjoint leading interval preserves the proved insertion value"
                            if not conflicts and value in (0, 1) else
                            "full-reservation entry cleanliness has not been established",
                            evidence_origin="proof" if not conflicts and value in (0, 1)
                            else "unproved_requirement",
                        ))
                    returned = HybridFragment(reference.width, request.replacement.ops
                                              + (HOp("reset", (resource.wire,)),),
                                              request.replacement.classical_inputs)
                    restoration = _attempt(_conditional_check, request.replacement,
                                           returned, clean, (), live, budget)
                    statement = "candidate returns the wire to pure zero, conditional on clean inputs"
                else:
                    restoration = _attempt(_conditional_check, request.replacement,
                                           request.replacement, clean, (resource.wire,), live, budget)
                    statement = "candidate preserves borrowed information and all its correlations"
                obligations.append(ResourceObligation(
                    "restoration", resource.name, statement,
                    "proved" if restoration.outcome == "equivalent" else
                    "inconclusive" if restoration.outcome == "inconclusive" else "open",
                    restoration.reason, evidence_origin="proof"
                    if restoration.outcome == "equivalent" else "unproved_requirement",
                ))
                if resource.interval != request.span:
                    obligations.append(ResourceObligation(
                        "lease_return", resource.name,
                        "reservation return preserves the local clean/borrowed restoration theorem",
                        "proved" if not conflicts and restoration.outcome == "equivalent" else
                        "inconclusive" if restoration.outcome == "inconclusive" else "open",
                        "disjoint trailing interval preserves the proved candidate exit"
                        if not conflicts and restoration.outcome == "equivalent" else
                        "reservation return is conditional on restoration and no outside interference",
                        evidence_origin="proof" if not conflicts and restoration.outcome == "equivalent"
                        else "unproved_requirement",
                    ))
            obligations.extend(_cache_obligations(request, ir, session))
            context = _attempt(check_hybrid_substitution, source, request.span, request.replacement,
                               wires=request.wires, clean=clean, preserved=borrowed,
                               observed_slots=request.observed_slots, budget=budget)
            session.check_time()
    except ResourceLimitExceeded as exc:
        interrupted = str(exc)
    except UnsupportedOperation as exc:
        context = ProofAttempt("unsupported", str(exc))
    return SiteResourceAssessment(
        source_sha, request_sha, request.span,
        (request.span[0], request.span[0] + len(request.replacement.ops)),
        local, context, tuple(obligations), request.notes, reads, interrupted,
    )
