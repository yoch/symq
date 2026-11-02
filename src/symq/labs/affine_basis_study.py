"""Opt-in basis/cache study; no API promise or change to the affine phase checker.

Only the choice of a complete kernel basis and an optional bounded lift cache vary.
The source parser, semantics, phase arithmetic and canonical receipt are the exact
affine_phase helpers. The qualification harness pins their published source.
A heuristic is never used to discharge a proof obligation.

The four ``REUSE_METHODS`` change only how each exact derivative polynomial is
assembled from modular lifts (direction-independent pinned lifts, complement and
Boolean-derivative identities, or one lift of the non-invariant phase translated as
a pseudo-Boolean polynomial); see docs/labs/affine-lift-reuse.md.
Every route yields the unique multilinear representative of the same function.
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
           "adaptive_cache", "canonical_precompute", "canonical_complement", "canonical_split",
           "canonical_factorized")
REUSE_METHODS = ("canonical_precompute", "canonical_complement", "canonical_split",
                 "canonical_factorized")
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
        # Units retained outside this LRU in the same call (a reuse method's pinned
        # table). Always 0 for the six reference methods, whose arithmetic is unchanged.
        self.reserved = 0
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
            limit = min(limit, self.work.guard.budget.max_terms - self.observed_units
                        - self.reserved)
        while self.cache and self.units > limit:
            self.evict()
        retained = self.units + self.observed_units + self.reserved
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
        self.work.check(self.units + self.observed_units + self.reserved)
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


_ONE = frozenset((0,))


class Reuse:
    """Exact derivative assembly reusing direction-independent lifts within one call.

    ``pinned`` holds lifts whose key does not depend on the direction: lift(p, -c)
    for ``canonical_precompute`` and lift(p, -2c) for the complement/split methods.
    It is filled lazily, so a predicate that is invariant along every direction is
    never lifted, and holds at most two keys per phase predicate. It is outside the
    LRU (never evicted, so the LRU caps do not bound it) but charged to the same term
    budget: together with the LRU and key statistics it never retains more than
    ``max_terms`` units, and an entry that does not fit is recomputed on demand.
    Direction-dependent lifts use the same bounded LRU as ``canonical_cache``.
    """

    def __init__(self, method, delta, basis, k, work, metrics, lifts):
        self.method, self.delta, self.basis, self.k = method, delta, basis, k
        self.modulus = 1 << k
        self.work, self.metrics, self.lifts = work, metrics, lifts
        self.pinned, self.units, self.linear, self.whole = {}, 0, {}, None
        metrics.update(pinned_requests=0, pinned_hits=0, pinned_misses=0, pinned_rejected=0,
                       pinned_peak_terms=0, affine_shortcuts=0, complement_contributions=0,
                       split_contributions=0, products_computed=0, product_terms=0)

    def lift_pinned(self, value, coefficient):
        work, metrics = self.work, self.metrics
        work.check()
        key = (value, coefficient % self.modulus, self.modulus)
        metrics["pinned_requests"] += 1
        if key in self.pinned:
            metrics["pinned_hits"] += 1
            return self.pinned[key]
        metrics["pinned_misses"] += 1
        result = core._lift(value, coefficient, self.modulus, work)
        units = len(value) + len(result) + 1
        limit = work.guard.budget.max_terms
        if limit is not None and (self.units + units
                                  > limit - self.lifts.units - self.lifts.observed_units):
            metrics["pinned_rejected"] += 1
            return result
        self.pinned[key] = result
        self.units += units
        self.lifts.reserved = self.units
        work.check(self.units + self.lifts.units + self.lifts.observed_units)
        metrics["pinned_peak_terms"] = max(self.units, metrics["pinned_peak_terms"])
        return result

    def linear_form(self, value):
        """Linear mask of an affine predicate, None for a nonlinear one (direction-free)."""
        if value not in self.linear:
            form = 0
            for mask in value:
                self.work.check()
                if mask.bit_count() > 1:
                    form = None
                    break
                form |= mask
            self.linear[value] = form
        return self.linear[value]

    def boolean_derivative(self, value, direction):
        """d = p XOR p(z XOR v), exactly; affine predicates need no substitution."""
        if self.method != "canonical_precompute":
            form = self.linear_form(value)
            if form is not None:
                self.metrics["affine_shortcuts"] += 1
                return None, (_ONE if (form & direction).bit_count() % 2 else core._ZERO)
        translated = core._translate(value, direction, self.work)
        difference = translated ^ value
        self.work.check(len(difference))
        return translated, difference

    def whole_phase(self):
        """Lift of the predicates that some basis direction does not leave invariant.

        For a direction v, predicates outside this set are v-invariant, so the
        derivative of the whole phase equals the derivative of this partial sum.
        """
        if self.whole is None:
            noninvariant = set()
            for direction in self.basis:
                for value in self.delta:
                    self.work.check(len(noninvariant))
                    if value not in noninvariant and self.boolean_derivative(value, direction)[1]:
                        noninvariant.add(value)
            whole, metrics = {}, self.metrics
            metrics["factorized_predicates"] = len(noninvariant)
            for value, coefficient in self.delta.items():
                if value in noninvariant:
                    metrics["pinned_misses"] += 1
                    for mask, term in core._lift(value, coefficient, self.modulus,
                                                 self.work).items():
                        core._add_term(whole, mask, term, self.modulus, self.work)
            metrics["factorized_terms"] = len(whole)
            self.whole = whole
        return self.whole

    def translated_difference(self, direction):
        """Delta(z XOR v) - Delta(z) for a pseudo-Boolean Delta: z_j -> 1 - z_j on v."""
        result, modulus, work = {}, self.modulus, self.work
        for mask, coefficient in self.whole_phase().items():
            changed = mask & direction
            if not changed:
                continue
            fixed, subset = mask ^ changed, changed
            while True:
                work.derivative_terms += 1
                sign = -1 if subset.bit_count() % 2 else 1
                core._add_term(result, fixed | subset, sign * coefficient, modulus, work)
                if not subset:
                    break
                subset = (subset - 1) & changed
            core._add_term(result, mask, -coefficient, modulus, work)
        return result

    def derivative(self, direction):
        if self.method == "canonical_factorized":
            return self.translated_difference(direction)
        result, modulus, work = {}, self.modulus, self.work

        def add(polynomial):
            for mask, term in polynomial.items():
                core._add_term(result, mask, term, modulus, work)

        for value, coefficient in self.delta.items():
            translated, difference = self.boolean_derivative(value, direction)
            if not difference:
                work.skipped_invariant += 1
                continue
            if self.method == "canonical_precompute" or (
                    self.method == "canonical_complement" and difference != _ONE):
                # c[p(z+v)] - c[p(z)]: only the first lift depends on the direction.
                add(self.lifts.get(translated, coefficient, modulus))
                add(self.lift_pinned(value, -coefficient))
            elif difference == _ONE:
                # c[p + 1] - c[p] = c - 2c[p].
                self.metrics["complement_contributions"] += 1
                core._add_term(result, 0, coefficient, modulus, work)
                if 2 * coefficient % modulus:
                    add(self.lift_pinned(value, -2 * coefficient))
            else:
                # c[p + d] - c[p] = c[d] - 2c[p d].
                self.metrics["split_contributions"] += 1
                add(self.lifts.get(difference, coefficient, modulus))
                if 2 * coefficient % modulus:
                    product = core._product([value, difference], work)
                    self.metrics["products_computed"] += 1
                    self.metrics["product_terms"] += len(product)
                    if product == value:
                        add(self.lift_pinned(value, -2 * coefficient))
                    else:
                        add(self.lifts.get(product, -2 * coefficient, modulus))
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
    lifts = Lifts(method.endswith("_cache") or method in REUSE_METHODS, settings, work, metrics)
    reuse = (Reuse(method, delta, basis, k, work, metrics, lifts)
             if method in REUSE_METHODS else None)
    proof_started, before = perf_counter(), work.derivative_terms
    try:
        for direction in basis:
            metrics["directions_checked"] = metrics.get("directions_checked", 0) + 1
            if reuse is None:
                difference = derivative(delta, direction, k, work, lifts)
            else:
                difference = reuse.derivative(direction)
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
        del reuse
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
