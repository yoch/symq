"""Summarize every retained trial without filtering failed or censored trials."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from pathlib import Path

REUSE = ("canonical_precompute", "canonical_complement", "canonical_split", "canonical_factorized")
PAIRS = (("canonical_cache", "published"), ("canonical_cache", "canonical"),
         ("adaptive_cache", "canonical_cache"), ("adaptive", "canonical"),
         *((method, other) for method in REUSE for other in ("published", "canonical_cache")))


def median(rows, key):
    values = [row[key] for row in rows if key in row]
    return statistics.median(values) if values else None


def geometric_mean(values):
    return math.exp(statistics.mean(map(math.log, values))) if values else None


def lifts_computed(metrics):
    """Modular lifts actually expanded: LRU misses plus pinned-table misses."""
    if "lift_misses" not in metrics:
        return None
    return metrics["lift_misses"] + metrics.get("pinned_misses", 0)


def summarize(path):
    document = json.loads(path.read_text())
    trials, methods = document["trials"], document["methods"]
    identities = {(row["case_id"], row["method"], row["repetition"]) for row in trials}
    expected = {(case["id"], method, rep) for case in document["cases"] for method in methods
                for rep in range(document["repetitions"])}
    if identities != expected or len(identities) != len(trials):
        raise ValueError("missing, duplicate or unexpected trials")
    report = {"input_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
              "trials": len(trials), "qualified": all(row["qualified"] for row in trials),
              "status_counts": dict(Counter(row.get("result", {}).get("status", "error") for row in trials)),
              "cases": [], "paired_ratios": {}, "provenance": document["provenance"]}
    for case in document["cases"]:
        line = {"id": case["id"], "methods": {}}
        for method in methods:
            rows = [row for row in trials if row["case_id"] == case["id"] and row["method"] == method]
            metrics = [row["result"]["metrics"] for row in rows if "result" in row]
            times = [row["total_seconds"] for row in metrics]
            line["methods"][method] = {
                "statuses": dict(Counter(row.get("result", {}).get("status", "error") for row in rows)),
                "median_seconds": statistics.median(times) if times else None,
                "min_seconds": min(times) if times else None, "max_seconds": max(times) if times else None,
                "selection_seconds": median(metrics, "selection_seconds"),
                "proof_seconds": median(metrics, "proof_seconds"),
                "replay_seconds": median(rows, "replay_seconds"),
                "proof_and_replay_seconds": median(rows, "proof_and_replay_seconds"),
                "construction_and_proof_seconds": median(rows, "construction_and_proof_seconds"),
                "construction_proof_replay_seconds": median(rows, "construction_proof_replay_seconds"),
                "peak_rss_kib": median(rows, "proof_peak_rss_kib"),
                "lift_requests": median(metrics, "lift_requests"),
                "lift_misses": median(metrics, "lift_misses"),
                "unique_lift_keys": median(metrics, "unique_lift_keys"),
                "cache_peak_terms": median(metrics, "cache_peak_terms"),
                "cache_evictions": median(metrics, "cache_evictions"),
                "lifts_computed": median([{"value": lifts_computed(row)} for row in metrics
                                          if lifts_computed(row) is not None], "value"),
                "pinned_peak_terms": median(metrics, "pinned_peak_terms"),
                "pinned_rejected": median(metrics, "pinned_rejected"),
                "peak_terms": median(metrics, "peak_terms"),
                "proof_translation_terms": median(metrics, "proof_translation_terms"),
                "qualified": all(row["qualified"] for row in rows)}
        report["cases"].append(line)
    by_id = {(row["case_id"], row["method"], row["repetition"]): row for row in trials}
    report["case_ratios"] = {}
    for numerator, denominator in PAIRS:
        if numerator not in methods or denominator not in methods:
            continue
        for status in ("equivalent", "not_proved"):
            values, replay_values, complete_values, proof_values = [], [], [], []
            per_case = {}
            for (case_id, method, repetition), row in by_id.items():
                if method != numerator:
                    continue
                other = by_id[case_id, denominator, repetition]
                if any(item.get("result", {}).get("status") != status or not item["qualified"]
                       for item in (row, other)):
                    continue
                values.append(row["result"]["metrics"]["total_seconds"]
                              / other["result"]["metrics"]["total_seconds"])
                per_case.setdefault(case_id, []).append(values[-1])
                # The published checker has no separate proof timer; it is excluded here.
                if "proof_seconds" in row["result"]["metrics"] and \
                        "proof_seconds" in other["result"]["metrics"]:
                    proof_values.append(row["result"]["metrics"]["proof_seconds"]
                                        / other["result"]["metrics"]["proof_seconds"])
                if "proof_and_replay_seconds" in row and "proof_and_replay_seconds" in other:
                    replay_values.append(row["proof_and_replay_seconds"] / other["proof_and_replay_seconds"])
                complete_values.append((row["source_generation_seconds"] + row["proof_outer_seconds"])
                                       / (other["source_generation_seconds"] + other["proof_outer_seconds"]))
            key = f"{numerator}/{denominator}:{status}"
            report["paired_ratios"][key] = {
                "pairs": len(values), "median": statistics.median(values) if values else None,
                "geometric_mean": math.exp(statistics.mean(map(math.log, values))) if values else None,
                "minimum": min(values) if values else None, "maximum": max(values) if values else None,
                "proof_and_replay_geometric_mean": math.exp(statistics.mean(map(math.log, replay_values)))
                if replay_values else None,
                "construction_and_proof_geometric_mean": math.exp(statistics.mean(map(math.log, complete_values)))
                if complete_values else None,
                "proof_only_pairs": len(proof_values),
                "proof_only_geometric_mean": geometric_mean(proof_values)}
            for case_id, ratios in per_case.items():
                report["case_ratios"].setdefault(f"{numerator}/{denominator}", {})[case_id] = {
                    "pairs": len(ratios), "geometric_mean": geometric_mean(ratios),
                    "minimum": min(ratios), "maximum": max(ratios)}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = summarize(args.input)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({name: report[name] for name in ("trials", "qualified", "status_counts", "paired_ratios")},
                     indent=2))
    methods = list(report["cases"][0]["methods"]) if report["cases"] else []
    labels = {"published": "Published", "canonical": "Canonical", "canonical_cache": "Cache",
              "hamming": "Hamming", "adaptive": "Adaptive", "adaptive_cache": "Adaptive+cache",
              "canonical_precompute": "Pinned", "canonical_complement": "Complement",
              "canonical_split": "Split", "canonical_factorized": "Factorized"}
    print("\n| Case | " + " | ".join(labels[method] for method in methods) + " | Status |")
    print("|---|" + "---:|" * len(methods) + "---|")
    for case in report["cases"]:
        times = [case["methods"][method]["median_seconds"] for method in methods]
        numbers = " | ".join("—" if value is None else f"{1000 * value:.3f}" for value in times)
        status = "; ".join(f"{labels[method]}: {'/'.join(case['methods'][method]['statuses'])}"
                           for method in methods)
        print(f"| {case['id']} | {numbers} | {status} |")


if __name__ == "__main__":
    main()
