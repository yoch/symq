"""Opt-in basis/cache study; no API promise or change to the affine phase checker.

Only the choice of a complete kernel basis and an optional bounded lift cache vary.
The source parser, semantics, phase arithmetic and canonical receipt are the exact
affine_phase helpers. The qualification harness pins their published source.
A heuristic is never used to discharge a proof obligation.
"""
from __future__ import annotations

import math
from collections import OrderedDict
from dataclasses import dataclass
from time import perf_counter

from symq.errors import InternalInconsistency, ResourceLimitExceeded
from symq.labs import affine_phase as core
from symq.resources import Budget

METHODS = ("published", "canonical", "canonical_cache", "hamming", "adaptive",
           "adaptive_cache")
_SETTING_BOUNDS = (("max_dimension", 256), ("max_candidates", 4096),
                   ("max_search_units", 10_000_000), ("max_probe_terms", 100_000),
                   ("max_cache_entries", 4096), ("max_cache_terms", 1_000_000),
                   ("max_observed_key_terms", 1_000_000))


@dataclass(frozen=True)
class Settings:
    max_dimension: int = 64
    max_candidates: int = 128
    max_search_units: int = 250_000
    max_probe_terms: int = 2048
    max_cache_entries: int = 128
    max_cache_terms: int = 16_384
    max_observed_key_terms: int = 16_384

    def __post_init__(self):
        for name, ceiling in _SETTING_BOUNDS:
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError(f"{name} must be an exact integer in 1..{ceiling}")


def freeze_settings(value, guard):
    guard.check_time()
    if value is None:
        return Settings()
    if type(value) is not Settings:
        raise TypeError("Settings required")
    snapshot = {}
    for name, ceiling in _SETTING_BOUNDS:
        item = getattr(value, name)
        if type(item) is not int or not 1 <= item <= ceiling:
            raise ValueError(f"{name} must be an exact integer in 1..{ceiling}")
        snapshot[name] = item
        guard.check_time()
    return Settings(**snapshot)


class SearchExhausted(Exception):
    pass


class Search:
    def __init__(self, settings, work, metrics):
        self.settings, self.work, self.metrics = settings, work, metrics

    def spend(self, amount=1):
        self.work.check()
        used = self.metrics.get("search_units", 0) + amount
        if used > self.settings.max_search_units:
            raise SearchExhausted
        self.metrics["search_units"] = used


def _rank(vectors, work):
    """Independent elementary elimination; not core._kernel."""
    pivots = {}
    for vector in vectors:
        work.check()
        value = vector
        while value:
            top = value.bit_length() - 1
            if top not in pivots:
                pivots[top] = value
                break
            value ^= pivots[top]
            work.check()
    return len(pivots)


def validate_basis(rows, dimension, canonical, selected, work):
    """Prove completeness and an invertible change of coordinates, exactly."""
    nullity = dimension - _rank(rows, work)
    if len(canonical) != nullity or len(selected) != nullity:
        raise InternalInconsistency("basis cardinality does not equal nullity")
    for vector in (*canonical, *selected):
        if type(vector) is not int or not 0 < vector < (1 << dimension):
            raise InternalInconsistency("invalid basis vector")
        for row in rows:
            work.check()
            if (row & vector).bit_count() % 2:
                raise InternalInconsistency("basis vector outside the kernel")
    pivots = {}
    for index, vector in enumerate(canonical):
        value, coordinates = vector, 1 << index
        while value:
            work.check()
            top = value.bit_length() - 1
            if top not in pivots:
                pivots[top] = value, coordinates
                break
            other, coefficient = pivots[top]
            value ^= other
            coordinates ^= coefficient
        if not value:
            raise InternalInconsistency("canonical kernel basis is dependent")
    transform = []
    for vector in selected:
        value, coordinates = vector, 0
        while value:
            work.check()
            top = value.bit_length() - 1
            if top not in pivots:
                raise InternalInconsistency("selected vector outside canonical span")
            other, coefficient = pivots[top]
            value ^= other
            coordinates ^= coefficient
        reconstructed = 0
        for index, original in enumerate(canonical):
            work.check()
            if coordinates >> index & 1:
                reconstructed ^= original
        if reconstructed != vector:
            raise InternalInconsistency("change-of-basis reconstruction failed")
        transform.append(coordinates)
    if _rank(transform, work) != nullity:
        raise InternalInconsistency("change-of-basis matrix is not invertible")
    return tuple(transform)


def _candidates(rows, dimension, canonical, phase, search):
    pool = list(canonical)
    present = set(pool)

    def add(vector):
        search.spend()
        if vector and vector not in present and len(pool) < search.settings.max_candidates:
            pool.append(vector)
            present.add(vector)
        search.work.check(len(pool))

    affine_rows = []
    for value in phase:
        search.spend(len(value) + 1)
        if all(mask.bit_count() <= 1 for mask in value):
            row = sum(mask for mask in value if mask)
            if row:
                affine_rows.append(row)
    # These directions are periods of every affine phase predicate. Nonlinear
    # predicates are still probed and every final derivative is checked exactly.
    for vector in core._kernel(tuple(rows) + tuple(affine_rows), dimension, search.work):
        add(vector)
    for i, first in enumerate(canonical):
        for second in canonical[i + 1:]:
            if len(pool) >= search.settings.max_candidates:
                return tuple(pool)
            add(first ^ second)
    return tuple(pool)


def _lift_cost(term_count, coefficient, k):
    """Saturated upper proxy for _lift additions, not a runtime prediction."""
    coefficient %= 1 << k
    valuation = (coefficient & -coefficient).bit_length() - 1
    depth = min(term_count, k - valuation + 1)
    total = 0
    for size in range(1, depth + 1):
        total += math.comb(term_count, size)
        if total >= 10**12:
            return 10**12
    return total


def _score(direction, phase, k, search):
    estimate, noninvariant, unknown = 0, 0, 0
    term_limit = search.work.guard.budget.max_terms
    probe_limit = search.settings.max_probe_terms
    if term_limit is not None:
        probe_limit = min(probe_limit, term_limit)
    for value, coefficient in phase.items():
        expansion = 0
        for mask in value:
            search.spend()
            expansion += 1 << (mask & direction).bit_count()
            if expansion > probe_limit:
                break
        if expansion > probe_limit:
            unknown += 1
            estimate += 10**12
            continue
        search.spend(expansion)
        translated = core._translate(value, direction, search.work)
        estimate += expansion
        if translated != value:
            noninvariant += 1
            estimate += _lift_cost(len(value), coefficient, k)
            estimate += _lift_cost(len(translated), coefficient, k)
    return estimate, noninvariant, unknown


def _greedy(scored, work):
    selected, pivots = [], {}
    for _, vector in scored:
        value = vector
        while value:
            work.check()
            top = value.bit_length() - 1
            if top not in pivots:
                pivots[top] = value
                selected.append(vector)
                break
            value ^= pivots[top]
    return tuple(selected)


def select_basis(rows, dimension, canonical, phase, k, method, settings, work, metrics):
    start, before = perf_counter(), work.derivative_terms
    try:
        if method.startswith("canonical") or not canonical or not phase:
            metrics["selection_skipped"] = True
            return canonical
        if len(canonical) > min(settings.max_dimension, settings.max_candidates):
            metrics["selection_fallback"] = ("dimension cap" if len(canonical) > settings.max_dimension
                                             else "candidate cap")
            return canonical
        search = Search(settings, work, metrics)
        try:
            pool = _candidates(rows, dimension, canonical, phase, search)
            metrics["candidate_count"] = len(pool)
            if method == "hamming":
                scored = [((v.bit_count(), v), v) for v in pool]
                scored.sort()
                return _greedy(scored, work)
            scores = {v: _score(v, phase, k, search) for v in pool}
            scored = sorted(((scores[v][0], v.bit_count(), v), v) for v in pool)
            selected = _greedy(scored, work)
            # Expensive/noninvariant directions first avoids gratuitously deferring
            # a counterexample; cost still includes all selection work.
            selected = tuple(sorted(selected, key=lambda v: (-scores[v][1],
                                                               scores[v][0], v)))
            metrics["selected_proxy_sum"] = sum(scores[v][0] for v in selected)
            metrics["selected_predicates_noninvariant"] = sum(scores[v][1] for v in selected)
            metrics["selected_predicates_unknown"] = sum(scores[v][2] for v in selected)
            return selected
        except SearchExhausted:
            metrics["selection_fallback"] = "search work cap"
            return canonical
    finally:
        metrics["selection_seconds"] = perf_counter() - start
        metrics["selection_translation_terms"] = work.derivative_terms - before


class Lifts:
    """Deterministic LRU; accounting bounds retained key+polynomial term units."""
    def __init__(self, enabled, settings, work, metrics):
        self.enabled, self.settings, self.work, self.metrics = enabled, settings, work, metrics
        self.cache = OrderedDict()
        self.units, self.observed_units = 0, 0
        self.seen = set()
        metrics.update(lift_requests=0, lift_misses=0, lift_hits=0, cache_evictions=0,
                       cache_peak_terms=0, retained_cache_and_stats_peak_terms=0,
                       unique_lift_keys=0, unique_lift_keys_complete=True)

    def evict(self):
        old_key, old_value = self.cache.popitem(last=False)
        self.units -= len(old_key[0]) + len(old_value) + 1
        self.metrics["cache_evictions"] += 1
        self.work.check()

    def get(self, value, coefficient, modulus):
        self.work.check()
        key = (value, coefficient % modulus, modulus)
        self.metrics["lift_requests"] += 1
        observed_limit = self.settings.max_observed_key_terms
        if self.work.guard.budget.max_terms is not None:
            observed_limit = min(observed_limit, self.work.guard.budget.max_terms // 4)
        if key not in self.seen:
            units = len(value) + 1
            if self.observed_units + units <= observed_limit:
                self.seen.add(key)
                self.observed_units += units
                self.metrics["unique_lift_keys"] = len(self.seen)
            else:
                self.metrics["unique_lift_keys_complete"] = False
        limit = self.settings.max_cache_terms
        if self.work.guard.budget.max_terms is not None:
            limit = min(limit, self.work.guard.budget.max_terms - self.observed_units)
        while self.cache and self.units > limit:
            self.evict()
        retained = self.units + self.observed_units
        self.work.check(retained)
        self.metrics["retained_cache_and_stats_peak_terms"] = max(
            retained, self.metrics["retained_cache_and_stats_peak_terms"])
        if self.enabled and key in self.cache:
            self.metrics["lift_hits"] += 1
            self.cache.move_to_end(key)
            return self.cache[key]
        self.metrics["lift_misses"] += 1
        result = core._lift(value, coefficient, modulus, self.work)
        if not self.enabled:
            return result
        units = len(value) + len(result) + 1
        if units > limit:
            return result
        while self.cache and (self.units + units > limit
                              or len(self.cache) >= self.settings.max_cache_entries):
            self.evict()
        self.cache[key] = result
        self.units += units
        self.work.check(self.units + self.observed_units)
        self.metrics["cache_peak_terms"] = max(self.units, self.metrics["cache_peak_terms"])
        self.metrics["retained_cache_and_stats_peak_terms"] = max(
            self.units + self.observed_units, self.metrics["retained_cache_and_stats_peak_terms"])
        return result


def derivative(phase, direction, k, work, lifts):
    result, modulus = {}, 1 << k
    for value, coefficient in phase.items():
        translated = core._translate(value, direction, work)
        if translated == value:
            work.skipped_invariant += 1
            continue
        for mask, term in lifts.get(translated, coefficient, modulus).items():
            core._add_term(result, mask, term, modulus, work)
        for mask, term in lifts.get(value, -coefficient, modulus).items():
            core._add_term(result, mask, term, modulus, work)
    return result


def _execute(left, right, dephaser, support, method, settings, work, metrics):
    started = perf_counter()
    limits = core._limits(None)
    a = core._freeze_dyadic(left, limits, work)
    b = core._freeze_dyadic(right, limits, work)
    source = core._freeze_dephaser(dephaser, limits, work)
    if a.width != b.width or a.width != source[0]:
        raise ValueError("dyadic widths must equal dephaser data width")
    domain = core._freeze_support(support, a.width, work)
    initial = core._inputs(domain)
    work.check(sum(map(len, initial)))
    dephased, signatures = core._dephasing_semantics(source, initial, work)
    if dephased != initial + [core._ZERO] * source[1]:
        return core.AffinePhaseResult("not_proved", "dephaser must restore (input data, zero ancillas)")
    if any(mask.bit_count() > 1 for value in signatures for mask in value):
        return core.AffinePhaseResult("not_proved", "dephaser signature is not affine on this support")
    rows = tuple(sum(mask for mask in value if mask) for value in signatures)
    constants = tuple(int(0 in value) for value in signatures)
    dimension, k = len(domain.columns), max(a.k, b.k)
    canonical = core._kernel(rows, dimension, work)
    out_a, phase_a = core._dyadic_semantics(a, initial, k, work, bool(canonical))
    out_b, phase_b = core._dyadic_semantics(b, initial, k, work, bool(canonical))
    metrics.update(parameter_dimension=dimension, kernel_dimension=len(canonical),
                   signature_rank=dimension - len(canonical), singleton_fibres=not canonical,
                   source_gates=len(a.gates) + len(b.gates) + len(source[2]))
    for x, y in zip(out_a, out_b):
        if x != y:
            z = min(x ^ y, key=lambda mask: (mask.bit_count(), mask))
            witness = core._ambient(domain, z)
            if core._run(a, witness, k)[0] == core._run(b, witness, k)[0]:
                raise InternalInconsistency("output counterexample failed replay")
            return core.AffinePhaseResult("not_proved", "output functions differ on the support",
                                         witness=(witness, witness))
    delta = dict(phase_a)
    for value, coefficient in phase_b.items():
        new = (delta.get(value, 0) - coefficient) % (1 << k)
        if new:
            delta[value] = new
        else:
            delta.pop(value, None)
        work.check(sum(map(len, delta)))
    metrics.update(phase_predicates=len(delta), preparation_seconds=perf_counter() - started,
                   canonical_basis=list(canonical))
    basis = select_basis(rows, dimension, canonical, delta, k, method, settings, work, metrics)
    validation_started = perf_counter()
    transform = validate_basis(rows, dimension, canonical, basis, work)
    metrics.update(basis_validation_seconds=perf_counter() - validation_started,
                   selected_basis=list(basis), basis_transform=list(transform))
    lifts = Lifts(method.endswith("_cache"), settings, work, metrics)
    proof_started, before = perf_counter(), work.derivative_terms
    try:
        for direction in basis:
            metrics["directions_checked"] = metrics.get("directions_checked", 0) + 1
            difference = derivative(delta, direction, k, work, lifts)
            if difference:
                z = min(difference, key=lambda mask: (mask.bit_count(), mask))
                x, y = core._ambient(domain, z), core._ambient(domain, z ^ direction)
                dx = (core._run(a, x, k)[1] - core._run(b, x, k)[1]) % (1 << k)
                dy = (core._run(a, y, k)[1] - core._run(b, y, k)[1]) % (1 << k)
                if dx == dy:
                    raise InternalInconsistency("phase counterexample failed replay")
                return core.AffinePhaseResult("not_proved", "relative phase varies on a coherence fibre",
                                             witness=(x, y))
    finally:
        metrics["proof_seconds"] = perf_counter() - proof_started
        metrics["proof_translation_terms"] = work.derivative_terms - before
    identity = {"left": core._source_document(a), "right": core._source_document(b),
                "dephaser": [source[0], source[1],
                             [[op.kind, list(op.qubits), op.outcome] for op in source[2]]],
                "support": [domain.width, domain.offset, list(domain.columns)]}
    phase_document = {"singleton_fibres": not canonical,
                      "weighted_predicates": sorted((sorted(v), c) for v, c in delta.items())}
    # Portable receipt deliberately stays canonical. Equality follows from the
    # independently checked invertible basis change, not from heuristic scores.
    receipt = core.AffinePhaseReceipt(core._hash(identity), core._hash(phase_document),
                                     dimension, k, rows, constants, canonical)
    core._validate_document(receipt.to_dict(), limits, work)
    return core.AffinePhaseResult("equivalent", "all selected-basis phase derivatives vanish", receipt)


def run(left, right, dephaser, *, support=None, method="canonical", budget=None, settings=None):
    started, metrics = perf_counter(), {"method": method}
    if type(method) is not str or method not in METHODS:
        raise ValueError("unknown research method")
    guard = core._guard(budget if budget is not None else Budget(max_terms=100_000,
                                                                max_seconds=10.0))
    work = core._Work(guard)
    try:
        settings = freeze_settings(settings, guard)
        if method == "published":
            result = core.check_affine_phase(left, right, dephaser, support=support,
                                            budget=guard.inherited_budget())
            metrics.update(result.metrics)
        else:
            result = _execute(left, right, dephaser, support, method, settings, work, metrics)
        if method != "published":
            metrics.update(peak_terms=work.peak, translation_terms=work.derivative_terms,
                           skipped_invariant_contributions=work.skipped_invariant)
        output = {"status": result.status, "reason": result.reason, "witness": result.witness,
                  "receipt": None if result.receipt is None else result.receipt.to_dict(),
                  "metrics": metrics}
        del result
        # The semantic helper owns/releases all source, phase, cache and selection
        # temporaries. The original guard covers configuration, output conversion,
        # and release of the rich result before any decisive dictionary escapes.
        guard.check_time()
    except ResourceLimitExceeded as error:
        metrics.update(peak_terms=work.peak, translation_terms=work.derivative_terms,
                       skipped_invariant_contributions=work.skipped_invariant)
        output = {"status": "inconclusive", "reason": str(error), "witness": None,
                  "receipt": None, "metrics": metrics}
    metrics["total_seconds"] = perf_counter() - started
    return output
