"""Pinned, paired, fresh-process qualification for synthetic experimental cases.

Run from a checkout with an installed SymQ: ``python benchmarks/roadmap_campaign.py``.
The campaign times uninstrumented public ``verify`` calls.  Each worker is a
new spawned process with hard wall/CPU/address-space limits; results include
failures and unsupported cases.  No external performance claim follows from
this deliberately small synthetic corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import platform
import random
import statistics
import subprocess
import time
from collections import Counter
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any

PINNED_MANIFEST_SHA256 = "9f4ee48a72ad334debd9168a9cd90670034c9c4c9282588a6aa24339ffe1bc72"


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _fixture(case: dict) -> tuple[dict, dict, dict]:
    from symq.experimental.contracts import VerificationContract
    from symq.experimental.serialization import program_to_dict
    from symq.phase import PhaseProgram

    data, events, family = case["data"], case["events"], case["family"]
    rng = random.Random(case["seed"])
    left, right = PhaseProgram(data, 1), PhaseProgram(data, 1)
    contract = VerificationContract()
    if family == "affine_repair":
        for _ in range(events):
            q = rng.randrange(data)
            left.cx(q, data)
            event = left.hmr(data)
            left.z_if(event, q)
    elif family == "nonlinear_repair":
        for _ in range(events):
            a, b, target = rng.sample(range(data), 3)
            left.ccx(a, b, target)
            right.ccx(a, b, target)
            left.ccx(a, b, data)
            event = left.hmr(data)
            left.cz_if(event, a, b)
    elif family == "kernel_mutant":
        left.ccx(0, 1, data)
        right.ccx(0, 2, data)
        left.hmr(data)
        right.hmr(data)
    elif family == "phase_mutant":
        a, b = rng.sample(range(data), 2)
        left.mcz(a, b)
    elif family == "reduced_discard":
        left, right = PhaseProgram(data, 2), PhaseProgram(data, 1)
        left.cx(0, data).cx(0, data + 1)
        right.cx(0, data)
        outputs = tuple(rng.sample(range(data), data))
        contract = VerificationContract("reduced_channel", "zdd",
                                        left_outputs=outputs, right_outputs=outputs)
    elif family == "unsupported_reset":
        from symq.experimental.hybrid import HybridProgram
        left, right = HybridProgram(data).reset(0), HybridProgram(data)
    else:
        raise ValueError(f"unknown campaign family {family!r}")
    return program_to_dict(left), program_to_dict(right), contract.to_dict()


def _trial(left: dict, right: dict, contract: dict, seconds: float) -> dict:
    """Spawn target: input materialisation and the complete public call are timed."""
    started, cpu_started = time.perf_counter(), time.process_time()
    from symq.experimental.api import replay, verify
    from symq.experimental.contracts import VerificationContract
    from symq.experimental.serialization import program_from_dict
    from symq.resources import Budget

    left_program, right_program = program_from_dict(left), program_from_dict(right)
    declaration = VerificationContract.from_dict(contract)
    verification_started = time.perf_counter()
    result = verify(left_program, right_program, declaration,
                    budget=Budget(max_seconds=seconds, max_nodes=2_000_000))
    verification_seconds = time.perf_counter() - verification_started
    replayed = False
    if result.outcome == "different":
        replayed = replay(result, left_program, right_program, declaration,
                          budget=Budget(max_seconds=seconds)).witness_checked
    counters = dict(result.statistics)
    return {"result": result.to_dict(), "verification_wall_seconds": verification_seconds,
            "worker_trial_wall_seconds": time.perf_counter() - started,
            "worker_trial_cpu_seconds": time.process_time() - cpu_started,
            "witness_replayed": replayed,
            "conversions": {name: counters.get(name) for name in
                            ("conversions", "conversion_terms", "conversion_seconds")}}


def _source_snapshot(root: Path) -> dict:
    files = sorted(path.relative_to(root).as_posix() for path in (root / "src/symq").rglob("*")
                   if path.is_file() and path.suffix in {".py", ".c"})
    files += ["pyproject.toml", "hatch_build.py", "benchmarks/roadmap_campaign.py",
              "benchmarks/roadmap_manifest.json"]
    hashes = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in files}
    try:
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root,
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        head = "unavailable"
    from symq.backends import has_native
    native_hash = None
    if has_native():
        from symq.backends import _zdd
        native_hash = hashlib.sha256(Path(_zdd.__file__).read_bytes()).hexdigest()
    return {"git_head": head, "file_sha256": hashes,
            "native_extension_sha256": native_hash, "native_available": has_native()}


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower, upper = int(position), min(len(ordered) - 1, int(position) + 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(values: list[float]) -> dict:
    return {"count": len(values), "median": statistics.median(values) if values else None,
            "p10": _quantile(values, 0.1), "p90": _quantile(values, 0.9)}


def _summarise(rows: list[dict], cases: list[dict]) -> list[dict]:
    summaries = []
    for case in cases:
        selected = [row for row in rows if row["case_id"] == case["id"]]
        by_backend = {}
        for backend in ("zdd", "zdd-native"):
            trials = [row for row in selected if row["backend"] == backend]
            accepted = [row for row in trials if row["qualification"] == "accepted"]
            by_backend[backend] = {
                "qualifications": dict(Counter(row["qualification"] for row in trials)),
                "verification_wall_seconds": _distribution(
                    [row["value"]["verification_wall_seconds"] for row in accepted]),
                "fresh_process_wall_seconds": _distribution(
                    [row["fresh_process_wall_seconds"] for row in trials]),
                "worker_overhead_seconds": _distribution(
                    [row["worker_overhead_seconds"] for row in trials
                     if row["worker_overhead_seconds"] is not None]),
            }
        paired = []
        for repetition in sorted({row["repetition"] for row in selected}):
            pair = {row["backend"]: row for row in selected if row["repetition"] == repetition}
            if (set(pair) == {"zdd", "zdd-native"} and
                    all(row["qualification"] == "accepted" for row in pair.values())):
                native = pair["zdd-native"]["value"]["verification_wall_seconds"]
                if native > 0:
                    paired.append(pair["zdd"]["value"]["verification_wall_seconds"] / native)
        summaries.append({"case_id": case["id"], "partition": case["partition"],
                          "family": case["family"], "expected": case["expected"],
                          "backends": by_backend,
                          "paired_python_over_native_verification_ratio": _distribution(paired)})
    return summaries


def run_campaign(manifest_path: Path, *, repetitions: int | None = None,
                 partition: str = "all", wall_seconds: float | None = None) -> dict:
    from symq.experimental.execution import HardLimits, run_isolated
    from symq.experimental.serialization import load_json

    manifest = load_json(manifest_path)
    if manifest.get("schema_version") != 1:
        raise ValueError("campaign manifest schema_version 1 required")
    if _digest(manifest) != PINNED_MANIFEST_SHA256:
        raise ValueError("manifest differs from the frozen synthetic-v1 corpus")
    repetitions = manifest["default_repetitions"] if repetitions is None else repetitions
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("positive repetition count required")
    cases = [case for case in manifest["cases"] if partition == "all" or
             case["partition"] == partition]
    if not cases:
        raise ValueError("campaign partition has no cases")
    all_fixtures = {case["id"]: _fixture(case) for case in manifest["cases"]}
    if len(all_fixtures) != len(manifest["cases"]):
        raise ValueError("duplicate campaign case ID")
    partitions: dict[str, set[str]] = {"development": set(), "holdout": set()}
    seeds: dict[str, set[int]] = {"development": set(), "holdout": set()}
    fixture_records = {}
    for case in manifest["cases"]:
        fixture = all_fixtures[case["id"]]
        digest = _digest(fixture)
        partitions[case["partition"]].update((_digest(fixture[0]), _digest(fixture[1])))
        seeds[case["partition"]].add(case["seed"])
        fixture_records[case["id"]] = {"sha256": digest, "partition": case["partition"],
                                      "left_sha256": _digest(fixture[0]),
                                      "right_sha256": _digest(fixture[1])}
    if partitions["development"] & partitions["holdout"] or seeds["development"] & seeds["holdout"]:
        raise ValueError("development and holdout overlap")
    limits = HardLimits(**dict(manifest["limits"], **({"wall_seconds": wall_seconds}
                        if wall_seconds is not None else {})))
    root = Path(__file__).resolve().parents[1]
    before = _source_snapshot(root)
    rng = random.Random(manifest["shuffle_seed"])
    pairs = [(case, rep) for case in cases for rep in range(repetitions)]
    rng.shuffle(pairs)
    rows = []
    campaign_started = time.perf_counter()
    for pair_index, (case, rep) in enumerate(pairs):
        backends = list(manifest["backends"])
        rng.shuffle(backends)
        for order, backend in enumerate(backends):
            left, right, base_contract = all_fixtures[case["id"]]
            contract = dict(base_contract, backend=backend)
            isolated = run_isolated(_trial, left, right, contract, limits.wall_seconds,
                                    limits=limits)
            value = isolated.value if isolated.status == "completed" else None
            outcome = value["result"]["outcome"] if value is not None else isolated.status
            if outcome == case["expected"]:
                qualification = "expected_unsupported" if outcome == "unsupported" else "accepted"
            else:
                qualification = "unsupported" if outcome == "unsupported" else "failure"
            if outcome == "different" and value is not None and not value["witness_replayed"]:
                qualification = "failure"
            rows.append({"case_id": case["id"], "partition": case["partition"],
                         "repetition": rep, "pair_index": pair_index, "backend_order": order,
                         "backend": backend, "expected": case["expected"], "outcome": outcome,
                         "qualification": qualification, "execution_status": isolated.status,
                         "execution_reason": isolated.reason, "exitcode": isolated.exitcode,
                         "fresh_process_wall_seconds": isolated.wall_seconds,
                         "worker_overhead_seconds": None if value is None else max(
                             0.0, isolated.wall_seconds - value["worker_trial_wall_seconds"]),
                         "process_cpu_seconds": isolated.cpu_seconds,
                         "peak_rss_bytes": isolated.peak_rss_bytes, "value": value})
    after = _source_snapshot(root)
    versions = {}
    for name in ("symq", "hatchling", "pytest", "python-sat"):
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = "not installed"
    return {"schema_version": 1, "created_utc": datetime.now(timezone.utc).isoformat(),
            "manifest": manifest, "manifest_sha256": _digest(manifest),
            "repetitions": repetitions, "partition": partition,
            "source_before": before, "source_after": after,
            "source_unchanged": before == after, "fixtures": fixture_records,
            "environment": {"python": platform.python_version(), "platform": platform.platform(),
                            "machine": platform.machine(), "processor": platform.processor(),
                            "logical_cpu_count": os.cpu_count(), "versions": versions},
            "limits": {"wall_seconds": limits.wall_seconds, "memory_bytes": limits.memory_bytes,
                       "cpu_seconds": limits.cpu_seconds},
            "campaign_wall_seconds": time.perf_counter() - campaign_started,
            "qualification_counts": dict(Counter(row["qualification"] for row in rows)),
            "summary": _summarise(rows, cases), "rows": rows,
            "measurement_notes": [
                "Every trial uses a fresh spawned worker; randomized backend order within each pair.",
                "Verification timing covers the complete uninstrumented public verify call.",
                "Worker overhead includes interpreter startup, imports outside the trial, IPC and cleanup; it is not pure startup latency.",
                "CPU and peak RSS are whole-worker values, including imports and replay.",
                "Conversion fields are null when the backend does not expose them; null is not zero.",
                "Paired ratios use only matching decisive accepted results; unsupported cases and failures remain in the raw rows.",
                "This small synthetic corpus does not establish general performance superiority or real-workload scaling."]}


def write_html(payload: dict, path: Path) -> None:
    rows = []
    for summary in payload["summary"]:
        ratio = summary["paired_python_over_native_verification_ratio"]
        ratio_text = "unavailable" if ratio["median"] is None else (
            f"{ratio['median']:.3f} (p10 {ratio['p10']:.3f}, p90 {ratio['p90']:.3f})")
        rows.append(f"<tr><td>{html.escape(summary['case_id'])}</td>"
                    f"<td>{html.escape(summary['expected'])}</td><td>{ratio['count']}</td>"
                    f"<td>{ratio_text}</td></tr>")
    evidence = html.escape(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False))
    path.write_text("<!doctype html><html lang='en'><meta charset='utf-8'>"
                    "<title>SymQ synthetic qualification</title><style>body{font:16px system-ui;"
                    "max-width:1100px;margin:3rem auto;padding:1rem}table{border-collapse:collapse;"
                    "width:100%}td,th{padding:.6rem;border-bottom:1px solid #ccd}pre{overflow:auto;"
                    "background:#f3f5f7;padding:1rem;font-size:12px}</style>"
                    "<h1>SymQ synthetic qualification</h1><p>Paired Python/native verification "
                    "ratios describe only the fixed small synthetic cases below. Fresh-process "
                    "overhead is recorded separately. No general speedup claim is made.</p>"
                    f"<p>Qualifications: {html.escape(str(payload['qualification_counts']))}. "
                    f"Source unchanged during campaign: {payload['source_unchanged']}.</p>"
                    "<table><tr><th>Case</th><th>Expected</th><th>Accepted pairs</th>"
                    "<th>Python/native ratio</th></tr>" + "".join(rows) + "</table>"
                    "<details><summary>Full provenance, raw measurements and failure records</summary>"
                    f"<pre>{evidence}</pre></details></html>", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("roadmap_manifest.json"))
    parser.add_argument("--repetitions", type=int)
    parser.add_argument("--partition", choices=("all", "development", "holdout"), default="all")
    parser.add_argument("--wall-seconds", type=float)
    parser.add_argument("--out", type=Path, default=Path("benchmarks/results/roadmap-campaign.json"))
    args = parser.parse_args(argv)
    payload = run_campaign(args.manifest, repetitions=args.repetitions,
                           partition=args.partition, wall_seconds=args.wall_seconds)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n")
    write_html(payload, args.out.with_suffix(".html"))
    print(json.dumps({"out": str(args.out), "qualification_counts": payload["qualification_counts"],
                      "source_unchanged": payload["source_unchanged"]}, sort_keys=True))
    return int(not payload["source_unchanged"] or payload["qualification_counts"].get("failure", 0) > 0)


if __name__ == "__main__":
    raise SystemExit(main())
