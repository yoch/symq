"""Summarize a result directory into REPORT.md and seal it with SHA256SUMS.

Usage: python benchmarks/report.py benchmarks/results/<run>
"""
from __future__ import annotations

import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

HISTORICAL = Path(__file__).resolve().parent / "historical" / "handoff_2026-10-27.json"
BASELINE = "sparse-copy"
OUTLIER = "c2_181"
SPLIT_ORDER = {"dev": 0, "holdout": 1, "extension": 2}
NATIVE_ALGEBRAS = ("polybori", "cudd-bdd", "cudd-zdd")


def load(directory: Path) -> tuple[dict, list[dict]]:
    env = json.loads((directory / "environment.json").read_text())
    rows = [json.loads(line) for line in (directory / "results.jsonl").read_text().splitlines()]
    return env, rows


def median_ms(row: dict) -> float | None:
    if row.get("status") != "ok":
        return None
    return statistics.median(row["seconds"]) * 1000


def fmt_ms(value: float) -> str:
    return f"{value:.3g}" if value < 100 else f"{value:.0f}"


def status_label(row: dict) -> str:
    if row is None:
        return "—"
    if row["status"] == "ok":
        return fmt_ms(median_ms(row))
    if row["status"] == "resource_limit":
        return f"refused ({row['resource']})"
    return row["status"]


def summarize(ratios: list[float]) -> str:
    if not ratios:
        return "n=0"
    geo = math.exp(sum(math.log(r) for r in ratios) / len(ratios))
    return (f"n={len(ratios)}, median {statistics.median(ratios):.2f}×, geomean {geo:.2f}×, "
            f"range {min(ratios):.2f}–{max(ratios):.2f}×")


def median_list_ms(values: list[float] | None) -> str:
    return fmt_ms(statistics.median(values) * 1000) if values else "—"


def native_section(env: dict, backends: list[str], cells: dict, circuits: list) -> list[str]:
    native = [b for b in backends if b in NATIVE_ALGEBRAS]
    if not native and "qcec" not in backends:
        return []
    external = env.get("external", {})
    versions = ", ".join(f"{k} {v}" for k, v in sorted(external.get("versions", {}).items()))
    out = ["", "## Native tools", "",
           f"- Versions: {versions or 'not recorded'}.",
           (f"- CUDD variable reordering: {external.get('cudd_reordering', 'not recorded')}; "
            f"PolyBoRi monomial order: `{external.get('polybori_order', 'not recorded')}`."),
           ("- Native algebras run the same simulate/equivalence code as the symq backends. "
            "Their times exclude the conversion of the final outputs to ANF (needed only for the "
            "fingerprint), reported here separately."),
           ("- tracemalloc only sees Python allocations: memory held by the C/C++ libraries "
            "(BDD/ZDD nodes, PolyBoRi diagrams, QCEC decision diagrams) is not counted in the "
            "KiB columns; worker peak RSS includes it.")]
    if native:
        out += ["", ("Native representation size of the `simulate` outputs (sum of node counts, "
                     "shared nodes counted per output) and ANF conversion time (ms):"), "",
                "| circuit | " + " | ".join(f"`{b}` nodes | `{b}` conversion" for b in native)
                + " |", "|---|" + "---:|---:|" * len(native)]
        for (_, name, *_rest) in circuits:
            sim = [cells.get((name, "simulate", b)) for b in native]
            if all(r is None for r in sim):
                continue
            out.append(f"| `{name}` | " + " | ".join(
                f"{r['native_nodes']} | {fmt_ms(r['conversion_seconds'] * 1000)}"
                if r and r["status"] == "ok" else "— | —" for r in sim) + " |")
    if "qcec" in backends:
        out += ["", (f"`qcec` configuration: `{json.dumps(external.get('qcec_configuration'))}`. "
                     "Median wall time of `qcec.verify` versus QCEC's own reported check and "
                     "preprocessing times (ms); the circuit conversion to `QuantumComputation` "
                     "is excluded from the timed runs."), "",
                "| circuit | workload | verdict | wall | check | preprocessing |",
                "|---|---|---|---:|---:|---:|"]
        for (_, name, *_rest) in circuits:
            for workload in ("equiv", "nonequiv"):
                r = cells.get((name, workload, "qcec"))
                if r is None:
                    continue
                if r["status"] != "ok":
                    out.append(f"| `{name}` | {workload} | {status_label(r)} | — | — | — |")
                    continue
                out.append(f"| `{name}` | {workload} | {r['verdict']} | {status_label(r)} | "
                           f"{median_list_ms(r['qcec_check_seconds'])} | "
                           f"{median_list_ms(r['qcec_preprocessing_seconds'])} |")
    return out


def render(env: dict, rows: list[dict]) -> str:
    protocol = env["protocol"]
    backends = protocol["backends"]
    cells = {(r["circuit"], r.get("workload"), r.get("backend")): r for r in rows}
    circuits = sorted({(SPLIT_ORDER[r["split"]], r["circuit"], r["split"], r["width"], r["gates"])
                       for r in rows})
    unsupported = [r for r in rows if r["status"] == "unsupported"]
    out = [
        "# Benchmark report",
        "",
        (f"- symq commit `{env['symq_commit']}` (dirty: {env['symq_dirty']}), started "
        f"{env['started_utc']}"),
        f"- {env['implementation']} {env['python'].split()[0]} on {env['platform']}",
        (f"- CPU: {env['cpu_model']} ({env['cpu_affinity']} usable of {env['cpu_count']}), "
        f"RAM {env['mem_total_kib'] / 1048576:.1f} GiB"),
        (f"- Corpus: {env['corpus_source']['repository']} @ `{env['corpus_source']['commit']}`, "
        f"manifest sha256 `{env['corpus_manifest_sha256'][:16]}…`"),
        (f"- Protocol: {protocol['warmup']} warmup + median of {protocol['repetitions']} timed "
        f"runs per cell; {protocol['timing']}; {protocol['memory']}; {protocol['isolation']}; "
        f"per-run budget {protocol['run_timeout_seconds']} s."),
        ("- Times are milliseconds. Sub-millisecond medians are sensitive to scheduling, GC and "
        "CPU frequency; no confidence interval is claimed."),
        "",
        "## Correctness checks",
        "",
    ]
    problems = []
    for (_, name, *_rest) in circuits:
        for workload in protocol["workloads"]:
            prints = {cells[(name, workload, b)]["fingerprint"] for b in backends
                      if cells.get((name, workload, b), {}).get("status") == "ok"
                      and cells[(name, workload, b)].get("fingerprint") is not None}
            if len(prints) > 1:
                problems.append(f"- DISAGREEMENT on {name}/{workload}: {len(prints)} distinct results")
    for r in rows:
        if r["status"] in ("wrong_verdict", "error"):
            problems.append(f"- {r['status']}: {r['circuit']}/{r['workload']}/{r['backend']}")
    out += problems or [("- All backends that completed a cell produced identical output "
                        "polynomials (simulate) or verdicts and differing output (equiv/nonequiv)."
                        " No wrong verdict, no worker error.")]
    if "qcec" in backends:
        out.append("- `qcec` gives verdicts only; they are checked against the expected verdict "
                   "(`wrong_verdict` otherwise), not against output polynomials.")
    counts = Counter((r.get("backend"), r["status"] if r["status"] != "resource_limit"
                      else f"refused:{r['resource']}") for r in rows if r.get("backend"))
    out += ["", "| backend | " + " | ".join(sorted({s for _, s in counts})) + " |",
            "|---|" + "---:|" * len({s for _, s in counts})]
    for b in backends:
        out.append(f"| `{b}` | " + " | ".join(str(counts.get((b, s), 0))
                                              for s in sorted({s for _, s in counts})) + " |")
    if unsupported:
        out += ["", "Rejected before benchmarking (outside the X/CX/CCX/MCX model):"]
        out += [f"- `{r['circuit']}`: {r['reason']}" for r in unsupported]

    for workload in protocol["workloads"]:
        out += ["", f"## Workload `{workload}` — median ms", "",
                "| circuit | split | width | gates | " + " | ".join(f"`{b}`" for b in backends)
                + " |", "|---|---|---:|---:|" + "---:|" * len(backends)]
        for (_, name, split, width, gates) in circuits:
            if (name, workload, backends[0]) not in cells:
                continue
            out.append(f"| `{name}` | {split} | {width} | {gates} | "
                       + " | ".join(status_label(cells.get((name, workload, b))) for b in backends)
                       + " |")
        out += ["", (f"Paired speedup of each backend over `{BASELINE}` (per-circuit ratio of "
                f"medians, >1 is faster), `{OUTLIER}` reported separately:"), "",
                "| backend | split | without " + OUTLIER + f" | {OUTLIER} |", "|---|---|---|---:|"]
        for b in backends:
            if b == BASELINE:
                continue
            for split in ("dev", "holdout", "extension"):
                ratios, outlier = [], "—"
                for (_, name, s, *_rest) in circuits:
                    if s != split:
                        continue
                    base = cells.get((name, workload, BASELINE))
                    other = cells.get((name, workload, b))
                    if base is None or other is None:
                        continue
                    if median_ms(base) is None or median_ms(other) is None:
                        continue
                    ratio = median_ms(base) / median_ms(other)
                    if name == OUTLIER:
                        outlier = f"{ratio:.1f}×"
                    else:
                        ratios.append(ratio)
                if ratios or outlier != "—":
                    out.append(f"| `{b}` | {split} | {summarize(ratios)} | {outlier} |")

    out += ["", "## Memory and representation changes (`simulate`)", "",
            ("tracemalloc peak in KiB (separate untimed run); worker peak RSS in MiB, which "
            "includes the interpreter."), "",
            "| circuit | " + " | ".join(f"`{b}` KiB" for b in backends) + " | max RSS MiB |",
            "|---|" + "---:|" * (len(backends) + 1)]
    for (_, name, *_rest) in circuits:
        sim = [cells.get((name, "simulate", b)) for b in backends]
        if all(r is None for r in sim):
            continue
        rss = max((r["maxrss_kib"] for r in sim if r and r["status"] == "ok"), default=0) / 1024
        out.append(f"| `{name}` | " + " | ".join(
            f"{r['tracemalloc_peak_bytes'] / 1024:.0f}" if r and r["status"] == "ok" else "—"
            for r in sim) + f" | {rss:.0f} |")
    out += ["", ("| circuit | `zdd` nodes | `auto-zdd` switch gate | `auto-zdd` conversions | "
            "`adaptive-wire` conversions | `packed-fallback` conversions |"),
            "|---|---:|---:|---:|---:|---:|"]
    for (_, name, *_rest) in circuits:
        def get(b, key, sub=None, name=name):
            r = cells.get((name, "simulate", b))
            if not r or r["status"] != "ok":
                return "—"
            value = r.get(key) if sub is None else r.get(key, {}).get(sub)
            return "none" if value is None else str(value)
        if (name, "simulate", "zdd") in cells:
            out.append(f"| `{name}` | {get('zdd', 'zdd_nodes')} | {get('auto-zdd', 'switch_gate')}"
                       f" | {get('auto-zdd', 'stats', 'conversions')} | "
                       f"{get('adaptive-wire', 'stats', 'conversions')} | "
                       f"{get('packed-fallback', 'stats', 'conversions')} |")

    out += native_section(env, backends, cells, circuits)

    historical = json.loads(HISTORICAL.read_text())
    mapping = historical["backend_mapping"]
    out += ["", "## Comparison with the historical handoff (`simulate`)", "",
            (f"Source: {historical['source']}. {historical['status']}. Different machine and "
            "different (reconstructed) code: compare speedup ratios, not absolute times."), "",
            "| circuit | " + " | ".join(f"{k} hist / `{v}` here (ms)" for k, v in mapping.items())
            + " | auto_zdd speedup hist | here |", "|---|" + "---|" * (len(mapping) + 2)]
    for name, values in historical["simulate"].items():
        ours = {v: cells.get((name, "simulate", v)) for v in mapping.values()}
        line = [f"`{name}`"]
        for k, v in mapping.items():
            here = median_ms(ours[v]) if ours[v] else None
            line.append(f"{values[k]:.3g} / {fmt_ms(here) if here else '—'}")
        hist_ratio = values["copy_set"] / values["auto_zdd"]
        base, auto = (median_ms(ours[mapping["copy_set"]]) if ours[mapping["copy_set"]] else None,
                      median_ms(ours[mapping["auto_zdd"]]) if ours[mapping["auto_zdd"]] else None)
        line += [f"{hist_ratio:.2f}×", f"{base / auto:.2f}×" if base and auto else "—"]
        out.append("| " + " | ".join(line) + " |")
    out.append("")
    return "\n".join(out)


def seal(directory: Path) -> None:
    lines = []
    for path in sorted(p for p in directory.iterdir() if p.name != "SHA256SUMS"):
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    (directory / "SHA256SUMS").write_text("\n".join(lines) + "\n")
    for path in directory.iterdir():
        path.chmod(0o444)


def write_report(directory: Path) -> Path:
    if (directory / "SHA256SUMS").exists():
        raise SystemExit(f"{directory} is sealed; result directories are immutable")
    env, rows = load(directory)
    report = directory / "REPORT.md"
    report.write_text(render(env, rows))
    seal(directory)
    return report


if __name__ == "__main__":
    print(write_report(Path(sys.argv[1])))
