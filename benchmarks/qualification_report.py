"""Descriptive paired/family reporting; missing and censored rows stay visible."""
from __future__ import annotations

import math
import random
import statistics
from collections import Counter, defaultdict

STATUSES = ("ok", "timeout", "oom", "unsupported", "not_run", "inconclusive", "killed", "error")


def _algorithm_family(backend):
    return {"sat": "sat", "qcec": "qcec"}.get(backend, "symbolic_anf_or_dd")


def cross_algorithm_groups(rows: list[dict]) -> tuple[list[dict], set[tuple]]:
    """Algorithm-diverse verdict agreement, separately from exhaustive oracles.

    Multiple ANF/BDD/ZDD backends do not by themselves meet this diversity gate.
    Agreement is evidence of consistency, never an independently checked proof.
    """
    buckets = defaultdict(list)
    for row in rows:
        if row["task"] in {"equivalence", "counterexample"}:
            key = (row["case_id"], row["task"], row["boundary"], row["repetition"])
            buckets[key].append(row)
    groups, checked = [], set()
    for key, members in sorted(buckets.items()):
        accepted = [r for r in members if r["status"] == "ok" and type(r.get("equivalent")) is bool]
        families = sorted({_algorithm_family(r["backend"]) for r in accepted})
        verdicts = {r["equivalent"] for r in accepted}
        status = ("insufficient_diversity" if len(families) < 2 else
                  "agreement" if len(verdicts) == 1 else "disagreement")
        if status == "agreement":
            checked.update((*key, r["backend"]) for r in accepted)
        groups.append({"case_id": key[0], "task": key[1], "boundary": key[2], "repetition": key[3],
                       "algorithm_families": families, "backends": sorted(r["backend"] for r in accepted),
                       "status": status, "equivalent": next(iter(verdicts)) if len(verdicts) == 1 else None,
                       "exhaustive_oracle_backends": sorted(r["backend"] for r in accepted if r.get("oracle_checked")),
                       "interpretation": "algorithm-diverse consistency only; not an exhaustive oracle or certificate"})
    return groups, checked


def _geomean(values):
    return math.exp(statistics.mean(math.log(v) for v in values)) if values else None


def family_summary(values: dict[str, list[float]], *, seed=20261030, draws=2000) -> dict:
    """Families are clusters, never independent individual circuit observations.

    Few clusters provide descriptive sensitivity only; the interval is not a
    justified population-level generalization or a machine-independent claim.
    """
    means = {family: _geomean(ratios) for family, ratios in values.items() if ratios}
    names = sorted(means)
    if not names:
        return {"families": 0, "family_balanced_ratio": None, "descriptive_cluster_interval": None}
    rng = random.Random(seed)
    samples = sorted(_geomean([means[rng.choice(names)] for _ in names]) for _ in range(draws))
    leave_one_out = {name: _geomean([value for other, value in means.items() if other != name])
                     for name in names}
    return {"families": len(names), "family_ratios": means,
            "family_balanced_ratio": _geomean(list(means.values())),
            "descriptive_cluster_interval": [samples[int(0.025 * (draws - 1))], samples[int(0.975 * (draws - 1))]],
            "leave_one_family_out": leave_one_out,
            "interpretation": "descriptive cluster resampling; few synthetic families do not establish population uncertainty"}


def summarise(result: dict) -> dict:
    rows = result["rows"]
    cross_groups, cross_checked = cross_algorithm_groups(rows)
    coverage = defaultdict(list)
    for row in rows:
        coverage[(row["family"], row["task"], row["boundary"], row["backend"])].append(row)
    groups = []
    for key, members in sorted(coverage.items()):
        counts = Counter(row["status"] for row in members)
        if any(status not in STATUSES for status in counts):
            raise ValueError("unknown qualification status")
        groups.append({"family": key[0], "task": key[1], "boundary": key[2], "backend": key[3],
                       "planned": len(members), "attempted": sum(row["status"] != "not_run" for row in members),
                       "counts": {s: counts[s] for s in STATUSES},
                       "computed": sum(row.get("computed", False) for row in members),
                       "service_completed": sum(row.get("service_completed", False) for row in members),
                       "validation_outcomes": dict(Counter(row.get("validation_status", "not_run")
                                                            for row in members)),
                       "exported": sum(row.get("exported", False) for row in members),
                       "oracle_checked": sum(row.get("oracle_checked", False) for row in members),
                       "cross_algorithm_checked": sum((row["case_id"], row["task"], row["boundary"],
                                                         row["repetition"], row["backend"]) in cross_checked
                                                        for row in members),
                       "witness_checked": sum(row.get("witness_checked", False) for row in members)})
    # Conditional latency ratios use identical case/task/boundary/repetition.
    # Collapse repetitions within each case before weighting cases/families:
    # censoring must not make a case with more completed repetitions heavier.
    lookup = {(r["case_id"], r["task"], r["boundary"], r["repetition"], r["backend"]): r for r in rows}
    comparisons = []
    for other in sorted({r["backend"] for r in rows} - {"zdd-native-fused"}):
        case_values = defaultdict(list)
        for key, native in lookup.items():
            case, task, boundary, repetition, backend = key
            if backend != "zdd-native-fused":
                continue
            peer = lookup.get((case, task, boundary, repetition, other))
            if (peer is None or native["status"] != "ok" or peer["status"] != "ok"
                    or not native.get("oracle_checked") or not peer.get("oracle_checked")
                    or not native.get("service_seconds", 0) > 0 or not peer.get("service_seconds", 0) > 0):
                continue
            case_values[(task, boundary, native["family"], case)].append(
                peer["service_seconds"] / native["service_seconds"])
        for task, boundary in sorted({(k[0], k[1]) for k in case_values}):
            cases = [{"family": family, "case_id": case,
                      "common_verified_pairs": len(values), "median_paired_ratio": statistics.median(values)}
                     for (t, b, family, case), values in sorted(case_values.items())
                     if (t, b) == (task, boundary)]
            families = defaultdict(list)
            for case in cases:
                families[case["family"]].append(case["median_paired_ratio"])
            comparisons.append({"numerator_backend": other, "denominator_backend": "zdd-native-fused",
                                "task": task, "boundary": boundary,
                                "common_verified_pairs": sum(c["common_verified_pairs"] for c in cases),
                                "common_verified_cases": len(cases), "case_summaries": cases,
                                "estimator": "median paired ratio per case; equal-case geometric mean within family; equal-family geometric mean",
                                **family_summary(families)})
    return {"status_counts": dict(Counter(r["status"] for r in rows)), "coverage": groups,
            "cross_algorithm_groups": cross_groups,
            "conditional_comparisons": comparisons,
            "warning": "Timing ratios require common exhaustive-oracle completions; algorithm-diverse agreement is counted separately and never sets oracle_checked. not_run/unsupported/timeouts remain separate. No headline from a singleton fingerprint."}
