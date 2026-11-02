"""Untimed operation counts for the affine basis study; a companion to the timed harness.

Each (case, method) runs once in this interpreter with counting wrappers around the
published helpers and tracemalloc enabled, so nothing here is a timing. Counts are
deterministic: modular lifts expanded, coefficient additions (``_add_term`` calls,
inside lifts and while summing them), Boolean products, Boolean translation terms,
and the tracemalloc peak of the proof call. The published checker is counted through
the same module globals it calls.

``--factorized`` adds an analysis-only count (not a study method) of the single-lift
factorization D_v delta = Delta(z + v) - Delta(z), with Delta the lift of the whole
phase, under an explicit term cap; see docs/labs/affine-lift-reuse.md.
"""
from __future__ import annotations

import argparse
import json
import sys
import tracemalloc
from pathlib import Path

from benchmarks.affine_basis import cases
from benchmarks.affine_basis_cases import make_case
from symq.labs import affine_basis_study as prototype
from symq.labs import affine_phase as core
from symq.resources import Budget


class Counting:
    """Install counting wrappers on the published helpers for one call."""

    NAMES = ("_lift", "_add_term", "_product", "_translate")

    def __init__(self):
        self.counts = dict.fromkeys(("lifts", "add_terms", "products", "translations"), 0)
        self.saved = {}

    def __enter__(self):
        keys = dict(zip(self.NAMES, ("lifts", "add_terms", "products", "translations")))
        for name in self.NAMES:
            original = getattr(core, name)
            self.saved[name] = original

            def wrapper(*args, _original=original, _key=keys[name]):
                self.counts[_key] += 1
                return _original(*args)

            setattr(core, name, wrapper)
        return self

    def __exit__(self, *exc):
        for name, original in self.saved.items():
            setattr(core, name, original)
        return False


def prepared(case):
    """Exact delta, canonical basis and k, from the published helpers."""
    work = core._Work(core._guard(Budget(max_terms=10**7)))
    limits = core._limits(None)
    a = core._freeze_dyadic(case.left, limits, work)
    b = core._freeze_dyadic(case.right, limits, work)
    source = core._freeze_dephaser(case.dephaser, limits, work)
    domain = core._freeze_support(case.support, a.width, work)
    initial = core._inputs(domain)
    _, signatures = core._dephasing_semantics(source, initial, work)
    rows = tuple(sum(mask for mask in value if mask) for value in signatures)
    k = max(a.k, b.k)
    basis = core._kernel(rows, len(domain.columns), work)
    _, phase_a = core._dyadic_semantics(a, initial, k, work, True)
    _, phase_b = core._dyadic_semantics(b, initial, k, work, True)
    delta = dict(phase_a)
    for value, coefficient in phase_b.items():
        new = (delta.get(value, 0) - coefficient) % (1 << k)
        if new:
            delta[value] = new
        else:
            delta.pop(value, None)
    return delta, basis, k


def factorized(case, cap):
    """Analysis only: lift the whole phase once, then translate the pseudo-Boolean lift."""
    delta, basis, k = prepared(case)
    modulus = 1 << k
    work = core._Work(core._guard(Budget(max_terms=cap)))
    operations = 0
    try:
        whole = {}
        for value, coefficient in delta.items():
            for mask, term in core._lift(value, coefficient, modulus, work).items():
                core._add_term(whole, mask, term, modulus, work)
                operations += 1
        derivatives = []
        for direction in basis:
            out = {}
            for mask, coefficient in whole.items():
                changed = mask & direction
                fixed, subset = mask ^ changed, changed
                # prod_{j in changed} (1 - z_j) = sum_{T subset changed} (-1)^|T| z^T
                while True:
                    sign = -1 if subset.bit_count() % 2 else 1
                    core._add_term(out, fixed | subset, sign * coefficient, modulus, work)
                    operations += 1
                    if not subset:
                        break
                    subset = (subset - 1) & changed
                core._add_term(out, mask, -coefficient, modulus, work)
                operations += 1
            derivatives.append(out)
            if out:
                break
        return {"status": "computed", "whole_phase_terms": len(whole), "operations": operations,
                "nonzero_derivative": any(derivatives)}
    except core.ResourceLimitExceeded as error:
        return {"status": "term cap", "reason": str(error), "operations": operations}


def count(case_spec, method):
    case = make_case(**case_spec["spec"])
    budget = Budget(max_terms=case_spec["budget"]["max_terms"], max_seconds=60.0)
    settings = prototype.Settings(**case_spec["settings"])
    tracemalloc.start()
    try:
        with Counting() as counter:
            result = prototype.run(case.left, case.right, case.dephaser, support=case.support,
                                   method=method, budget=budget, settings=settings)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    metrics = result["metrics"]
    return {"case_id": case_spec["id"], "method": method, "status": result["status"],
            **counter.counts, "tracemalloc_peak_kib": peak / 1024,
            "peak_terms": metrics.get("peak_terms"),
            "translation_terms": metrics.get("translation_terms",
                                             metrics.get("derivative_terms")),
            "cache_evictions": metrics.get("cache_evictions"),
            "cache_peak_terms": metrics.get("cache_peak_terms"),
            "pinned_peak_terms": metrics.get("pinned_peak_terms"),
            "pinned_rejected": metrics.get("pinned_rejected"),
            "receipt": result["receipt"], "witness": result["witness"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", nargs="*")
    parser.add_argument("--methods", nargs="*", choices=prototype.METHODS,
                        default=["published", "canonical", "canonical_cache",
                                 *prototype.REUSE_METHODS])
    parser.add_argument("--factorized", action="store_true")
    parser.add_argument("--factorized-cap", type=int, default=200_000)
    args = parser.parse_args(argv)
    specs = [case for case in cases() if args.cases is None or case["id"] in args.cases]
    rows, consistent = [], True
    for spec in specs:
        reference = None
        for method in args.methods:
            row = count(spec, method)
            if reference is None:
                reference = row
            elif "inconclusive" not in (row["status"], reference["status"]):
                # Same derivative polynomials, so same decision, witness and receipt.
                same = all(row[key] == reference[key] for key in ("status", "receipt", "witness"))
                row["matches_first_method"] = same
                consistent = consistent and same
            rows.append(row)
        if args.factorized:
            rows.append({"case_id": spec["id"], "method": "factorized_analysis",
                         **factorized(make_case(**spec["spec"]), args.factorized_cap)})
    for row in rows:
        row.pop("receipt", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema": "symq.affine-basis-operations/v1",
                                       "consistent": consistent, "rows": rows}, indent=2) + "\n")
    print("| Case | Method | Status | Lifts | Additions | Products | Translation terms "
          "| Peak terms | tracemalloc KiB |")
    print("|---|---|---|---:|---:|---:|---:|---:|---:|")
    for row in rows:
        if row["method"] == "factorized_analysis":
            print(f"| {row['case_id']} | factorized (analysis) | {row['status']} | — "
                  f"| {row['operations']} | — | — | {row.get('whole_phase_terms', '—')} | — |")
            continue
        print(f"| {row['case_id']} | {row['method']} | {row['status']} | {row['lifts']} "
              f"| {row['add_terms']} | {row['products']} | {row['translation_terms']} "
              f"| {row['peak_terms']} | {row['tracemalloc_peak_kib']:.0f} |")
    return 0 if consistent else 1


if __name__ == "__main__":
    sys.exit(main())
