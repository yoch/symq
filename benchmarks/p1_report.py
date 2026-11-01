"""Render an inspectable P1 coverage report without inventing speed rankings."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def _duration(value) -> str:
    return "N/A" if value is None else f"{value:.4f}"


def _memory(value) -> str:
    return "N/A" if value is None else f"{value / (1024 * 1024):.1f}"


def render(report: dict) -> str:
    if (report.get("kind") != "symq-p1-public-development-comparative-pilot"
            or report.get("schema_version") != 1
            or not report.get("source_unchanged")):
        raise ValueError("not a source-stable SymQ P1 pilot")
    reps = report["repetitions"]
    doc = [
        "# SymQ P1 — matched public-source development pilot",
        "",
        f"Run UTC: {report['created_utc']}; repetitions per eligible cell: **{reps}**.",
        f"Manifest SHA-256: `{report['manifest_sha256']}`.",
        "",
        "This is an **exploratory development-only pilot**, not an untouched holdout,",
        "a new real optimizer comparison, a stable API qualification, or evidence",
        "that SymQ is generally faster than QCEC/PyZX.",
        "",
        f"Eligible measured trials: **{report['eligible_trials']}**.",
        f"Qualification counts: `{json.dumps(report['qualification_counts'],sort_keys=True)}`.",
        "Every failed/inconclusive/unsupported case remains in the raw JSON.",
        "",
        "## Theorem/engine eligibility",
        "",
        "Classical all-input X/CX/CCX/MCX **full permutation**: SymQ SAT, SymQ ZDD",
        "and deterministic MQT QCEC alternating checker (same full unitary theorem).",
        "Measurement-assisted **full coherent channel after preparation**:",
        "SymQ ZDD versus separately implemented exact Kraus/oracle (hybrid-exact).",
        "QCEC's unitary adapter does **not** support this HMR theorem.",
        "PyZX has **no verified same-theorem adapter here**; it was not run.",
        "Not-applicable and not-run are not algorithmic failures.",
        "",
        "## Per-case coverage and measurement (median of correct decisive trials)",
        "",
        "| Case | Theorem | Expected | Engine | Correct/eligible | Incomplete or wrong | Decision wall (s) | Worker wall (s) | Peak RSS (MiB) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for case in report["summary"]:
        for engine, values in case["backends"].items():
            counts = values["qualifications"]
            correct = counts.get("matched", 0)
            errors = ",".join(
                f"{k}={v}" for k, v in sorted(counts.items()) if k != "matched"
            ) or "none"
            doc.append(
                f"| {case['case_id']} | {case['theorem']} | {case['expected']} | {engine} | "
                f"{correct}/{values['eligible_trials']} | {errors} | "
                f"{_duration(values['decision_wall_seconds']['median'])} | "
                f"{_duration(values['whole_worker_wall_seconds']['median'])} | "
                f"{_memory(values['whole_worker_peak_rss_bytes']['median'])} |"
            )
    doc += [
        "",
        "## Paired, same-case ratios (exploratory only)",
        "",
    ]
    if reps < 15:
        doc += [
            "The configured 15-repetition campaign has **not** been executed in this",
            "report; no timing ratio or apparent ranking is promoted to a claim.",
            "Individual trial timings and all censored cases remain in the JSON.",
        ]
    else:
        doc += [
            "Ratios below are medians of case/repetition pairs where **both** engines",
            "proved the correct decision. Missing/timeout cases are never imputed.",
            "",
            "| Case | Ratio label | Complete matched pairs | Median | p10–p90 |",
            "| --- | --- | ---: | ---: | --- |",
        ]
        for case in report["summary"]:
            ratio = case["paired_ratio_only_matched"]
            doc.append(
                f"| {case['case_id']} | {case['ratio_title']} | {ratio['n']} | "
                f"{_duration(ratio['median'])} | "
                f"{_duration(ratio['p10'])}–{_duration(ratio['p90'])} |"
            )
        doc += [
            "",
            "These are selected exposed **development** cases and cannot establish",
            "a population speed advantage; censored trials create selection bias.",
        ]
    doc += [
        "",
        "## Provenance and deliberate limitations",
        "",
        "- MQT QCEC QASM sources: MIT, upstream commit `98d6784176bfeb6ef923d4d0220e8d486dc1982f`; only the legacy **dev** split is used. Generated commuting variants/mutants are synthetic, not independent compiler outputs.",
        "- Public KMB GF(16)/GF(64): James Barlow, Apache-2.0 **declared**, authentic SHA-256 from the user-supplied exposed dataset; SymQ's GF tower rewrite is independently constructed.",
        "- Qualtran GF2MulMBUC: Apache-2.0, commit `638777fac4379bc62e2a1e4a52cf1a1753895d48`, prepared-zero ancilla and discarded measurement records. Exhaustive small coherent-input independent Kraus oracle labels are prechecked.",
        "- Dirty borrowed-register and compute/uncompute cases are **synthetic** and exhaustive on 5/6 wires; missing-cleanup mutants are tested as true differences.",
        "- Whole-worker wall, CPU and peak RSS include startup, imports and circuit conversion; verifier decision wall is separately recorded. Hard worker CPU/wall/address-space limits are applied through fresh processes.",
        "- Full-input classical equivalence is not a proof for restricted SAT-cut assumptions; HMR coherent channel equality is not observed instrument equality.",
        "- PyZX not measured; optional QCEC missing/unsupported/timeouts are not translated into proven non-equivalence.",
        "- Existing QCEC holdout/extension and public HMR qualification are already explored elsewhere; this run has **no novel blind holdout**.",
        "- Source/fixture hashes, full status rows, environment, Python/external tool versions and raw timing/RSS distributions are stored in the companion JSON and SHA-256 sidecar.",
        "",
    ]
    return "\n".join(doc)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", required=True, type=Path)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    raw = args.input.read_bytes()
    sidecar = args.input.with_name(args.input.name + ".sha256").read_text().split()[0]
    if hashlib.sha256(raw).hexdigest() != sidecar:
        raise ValueError("P1 report data does not match its SHA-256 sidecar")
    value = json.loads(raw)
    args.output.write_text(render(value), encoding="utf-8")
    print("P1 source-backed coverage report:", args.output)


if __name__ == "__main__":
    main()
