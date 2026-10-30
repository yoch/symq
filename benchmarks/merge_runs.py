"""Build a derived result directory from a base ``matched.py`` run and targeted re-runs.

A long campaign can lose cells to incidents that are not properties of the engines: a worker
killed by the shared memory cgroup, a source tree changed under a running campaign. The base
directory is never edited. This script writes a new directory whose ``results.jsonl`` is the
base rows with the cells of the override runs substituted, keeps the untouched base rows in
``results.raw.jsonl``, lists every substitution in ``merge.json``, and regenerates the
summary, report and checksums with ``matched_report``.

Usage::

    python benchmarks/merge_runs.py --base RUN --label NAME \\
        [--override RUN[@mode,mode[@workload,workload]]]... [--out DIR]

An override directory contributes only the cells selected by its optional filters. Remaining
``error`` rows of a worker killed by SIGKILL (return code -9, or, in runs that did not record
it, no output at all) are re-labelled ``killed``; any other ``error`` aborts the merge,
because it would be a real failure.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import matched_report

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "results"
SEALED = ("environment.json", "results.jsonl", "results.raw.jsonl", "merge.json",
          "summary.json", "REPORT.md")


def key(row: dict) -> tuple[str, str, str]:
    return (row["circuit"], row["workload"], row["mode"])


def read_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in (path / "results.jsonl").read_text().splitlines()]


def parse_override(spec: str) -> tuple[Path, set[str] | None, set[str] | None]:
    parts = spec.split("@")
    modes = set(parts[1].split(",")) if len(parts) > 1 and parts[1] else None
    workloads = set(parts[2].split(",")) if len(parts) > 2 and parts[2] else None
    path = Path(parts[0])
    return (path if path.is_absolute() else RESULTS / path), modes, workloads


def chain_problems(rows: list[dict]) -> list[str]:
    """Report a completed cell larger than a timed-out one in the same censoring chain.

    Chains are those of the corrected harness (random circuits grouped by gates and controls),
    which refine the older per-family chains, so the check is valid for rows of either."""
    chains: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        parts = row["circuit"].split("_")
        chain = "_".join([parts[0], *parts[2:]]) if parts[0] == "rand" else parts[0]
        chains.setdefault((chain, row["workload"], row["mode"]), []).append(row)
    problems = []
    for (chain, workload, mode), members in chains.items():
        members.sort(key=lambda r: (r["width"], r["gates"], r["circuit"]))
        timed_out = None
        for row in members:
            if timed_out and row["status"] == "ok":
                problems.append(f"{row['circuit']} {workload} {mode}: completed although "
                                f"{timed_out} of the same chain timed out")
            if row["status"] == "timeout" and timed_out is None:
                timed_out = row["circuit"]
    return problems


def merge(base: Path, overrides: list[str], label: str, out: Path) -> Path:
    env = json.loads((base / "environment.json").read_text())
    base_rows = read_rows(base)
    merged = {key(row): row for row in base_rows}
    log = []
    sources = [{"role": "base", "dir": base.name, "symq_commit": env.get("symq_commit"),
                "native_source_sha256": env.get("native_source_sha256")}]
    for spec in overrides:
        path, modes, workloads = parse_override(spec)
        other_env = json.loads((path / "environment.json").read_text())
        if other_env.get("corpus_manifest_sha256") != env.get("corpus_manifest_sha256"):
            raise SystemExit(f"{path.name}: another corpus manifest than the base run")
        sources.append({"role": "override", "dir": path.name, "filter_modes": sorted(modes or []),
                        "filter_workloads": sorted(workloads or []),
                        "symq_commit": other_env.get("symq_commit"),
                        "native_source_sha256": other_env.get("native_source_sha256")})
        for row in read_rows(path):
            if (modes and row["mode"] not in modes) or (
                    workloads and row["workload"] not in workloads):
                continue
            old = merged.get(key(row))
            if old is None:
                raise SystemExit(f"{path.name}: cell {key(row)} is not in the base run")
            log.append({"cell": list(key(row)), "base_status": old["status"],
                        "new_status": row["status"], "source": path.name})
            merged[key(row)] = row
    final = []
    for row in base_rows:
        row = merged[key(row)]
        if row["status"] == "error":
            if row.get("returncode", -9) != -9 or row.get("stderr"):
                raise SystemExit(f"genuine error left in {key(row)}: {row.get('stderr', '')[-200:]}")
            row = {**row, "status": "killed",
                   "reason": "worker killed without output (SIGKILL; memory cgroup out of memory)"}
            log.append({"cell": list(key(row)), "base_status": "error", "new_status": "killed",
                        "source": "relabelled"})
        final.append(row)
    out.mkdir(parents=True, exist_ok=False)
    env = {**env, "merged_from": sources, "derived_label": label}
    (out / "environment.json").write_text(json.dumps(env, indent=2) + "\n")
    (out / "results.jsonl").write_text("".join(json.dumps(r) + "\n" for r in final))
    (out / "results.raw.jsonl").write_text("".join(json.dumps(r) + "\n" for r in base_rows))
    problems = chain_problems(final)
    (out / "merge.json").write_text(json.dumps(
        {"sources": sources, "substitutions": log, "chain_inconsistencies": problems},
        indent=1) + "\n")
    matched_report.write_report(out)
    sums = [f"{hashlib.sha256((out / name).read_bytes()).hexdigest()}  {name}" for name in SEALED]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--override", action="append", default=[])
    parser.add_argument("--label", required=True)
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()
    base = args.base if args.base.is_absolute() else RESULTS / args.base
    env = json.loads((base / "environment.json").read_text())
    stamp = env["started_utc"].replace("-", "").replace(":", "")
    target = args.out / f"{stamp}_{env['symq_commit'][:12]}_{args.label}"
    out = merge(base, args.override, args.label, target)
    info = json.loads((out / "merge.json").read_text())
    print(f"{out}: {len(info['substitutions'])} substitutions, "
          f"{len(info['chain_inconsistencies'])} chain inconsistencies")
    for line in info["chain_inconsistencies"]:
        print("  ", line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
