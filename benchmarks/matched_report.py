"""Paired statistics and report for a ``matched.py`` result directory.

Writes ``summary.json`` (machine-readable, consumed by ``paper/tools/make_tables.py``),
``REPORT.md`` and ``SHA256SUMS``. Usage: python benchmarks/matched_report.py <result dir>
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

BOOTSTRAP = 10_000
BOOTSTRAP_SEED = 20261027

# (candidate, baseline, question). Ratios are baseline time / candidate time, so a value
# above 1 means the candidate is faster.
ABLATION = (
    ("zdd-native/algebra", "zdd-python/algebra", "C core instead of the Python ZDD (same symq driver)"),
    ("zdd-native/loop", "zdd-native/algebra", "minimal Python loop instead of symq's Algebra driver"),
    ("zdd-native/loop-sorted", "zdd-native/loop", "factors sorted by monomial count"),
    ("zdd-native/fused", "zdd-native/loop-sorted", "gate loop fused in C"),
    ("zdd-native/fused", "zdd-python/algebra", "all of the above"),
)
MATCHED = (
    ("zdd-native/loop", "polybori/loop", "same minimal loop, gate order"),
    ("zdd-native/loop-sorted", "polybori/loop-sorted", "same minimal loop, sorted factors"),
    ("zdd-native/algebra", "polybori/algebra", "same symq Algebra driver"),
    ("zdd-native/fused", "polybori/best", "shipped fused loop vs PolyBoRi's best driver"),
    ("zdd-native/loop", "cudd-bdd/loop", "same minimal loop, CUDD BDD (dynamic reordering)"),
    ("zdd-native/loop", "cudd-bdd-static/loop", "same minimal loop, CUDD BDD (no reordering)"),
    ("zdd-native/fused", "sparse/algebra", "shipped fused loop vs symq's sparse Python ANF"),
)
QCEC = (("zdd-native/fused", "qcec", "verdict with polynomials vs MQT QCEC verdict"),)
PHASES = ("compute", "end_to_end", "warm:compute")
BEST = {"polybori/best": ("polybori/algebra", "polybori/loop", "polybori/loop-sorted")}


def load(target: Path) -> tuple[dict, list[dict]]:
    env = json.loads((target / "environment.json").read_text())
    rows = [json.loads(line) for line in (target / "results.jsonl").read_text().splitlines()]
    return env, rows


def median_phase(row: dict, phase: str) -> float | None:
    """``phase`` reads the cold runs; ``warm:phase`` the runs on a reused manager."""
    key = "warm_phases" if phase.startswith("warm:") else "phases"
    values = (row.get(key) or {}).get(phase.removeprefix("warm:"))
    return statistics.median(values) if values else None


def family(name: str) -> str:
    return name.split("_", 1)[0]


def index(rows: list[dict]) -> dict:
    table: dict = {}
    for row in rows:
        table[(row["circuit"], row["workload"], row["mode"])] = row
    for best, members in BEST.items():
        keys = {(c, w) for (c, w, m) in table if m in members}
        for circuit, workload in keys:
            candidates = [table[(circuit, workload, m)] for m in members
                          if (circuit, workload, m) in table]
            done = [r for r in candidates if r.get("status") == "ok"]
            if done:
                fastest = {}
                for phase in PHASES:
                    times = [median_phase(r, phase) for r in done]
                    times = [t for t in times if t is not None]
                    if times:
                        fastest[phase] = [min(times)]
                table[(circuit, workload, best)] = {
                    "status": "ok", "circuit": circuit,
                    "phases": {k: v for k, v in fastest.items() if ":" not in k},
                    "warm_phases": {k.removeprefix("warm:"): v for k, v in fastest.items()
                                    if ":" in k}}
            else:
                table[(circuit, workload, best)] = {"status": candidates[0].get("status")}
    return table


def geomean(values: list[float]) -> float:
    return math.exp(sum(math.log(v) for v in values) / len(values))


def bootstrap(values: list[float]) -> tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)
    logs = [math.log(v) for v in values]
    means = sorted(sum(rng.choice(logs) for _ in logs) / len(logs) for _ in range(BOOTSTRAP))
    return math.exp(means[int(0.025 * BOOTSTRAP)]), math.exp(means[int(0.975 * BOOTSTRAP) - 1])


def compare(table: dict, circuits: list[str], workload: str, candidate: str, baseline: str,
            phase: str) -> dict:
    ratios, per_circuit = [], {}
    only_candidate = only_baseline = neither = 0
    for circuit in circuits:
        a = table.get((circuit, workload, candidate))
        b = table.get((circuit, workload, baseline))
        if a is None or b is None:
            continue
        ok_a, ok_b = a.get("status") == "ok", b.get("status") == "ok"
        if ok_a and ok_b:
            ta, tb = median_phase(a, phase), median_phase(b, phase)
            if ta and tb:
                ratios.append(tb / ta)
                per_circuit[circuit] = {"candidate": ta, "baseline": tb, "ratio": tb / ta}
        elif ok_a:
            only_candidate += 1
        elif ok_b:
            only_baseline += 1
        else:
            neither += 1
    result = {"candidate": candidate, "baseline": baseline, "workload": workload,
              "phase": phase, "n": len(ratios), "only_candidate": only_candidate,
              "only_baseline": only_baseline, "neither": neither, "per_circuit": per_circuit}
    if ratios:
        low, high = bootstrap(ratios)
        result.update(geomean=geomean(ratios), ci95=[low, high],
                      median=statistics.median(ratios), min=min(ratios), max=max(ratios),
                      wins=sum(r > 1 for r in ratios))
    return result


def summarise(env: dict, rows: list[dict]) -> dict:
    table = index(rows)
    circuits = sorted({r["circuit"] for r in rows})
    workloads = sorted({r["workload"] for r in rows})
    families = sorted({family(c) for c in circuits})
    status = defaultdict(Counter)
    for row in rows:
        status[row["mode"]][row["status"]] += 1
    disagreements, invalid_witnesses = [], []
    groups = defaultdict(set)
    for row in rows:
        if row.get("status") == "ok" and row.get("fingerprint"):
            groups[(row["circuit"], row["workload"])].add(row["fingerprint"])
        if row.get("witness_valid") is False:
            invalid_witnesses.append([row["circuit"], row["workload"], row["mode"]])
    for key, prints in sorted(groups.items()):
        if len(prints) > 1:
            disagreements.append(list(key))
    wrong = [[r["circuit"], r["workload"], r["mode"]] for r in rows
             if r.get("status") == "wrong_verdict"]
    comparisons = []
    for group, specs in (("ablation", ABLATION), ("matched", MATCHED), ("qcec", QCEC)):
        for candidate, baseline, question in specs:
            for workload in workloads:
                if group == "qcec" and workload == "simulate":
                    continue
                for phase in PHASES:
                    item = compare(table, circuits, workload, candidate, baseline, phase)
                    item.update(group=group, question=question)
                    if group == "matched" and phase == "compute":
                        item["by_family"] = {}
                        for name in families:
                            members = [c for c in circuits if family(c) == name]
                            part = compare(table, members, workload, candidate, baseline,
                                           phase)
                            part.pop("per_circuit")
                            item["by_family"][name] = part
                    comparisons.append(item)
    medians = {}
    for (circuit, workload, mode), row in table.items():
        if row.get("status") == "ok":
            medians.setdefault(f"{circuit}|{workload}|{mode}", {
                phase: median_phase(row, phase)
                for phase in ("setup", "compute", "compare", "witness", "end_to_end",
                              "conversion", "warm:compute", "warm:end_to_end")
                if median_phase(row, phase) is not None
            } | {k: row[k] for k in ("extract_seconds", "rss_growth_kib", "zdd_nodes",
                                      "output_terms", "extract_failure", "status")
                 if k in row})
    return {
        "environment": {k: env.get(k) for k in (
            "symq_commit", "symq_dirty", "symq_tree_sha256", "native_extension_sha256",
            "native_source_sha256", "compiler", "compiler_flags", "python", "platform",
            "cpu_model", "cpu_count", "corpus", "corpus_manifest_sha256", "external_versions",
            "started_utc")},
        "protocol": env.get("protocol"),
        "circuits": circuits,
        "families": families,
        "status": {mode: dict(counts) for mode, counts in sorted(status.items())},
        "correctness": {"fingerprint_disagreements": disagreements,
                        "wrong_verdicts": wrong, "invalid_witnesses": invalid_witnesses,
                        "groups_checked": len(groups)},
        "comparisons": comparisons,
        "medians": medians,
    }


def fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}"


def render(summary: dict) -> str:
    env = summary["environment"]
    lines = [
        f"# Matched-driver benchmark — corpus `{env['corpus']}`",
        "",
        (f"symq `{env['symq_commit']}` (dirty: {env['symq_dirty']}), native extension "
        f"SHA-256 `{(env['native_extension_sha256'] or '')[:16]}…`, {env['compiler']}, "
        f"{env['python'].split()[0]}, {env['cpu_model']} ({env['cpu_count']} vCPU), "
        f"started {env['started_utc']}."),
        "",
        ("Ratios are paired per circuit: baseline time / candidate time (> 1: candidate "
        "faster). Geometric mean with a 95% bootstrap interval over circuits, median, range "
        "and wins. `n` counts circuits both sides completed; one-sided completions are listed."),
        "",
        "## Correctness",
        "",
        (f"- Output groups checked: {summary['correctness']['groups_checked']}; fingerprint "
        f"disagreements: {len(summary['correctness']['fingerprint_disagreements'])}; wrong "
        f"verdicts: {len(summary['correctness']['wrong_verdicts'])}; invalid witnesses: "
        f"{len(summary['correctness']['invalid_witnesses'])}."),
        "",
        "| mode | " + " | ".join(sorted({s for c in summary["status"].values() for s in c}))
        + " |",
    ]
    statuses = sorted({s for c in summary["status"].values() for s in c})
    lines.append("|---|" + "---:|" * len(statuses))
    for mode, counts in summary["status"].items():
        lines.append(f"| `{mode}` | " + " | ".join(str(counts.get(s, 0)) for s in statuses)
                     + " |")
    for group, title in (("ablation", "E1 — ablation of the native engine"),
                         ("matched", "E2 — matched drivers against native baselines"),
                         ("qcec", "MQT QCEC (verdicts only)")):
        lines += ["", f"## {title}", "",
                  ("| candidate | baseline | workload | phase | n | geomean [95% CI] | median "
                  "| range | wins | only cand. | only base. |"),
                  "|---|---|---|---|---:|---|---:|---|---:|---:|---:|"]
        for item in summary["comparisons"]:
            if item["group"] != group:
                continue
            ci = item.get("ci95")
            lines.append(
                f"| `{item['candidate']}` | `{item['baseline']}` | {item['workload']} | "
                f"{item['phase']} | {item['n']} | "
                + (f"{fmt(item['geomean'])} [{fmt(ci[0])}, {fmt(ci[1])}]" if ci else "—")
                + f" | {fmt(item.get('median'))} | "
                + (f"{fmt(item['min'])}–{fmt(item['max'])}" if "min" in item else "—")
                + f" | {item.get('wins', 0)} | {item['only_candidate']} | "
                f"{item['only_baseline']} |")
    lines += ["", "## E2 by family (compute phase, simulate)", "",
              "| candidate | baseline | family | n | geomean | range | only cand. | only base. |",
              "|---|---|---|---:|---:|---|---:|---:|"]
    for item in summary["comparisons"]:
        if item["group"] == "matched" and item["phase"] == "compute" \
                and item["workload"] == "simulate":
            for name, part in item["by_family"].items():
                lines.append(
                    f"| `{item['candidate']}` | `{item['baseline']}` | {name} | {part['n']} | "
                    f"{fmt(part.get('geomean'))} | "
                    + (f"{fmt(part['min'])}–{fmt(part['max'])}" if "min" in part else "—")
                    + f" | {part['only_candidate']} | {part['only_baseline']} |")
    return "\n".join(lines) + "\n"


def write_report(target: Path) -> str:
    env, rows = load(target)
    summary = summarise(env, rows)
    (target / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    report = render(summary)
    (target / "REPORT.md").write_text(report)
    sums = []
    for name in ("environment.json", "results.jsonl", "summary.json", "REPORT.md"):
        sums.append(f"{hashlib.sha256((target / name).read_bytes()).hexdigest()}  {name}")
    if (target / "working-tree.patch").exists():
        data = (target / "working-tree.patch").read_bytes()
        sums.append(f"{hashlib.sha256(data).hexdigest()}  working-tree.patch")
    (target / "SHA256SUMS").write_text("\n".join(sums) + "\n")
    return report


if __name__ == "__main__":
    print(write_report(Path(sys.argv[1])))
