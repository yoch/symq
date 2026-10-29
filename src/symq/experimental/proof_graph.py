"""Versioned obligation DAGs and a small, replaying proof kernel.

Discovery may propose any graph. The kernel recognizes only concrete exact
queries and conjunction, and independently verifies all reachable leaves. JSON
receipts, hashes and caller-provided verdicts are never certification authority.
"""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, fields, is_dataclass, replace
from pathlib import Path

from symq.backends import make_algebra, simulate
from symq.circuit import Gate
from symq.equivalence import check_equivalence
from symq.experimental.classical_transcript import Program
from symq.experimental.composition import (
    ChannelSlot,
    FrozenHybridProgram,
    HybridCommon,
    HybridFragment,
    hybrid_digest,
    verify_channel_transcript,
)
from symq.experimental.execution import HardLimits, IsolatedResult, run_isolated
from symq.experimental.hybrid import HOp, same_channel, same_instrument
from symq.experimental.ledger import PhaseDischarge, verify_phase_ledger
from symq.resources import (
    Budget,
    Guard,
    ResourceLimitExceeded,
    VerificationSession,
    current_session,
    session_scoped,
)

GRAPH_VERSION = "symq-obligation-dag-v1"
KERNEL_VERSION = "symq-replaying-kernel-v1"


@dataclass(frozen=True)
class ClassicalObligation:
    reference: Program
    candidate: Program
    backend: str = "sparse"
    preserved: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if type(self.reference) is not Program or type(self.candidate) is not Program:
            raise TypeError("frozen classical programs required")
        if self.reference.width != self.candidate.width:
            raise ValueError("classical obligation widths differ")
        if type(self.backend) is not str:
            raise TypeError("explicit backend required")
        if (type(self.preserved) is not tuple or len(set(self.preserved)) != len(self.preserved)
                or any(type(q) is not int or q < 0 or q >= self.reference.width
                       for q in self.preserved)):
            raise ValueError("unique preserved wires required")


@dataclass(frozen=True)
class ChannelObligation:
    reference: FrozenHybridProgram
    candidate: FrozenHybridProgram
    observed_slots: tuple[str, ...] = ()
    trace_ancillas: bool = False

    def __post_init__(self) -> None:
        if (type(self.reference) is not FrozenHybridProgram
                or type(self.candidate) is not FrozenHybridProgram):
            raise TypeError("frozen hybrid programs required")
        if type(self.trace_ancillas) is not bool or type(self.observed_slots) is not tuple:
            raise ValueError("explicit trace choice and immutable observed slots required")
        if any(type(s) is not str for s in self.observed_slots):
            raise ValueError("classical slot names must be strings")


@dataclass(frozen=True)
class TranscriptObligation:
    reference: FrozenHybridProgram
    candidate: FrozenHybridProgram
    steps: tuple[HybridCommon | ChannelSlot, ...]
    observed_slots: tuple[str, ...] = ()
    discarded_global: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if (type(self.reference) is not FrozenHybridProgram
                or type(self.candidate) is not FrozenHybridProgram):
            raise TypeError("frozen global programs required")
        if (type(self.steps) is not tuple or not self.steps
                or any(type(step) not in (HybridCommon, ChannelSlot) for step in self.steps)):
            raise ValueError("nonempty frozen composition transcript required")
        if type(self.observed_slots) is not tuple or type(self.discarded_global) is not tuple:
            raise TypeError("immutable output interfaces required")


@dataclass(frozen=True)
class LedgerObligation:
    program: FrozenHybridProgram
    discharges: tuple[PhaseDischarge, ...]
    require_all_events: bool = True

    def __post_init__(self) -> None:
        if type(self.program) is not FrozenHybridProgram:
            raise TypeError("frozen phase-ledger program required")
        if (type(self.discharges) is not tuple
                or any(type(d) is not PhaseDischarge for d in self.discharges)
                or type(self.require_all_events) is not bool):
            raise TypeError("immutable discharge claims and explicit event policy required")


_OBLIGATIONS = (ClassicalObligation, ChannelObligation, TranscriptObligation, LedgerObligation)


@dataclass(frozen=True)
class ProofNode:
    name: str
    obligation: ClassicalObligation | ChannelObligation | TranscriptObligation | LedgerObligation | None = None
    dependencies: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if type(self.name) is not str or not self.name or len(self.name) > 200:
            raise ValueError("nonempty bounded node name required")
        if (type(self.dependencies) is not tuple or len(set(self.dependencies)) != len(self.dependencies)
                or any(type(s) is not str or not s for s in self.dependencies)):
            raise ValueError("unique named dependencies required")
        if self.obligation is not None and type(self.obligation) not in _OBLIGATIONS:
            raise TypeError("kernel recognizes only exact classical/channel/transcript obligations")
        if self.obligation is not None and self.dependencies:
            raise ValueError("leaves cannot claim unverified inference dependencies")
        if self.obligation is None and not self.dependencies:
            raise ValueError("a conjunction must contain at least one obligation")


@dataclass(frozen=True)
class ProofGraph:
    nodes: tuple[ProofNode, ...]
    root: str
    version: str = GRAPH_VERSION

    def __post_init__(self) -> None:
        if self.version != GRAPH_VERSION:
            raise ValueError("unsupported proof graph version")
        if (type(self.nodes) is not tuple or not self.nodes or len(self.nodes) > 10_000
                or any(type(n) is not ProofNode for n in self.nodes)):
            raise ValueError("bounded immutable proof nodes required")
        names = [n.name for n in self.nodes]
        if len(set(names)) != len(names) or self.root not in names:
            raise ValueError("unique nodes and an existing root required")
        self.order()

    def order(self) -> tuple[ProofNode, ...]:
        """Iterative reachable topological order; reject cycles and missing nodes."""
        table = {n.name: n for n in self.nodes}
        if any(dep not in table for node in self.nodes for dep in node.dependencies):
            raise ValueError("proof graph has a missing dependency")
        state = {}
        ordered = []
        # Validate disconnected nodes too: malformed dead material is refused.
        for first in table:
            pending = [(first, False)]
            while pending:
                name, exiting = pending.pop()
                if exiting:
                    state[name] = 2
                    ordered.append(table[name])
                    continue
                status = state.get(name, 0)
                if status == 1:
                    raise ValueError("proof graph cycle")
                if status == 2:
                    continue
                state[name] = 1
                pending.append((name, True))
                pending.extend((dep, False) for dep in reversed(table[name].dependencies))
        reachable = set()
        pending = [self.root]
        while pending:
            name = pending.pop()
            if name not in reachable:
                reachable.add(name)
                pending.extend(table[name].dependencies)
        return tuple(node for node in ordered if node.name in reachable)

    def addresses(self) -> dict[str, str]:
        result = {}
        for node in self.order():
            body = [KERNEL_VERSION, _encode(node.obligation),
                    [result[d] for d in node.dependencies]]
            result[node.name] = hashlib.sha256(_canonical(body).encode()).hexdigest()
        return result

    def to_json(self) -> str:
        return _canonical(_encode(self))

    @classmethod
    def from_json(cls, text: str, *, max_bytes: int = 8_000_000) -> ProofGraph:
        if type(text) is not str or len(text.encode()) > max_bytes:
            raise ValueError("proof graph serialization exceeds size bound")
        try:
            value = _decode(json.loads(text))
        except (RecursionError, TypeError, KeyError) as exc:
            raise ValueError("malformed proof graph serialization") from exc
        if type(value) is not ProofGraph:
            raise ValueError("proof graph object required")
        return value


_SERIAL_TYPES = {t.__name__: t for t in (
    Gate, HOp, Program, FrozenHybridProgram, HybridFragment, HybridCommon, ChannelSlot,
    ClassicalObligation, ChannelObligation, TranscriptObligation, LedgerObligation, PhaseDischarge,
    ProofNode, ProofGraph,
)}


def _encode(value):
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is tuple:
        return [_encode(v) for v in value]
    if is_dataclass(value) and type(value).__name__ in _SERIAL_TYPES:
        return {"type": type(value).__name__,
                "fields": {f.name: _encode(getattr(value, f.name)) for f in fields(value)}}
    raise TypeError("unsupported proof object")


def _decode(value, depth=0):
    if depth > 128:
        raise ValueError("proof serialization depth bound exceeded")
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is list:
        return tuple(_decode(v, depth+1) for v in value)
    if type(value) is not dict or set(value) != {"type", "fields"}:
        raise ValueError("unknown proof serialization node (verdicts are not certificates)")
    cls = _SERIAL_TYPES.get(value["type"])
    if cls is None or type(value["fields"]) is not dict:
        raise ValueError("unrecognized kernel object")
    if set(value["fields"]) != {f.name for f in fields(cls)}:
        raise ValueError("proof object has missing or unexpected fields")
    return cls(**{k: _decode(v, depth+1) for k, v in value["fields"].items()})


def _canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class NodeEvidence:
    name: str
    address: str
    accepted: bool
    cached: bool
    reason: str
    independent_runs: tuple[IsolatedResult, ...] = ()


@dataclass(frozen=True)
class GraphDecision:
    accepted: bool
    root_address: str
    evidence: tuple[NodeEvidence, ...]
    kernel_version: str = KERNEL_VERSION


@session_scoped
def _verify_obligation(obligation, backend: str | None, budget: Budget | None) -> bool:
    """Importable subprocess worker; no algebra/manager crosses this boundary."""
    if type(obligation) is ClassicalObligation:
        chosen = backend or obligation.backend
        if chosen == "truthtable":
            from symq.backends.truthtable import DEFAULT_MAX_WIDTH
            if obligation.reference.width > DEFAULT_MAX_WIDTH:
                raise ResourceLimitExceeded("truth-table width", DEFAULT_MAX_WIDTH,
                                            obligation.reference.width)
        if not check_equivalence(obligation.reference.circuit(), obligation.candidate.circuit(),
                                 backend=chosen, budget=budget).equivalent:
            return False
        for p in (obligation.reference, obligation.candidate):
            if obligation.preserved:
                algebra = make_algebra(chosen, p.width, budget)
                outputs = simulate(p.circuit(), algebra)
                if not all(algebra.equal(outputs[q], algebra.variable(q)) for q in obligation.preserved):
                    return False
        return True
    if type(obligation) is ChannelObligation:
        left, right = obligation.reference.to_program(), obligation.candidate.to_program()
        if obligation.observed_slots:
            return same_instrument(left, right, observed_slots=obligation.observed_slots,
                                   trace_ancillas=obligation.trace_ancillas, budget=budget).equivalent
        return same_channel(left, right, trace_ancillas=obligation.trace_ancillas,
                            budget=budget).equivalent
    if type(obligation) is TranscriptObligation:
        verify_channel_transcript(
            obligation.reference.to_program(), obligation.candidate.to_program(), obligation.steps,
            reference_sha256=hybrid_digest(obligation.reference),
            candidate_sha256=hybrid_digest(obligation.candidate),
            observed_slots=obligation.observed_slots, discarded_global=obligation.discarded_global,
            budget=budget,
        )
        return True
    if type(obligation) is LedgerObligation:
        verify_phase_ledger(obligation.program.to_program(), obligation.discharges,
                            require_all_events=obligation.require_all_events, budget=budget)
        return True
    raise TypeError("unknown proof obligation")


class ProofKernel:
    """Replay proposed leaves; cache only results produced by this live kernel.

    A cache directory is an inspection trail. Its JSON files are write-only to
    the verifier: editing or forging them cannot create an accepted verdict.
    ``independent=True`` performs two fresh spawned runs; classical runs use
    sparse and truth-table engines. Quantum runs repeat the bounded exact
    oracle, so process independence does not claim implementation diversity.
    """
    def __init__(self, *, cache_directory: str | Path | None = None) -> None:
        self._verified: dict[tuple[str, bool], bool] = {}
        self.cache_directory = None if cache_directory is None else Path(cache_directory)

    @session_scoped
    def verify(self, graph: ProofGraph, *, budget: Budget | None = None,
               independent: bool = False, limits: HardLimits | None = None,
               parallel_workers: int = 1) -> GraphDecision:
        if type(graph) is not ProofGraph or type(independent) is not bool:
            raise TypeError("validated ProofGraph and explicit independent flag required")
        if type(parallel_workers) is not int or not 1 <= parallel_workers <= 8:
            raise ValueError("parallel_workers must be an integer from 1 to 8")
        if parallel_workers != 1 and not independent:
            raise ValueError("parallel workers require isolated independent verification")
        limits = limits or HardLimits()
        # The hard duration bounds the whole graph, including all audit runs,
        # rather than restarting for every independent leaf or child process.
        effective = Budget(max_seconds=limits.wall_seconds) if independent else Budget()
        with VerificationSession(effective):
            return self._verify_graph(graph, budget, independent, limits, parallel_workers)

    def _verify_graph(self, graph, budget, independent, limits, parallel_workers):
        guard = Guard(budget)
        guard.check_time()
        addresses = graph.addresses()
        ordered = graph.order()
        evidence = []
        accepted = {}
        independent_results = {}
        session = current_session()
        if independent:
            memory = limits.memory_bytes
            worker_limits = replace(limits, memory_bytes=None if memory is None else max(1, memory // parallel_workers))
            leaves = [node for node in ordered if node.obligation is not None
                      and (addresses[node.name], True) not in self._verified]

            def check_leaf(node):
                # Context variables do not propagate to orchestration threads.
                # Pass the absolute parent session explicitly to every worker.
                engines = (("sparse", "truthtable") if type(node.obligation) is ClassicalObligation
                           else (None, None))
                results = []
                for backend in engines:
                    session.check_time()
                    # A spawned process has a fresh clock epoch. Only this
                    # boundary converts the parent's absolute deadline into
                    # a relative duration; in-process lemmas inherit it.
                    child_budget = session.subprocess_budget()
                    result = run_isolated(_verify_obligation, node.obligation, backend, child_budget,
                                          limits=worker_limits, session=session)
                    results.append(result)
                    if result.status != "completed" or result.value is not True:
                        break
                return tuple(results)

            # At most N leaf jobs exist at once, with two sequential audits per
            # job. Process managers remain separate; only primitive results cross.
            with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
                for offset in range(0, len(leaves), parallel_workers):
                    guard.check_time()
                    batch = leaves[offset:offset+parallel_workers]
                    futures = [executor.submit(check_leaf, node) for node in batch]
                    for node, future in zip(batch, futures):
                        independent_results[node.name] = future.result()
                    guard.check_time()
        for node in ordered:
            guard.check_time()
            address = addresses[node.name]
            cache_key = (address, independent)
            runs = ()
            cached = cache_key in self._verified
            if cached:
                okay = self._verified[cache_key]
                reason = "verified immutable obligation reused by this live kernel"
            elif node.obligation is None:
                okay = all(accepted[d] for d in node.dependencies)
                reason = "all dependency obligations accepted" if okay else "dependency rejected"
            elif independent:
                runs = independent_results[node.name]
                okay = len(runs) == 2 and all(r.status == "completed" and r.value is True for r in runs)
                reason = "two isolated checks accepted" if okay else "independent leaf check not established"
            else:
                okay = _verify_obligation(node.obligation, None, budget)
                reason = "leaf recomputed by exact kernel" if okay else "leaf obligation differs"
            guard.check_time()
            accepted[node.name] = okay
            evidence.append(NodeEvidence(node.name, address, okay, cached, reason, runs))
        guard.check_time()
        # Commit successful in-memory receipts only after the complete call is
        # within its deadline; a late result never populates a successful cache.
        nodes_by_name = {node.name: node for node in ordered}
        for record in evidence:
            if self.cache_directory is not None:
                self.cache_directory.mkdir(parents=True, exist_ok=True)
                node = nodes_by_name[record.name]
                body = {"kernel": KERNEL_VERSION, "address": record.address,
                        "accepted": record.accepted,
                        "authority": "untrusted inspection receipt; leaves must be replayed",
                        "node": _encode(node)}
                path = self.cache_directory / (record.address + ".json")
                path.write_text(_canonical(body) + "\n")
        guard.check_time()
        additions = [(record.address, independent) for record in evidence
                     if record.accepted and (record.address, independent) not in self._verified]
        for key in additions:
            self._verified[key] = True
        try:
            guard.check_time()
        except BaseException:
            for key in additions:
                self._verified.pop(key, None)
            raise
        return GraphDecision(accepted[graph.root], addresses[graph.root], tuple(evidence))
