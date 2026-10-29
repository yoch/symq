"""Manager-owned reference cache: no raw ZDD root is a public cache value."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import replace
from threading import RLock

from symq.backends import make_algebra
from symq.phase import PhaseProgram
from symq.resources import ResourceLimitExceeded, VerificationSession

from .channel import (
    EmptyDomain,
    _compare_states,
    _compile,
    _diagonal_difference,
    _other_half,
    _State,
    _validate_programs,
)
from .contracts import VerificationContract, VerificationResult
from .domains import FullCube


class PreparedReference:
    """Reusable frozen reference and exact roots belonging to one private manager.

    Each comparison starts a new whole-call budget and rebinds the native
    manager's limits. Cache entries contain content-addressed result records,
    never roots from another owner. The object serializes its own comparisons.
    ``clear_cache`` compacts to live reference roots without an ANF conversion
    on native backends; Python ZDD reconstructs the reference symbolically.
    """
    def __init__(self, reference, contract=None, *, budget=None, max_cache_entries=64):
        from .api import program_hash
        from .capabilities import inspect_program
        with VerificationSession(budget) as session:
            if type(max_cache_entries) is not int or max_cache_entries < 1:
                raise ValueError("positive max_cache_entries required")
            self._contract = contract or VerificationContract()
            if type(self._contract) is not VerificationContract:
                raise TypeError("VerificationContract required")
            if type(reference) is not PhaseProgram:
                raise ValueError("prepared symbolic caching requires a sign/HMR PhaseProgram")
            reference.validate()
            self._reference = PhaseProgram(reference.data, reference.ancillas, list(reference.ops))
            capability = inspect_program(self._reference, self.contract)
            if not capability.supported or self.contract.backend == "zdd-native-blocks":
                raise ValueError("prepared caching requires an admissible monolithic backend")
            self._reference_sha256 = program_hash(self._reference)
            self._domain = self.contract.domain or FullCube(reference.data)
            self._lock = RLock()
            self._closed = False
            self._cache = OrderedDict()
            self.max_cache_entries = max_cache_entries
            self.cache_hits = 0
            self.comparisons = 0
            self._build(session)

    @property
    def contract(self):
        return self._contract

    @property
    def domain(self):
        return self._domain

    @property
    def reference_sha256(self):
        return self._reference_sha256

    def _new_baseline(self, guard):
        algebra = make_algebra(self.contract.backend, max(1, 2 * self.domain.parameters),
                               guard.budget)
        lx, legal_x = _compile(self._reference, algebra, self.domain, 0, guard)
        if algebra.is_zero(legal_x):
            raise EmptyDomain("coherent input domain is empty")
        ly, legal_y = _other_half(self._reference, algebra, self.domain, lx,
                                  self.domain.parameters, guard)
        return algebra, lx, legal_x, ly, legal_y

    def _build(self, guard):
        self._algebra, self._lx, self._legal_x, self._ly, self._legal_y = self._new_baseline(guard)

    def _owner(self):
        return getattr(self._algebra, "manager", self._algebra)

    def _bind(self, guard):
        bind = getattr(self._algebra, "bind_guard", None)
        if bind is not None:
            bind(guard)
        else:
            self._algebra.guard = guard
        guard.check_time()
        guard.check_nodes(self._algebra.node_count)
        guard.reserve(self._owner(), nodes=self._algebra.node_count)
        for root in self._roots():
            terms = self._algebra.terms(root)
            if terms is not None:
                guard.check_terms(terms)

    def _roots(self):
        return (self._lx.outputs + (self._lx.phase0,) + self._lx.outcome_coefficients +
                self._ly.outputs + (self._ly.phase0,) + self._ly.outcome_coefficients +
                (self._legal_x, self._legal_y))

    def _compact(self, guard):
        collect = getattr(self._algebra, "collect_roots", None)
        if collect is None:
            old_owner = self._owner()
            baseline = self._new_baseline(guard)
            new_algebra = baseline[0]
            guard.reserve(new_algebra, nodes=new_algebra.node_count)
            self._algebra, self._lx, self._legal_x, self._ly, self._legal_y = baseline
            guard.release(old_owner)
            return
        roots = tuple(collect(self._roots()))
        count = len(self._lx.outputs)
        events = len(self._lx.outcome_coefficients)
        half = count + 1 + events
        self._lx = _State(roots[:count], roots[count], roots[count + 1:half])
        self._ly = _State(roots[half:half + count], roots[half + count],
                          roots[half + count + 1:2 * half])
        self._legal_x, self._legal_y = roots[-2:]
        guard.check_time()

    def compare(self, candidate, *, budget=None):
        from .api import program_hash
        candidate_hash = ""
        owner_before = None
        session = None

        def record(outcome, reason, **kwargs):
            return VerificationResult(outcome, self.contract.theorem, self.contract.backend,
                                      reason, self.reference_sha256, candidate_hash,
                                      self.contract.sha256, **kwargs)
        try:
            with VerificationSession(budget) as session, self._lock:
                if self._closed:
                    raise RuntimeError("prepared reference is closed")
                if type(candidate) is not PhaseProgram:
                    raise TypeError("a PhaseProgram candidate is required")
                candidate.validate()
                snapshot = PhaseProgram(candidate.data, candidate.ancillas, list(candidate.ops))
                candidate_hash = program_hash(snapshot)
                outputs_left, outputs_right = _validate_programs(
                    self._reference, snapshot, self.contract.theorem,
                    self.contract.left_outputs, self.contract.right_outputs)
                owner_before = self._owner()
                self._bind(session)
                key = (candidate_hash, self.contract.sha256)
                cached = self._cache.get(key)
                if cached is not None:
                    self.cache_hits += 1
                    self._cache.move_to_end(key)
                    if program_hash(candidate) != candidate_hash:
                        raise RuntimeError("candidate changed during comparison")
                    return replace(cached, statistics=cached.statistics + (("cache_hit", 1),))
                rx, _ = _compile(snapshot, self._algebra, self.domain, 0, session)
                diagonal = _diagonal_difference(
                    self._reference, snapshot, self._algebra, self.domain, self._lx, rx,
                    self._legal_x, outputs_left, outputs_right, self.contract.theorem,
                    self.contract.backend, session)
                if diagonal is not None:
                    decision = diagonal
                else:
                    ry, _ = _other_half(snapshot, self._algebra, self.domain, rx,
                                         self.domain.parameters, session)
                    decision = _compare_states(
                        self._reference, snapshot, algebra=self._algebra, domain=self.domain,
                        lx=self._lx, ly=self._ly, legal_x=self._legal_x, legal_y=self._legal_y,
                        rx=rx, ry=ry, outputs_left=outputs_left, outputs_right=outputs_right,
                        theorem=self.contract.theorem, backend=self.contract.backend, guard=session)
                session.reserve(self._owner(), nodes=self._algebra.node_count)
                if program_hash(candidate) != candidate_hash:
                    raise RuntimeError("candidate changed during comparison")
                result = record("equivalent" if decision.equivalent else "different",
                                decision.reason, witness=decision.witness,
                                witness_kind=decision.witness_kind,
                                witness_checked=decision.witness is not None,
                                statistics=(("cache_hit", 0),
                                            ("coefficients_before", decision.coefficients_before),
                                            ("coefficients_after", decision.coefficients_after)) +
                                           decision.statistics,
                                coefficient_reductions=decision.coefficient_reductions)
                self.comparisons += 1
                if len(self._cache) >= self.max_cache_entries:
                    self._cache.popitem(last=False)
                    self._compact(session)
                self._cache[key] = result
                return result
        except ResourceLimitExceeded as exc:
            return record("inconclusive", str(exc))
        finally:
            if session is not None:
                if owner_before is not None:
                    session.release(owner_before)
                if not self._closed:
                    session.release(self._owner())

    def clear_cache(self, *, budget=None):
        session = None
        owner = None
        try:
            with VerificationSession(budget) as session, self._lock:
                if self._closed:
                    raise RuntimeError("prepared reference is closed")
                owner = self._owner()
                self._bind(session)
                self._compact(session)
                self._cache.clear()
        finally:
            if session is not None:
                if owner is not None:
                    session.release(owner)
                if not self._closed:
                    session.release(self._owner())

    def close(self):
        with self._lock:
            self._cache.clear()
            self._algebra = None
            self._closed = True

    def __enter__(self):
        if self._closed:
            raise RuntimeError("prepared reference is closed")
        return self

    def __exit__(self, *args):
        self.close()
