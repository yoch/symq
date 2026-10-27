"""Generate every table, figure and number of the paper from sealed result directories.

Nothing in ``paper/tables`` or ``paper/figures`` is edited by hand: this script reads the
``summary.json`` and ``results.jsonl`` of the sealed runs listed in ``RUNS``, checks them
against their ``SHA256SUMS``, and writes LaTeX fragments plus ``numbers.tex`` (macros used in
the text). Usage: python paper/tools/make_tables.py
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "benchmarks" / "results"
PAPER = ROOT / "paper"
RUNS = {
    "qcec": "20261027T150621Z_23469829a0dc_matched-qcec",
    "blind": "20261027T150621Z_23469829a0dc_matched-blind",
}
ORDER_RUNS = {
    "qcec": "20261027T153026Z_e71c7e0fc8a2_variable-order-qcec",
    "blind": "20261027T153137Z_e71c7e0fc8a2_variable-order-blind",
}
CORPUS_LABEL = {"qcec": "QCEC (19 circuits)", "blind": "blind (30 circuits)"}
WORKLOADS = ("simulate", "equiv", "nonequiv")
MODE_LABEL = {
    "zdd-native/fused": "symq native, fused C loop",
    "zdd-native/loop": "symq native, minimal loop",
    "zdd-native/loop-sorted": "symq native, minimal loop, sorted",
    "zdd-native/algebra": "symq native, \\texttt{Algebra} driver",
    "zdd-python/algebra": "symq Python ZDD, \\texttt{Algebra} driver",
    "polybori/loop": "PolyBoRi, minimal loop",
    "polybori/loop-sorted": "PolyBoRi, minimal loop, sorted",
    "polybori/algebra": "PolyBoRi, \\texttt{Algebra} driver",
    "polybori/best": "PolyBoRi, best of its three drivers",
    "cudd-bdd/loop": "CUDD BDD, minimal loop (reordering)",
    "cudd-bdd-static/loop": "CUDD BDD, minimal loop (static order)",
    "sparse/algebra": "symq sparse ANF (Python)",
    "qcec": "MQT QCEC (alternating checker)",
}
SHORT = {
    "zdd-native/fused": "nat-fused",
    "zdd-native/loop": "nat-loop",
    "zdd-native/loop-sorted": "nat-sorted",
    "zdd-native/algebra": "nat-alg",
    "zdd-python/algebra": "py-alg",
    "polybori/loop": "pb-loop",
    "polybori/loop-sorted": "pb-sorted",
    "polybori/algebra": "pb-alg",
    "polybori/best": "pb-best",
    "cudd-bdd/loop": "bdd-loop",
    "cudd-bdd-static/loop": "bdd-static",
    "sparse/algebra": "sparse",
    "qcec": "qcec",
}


def verified(run: str) -> Path | None:
    target = RESULTS / run
    sums = target / "SHA256SUMS"
    if not sums.is_file():
        return None
    for line in sums.read_text().splitlines():
        digest, name = line.split("  ", 1)
        actual = hashlib.sha256((target / name).read_bytes()).hexdigest()
        if actual != digest:
            raise SystemExit(f"{run}/{name}: SHA-256 mismatch, refusing to build tables")
    return target


def load(run: str) -> tuple[dict | None, list[dict]]:
    target = verified(run)
    if target is None:
        return None, []
    summary = json.loads((target / "summary.json").read_text())
    rows = [json.loads(line) for line in (target / "results.jsonl").read_text().splitlines()]
    return summary, rows


def find(summary: dict, candidate: str, baseline: str, workload: str, phase: str) -> dict:
    for item in summary["comparisons"]:
        if (item["candidate"], item["baseline"], item["workload"], item["phase"]) == (
                candidate, baseline, workload, phase):
            return item
    raise KeyError((candidate, baseline, workload, phase))


def cell(item: dict, total: int) -> str:
    if item["n"] == 0:
        return "---"
    low, high = item["ci95"]
    return (f"{item['geomean']:.2f} [{low:.2f}, {high:.2f}]"
            f"\\,{{\\scriptsize({item['wins']}/{item['n']}"
            + (f"; {total - item['n']} n/c" if item["n"] < total else "") + ")}")


def comparison_table(summaries: dict, pairs: list[tuple[str, str]], phase: str, name: str,
                     caption: str, label: str) -> None:
    legend = "; ".join(f"\\textsf{{{SHORT[m]}}}: {MODE_LABEL[m]}"
                       for m in dict.fromkeys(m for pair in pairs for m in pair))
    lines = [
        "\\begin{table}[t]", "\\centering\\footnotesize",
        f"\\caption{{{caption} Modes: {legend}.}}",
        f"\\label{{{label}}}", "\\begin{tabular}{llll}", "\\toprule",
        "candidate / baseline & simulate & equiv & nonequiv \\\\",
    ]
    for corpus, summary in summaries.items():
        lines += ["\\midrule", f"\\multicolumn{{4}}{{l}}{{\\emph{{{CORPUS_LABEL[corpus]}}}}} \\\\"]
        if summary is None:
            lines.append("\\multicolumn{4}{l}{run not available} \\\\")
            continue
        total = len(summary["circuits"])
        for candidate, baseline in pairs:
            cells = []
            for workload in WORKLOADS:
                try:
                    cells.append(cell(find(summary, candidate, baseline, workload, phase), total))
                except KeyError:
                    cells.append("n/a")
            lines.append(f"\\textsf{{{SHORT[candidate]}}} / \\textsf{{{SHORT[baseline]}}} & "
                         + " & ".join(cells) + " \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    (PAPER / "tables" / name).write_text("\n".join(lines) + "\n")


def medians(rows: list[dict], mode: str, workload: str, key: str, warm: bool = False):
    out = {}
    for row in rows:
        if row["mode"] == mode and row["workload"] == workload and row.get("status") == "ok":
            values = (row.get("warm_phases" if warm else "phases") or {}).get(key)
            if values:
                out[row["circuit"]] = statistics.median(values)
    return out


def paired(rows: list[dict], candidate: str, baseline: str, workload: str) -> dict | None:
    """Paired ratio baseline/candidate of cold compute medians, recomputed from raw rows."""
    a = medians(rows, candidate, workload, "compute")
    b = medians(rows, baseline, workload, "compute")
    common = sorted(set(a) & set(b))
    if not common:
        return None
    logs = [math.log(b[c] / a[c]) for c in common]
    rng = random.Random(20261027)
    boot = sorted(statistics.fmean(rng.choices(logs, k=len(logs))) for _ in range(10_000))
    return {"geomean": math.exp(statistics.fmean(logs)), "n": len(common),
            "wins": sum(x > 0 for x in logs),
            "ci95": (math.exp(boot[249]), math.exp(boot[9749]))}


def status_table(summaries: dict, rows_by: dict) -> None:
    modes = ["zdd-native/fused", "zdd-native/loop", "polybori/loop", "polybori/algebra",
             "cudd-bdd/loop", "cudd-bdd-static/loop", "zdd-python/algebra", "sparse/algebra",
             "qcec"]
    lines = ["\\begin{table}[t]", "\\centering\\small",
             ("\\caption{Completion on the blind corpus (90 cells per mode: 30 circuits $\\times$ "
             "3 workloads; QCEC has no \\emph{simulate}). \\emph{censored}: not run because a "
             "smaller circuit of the same family timed out (120\\,s).}"),
             "\\label{tab:status}", "\\begin{tabular}{lrrrr}", "\\toprule",
             "mode & ok & timeout & censored & error \\\\", "\\midrule"]
    rows = rows_by.get("blind") or []
    if not rows:
        lines.append("\\multicolumn{5}{l}{run not available} \\\\")
    for mode in modes:
        counts = {}
        for row in rows:
            if row["mode"] == mode:
                counts[row["status"]] = counts.get(row["status"], 0) + 1
        if rows:
            lines.append(f"{MODE_LABEL[mode]} & {counts.get('ok', 0)} & "
                         f"{counts.get('timeout', 0)} & {counts.get('timeout_censored', 0)} & "
                         f"{counts.get('error', 0) + counts.get('wrong_verdict', 0)} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    (PAPER / "tables" / "tab_status.tex").write_text("\n".join(lines) + "\n")


def family_table(summary: dict | None) -> None:
    lines = ["\\begin{table}[t]", "\\centering\\small",
             ("\\caption{Blind corpus by family, \\emph{simulate}, cold compute phase: geometric "
             "mean of the paired ratio (completed by both / circuits in the family). Last "
             "column: circuits completed by the native minimal loop but not PolyBoRi, by "
             "PolyBoRi but not the native loop, and by CUDD but not the native loop.}"),
             "\\label{tab:families}", "\\begin{tabular}{lrrr}", "\\toprule",
             ("family & vs.\\ \\textsf{pb-loop} & vs.\\ \\textsf{bdd-loop} & "
              "nat$\\setminus$pb / pb$\\setminus$nat / bdd$\\setminus$nat \\\\"),
             "\\midrule"]
    if summary is None:
        lines.append("\\multicolumn{4}{l}{run not available} \\\\")
    else:
        pb = find(summary, "zdd-native/loop", "polybori/loop", "simulate", "compute")
        bdd = find(summary, "zdd-native/loop", "cudd-bdd/loop", "simulate", "compute")
        for name in summary["families"]:
            a, b = pb["by_family"][name], bdd["by_family"][name]
            size = sum(1 for c in summary["circuits"] if c.split("_", 1)[0] == name)

            def g(part):
                return f"{part['geomean']:.2f}" if part.get("n") else "---"
            lines.append(f"\\texttt{{{name}}} & {g(a)} ({a['n']}/{size}) & {g(b)} "
                         f"({b['n']}/{size}) & {a['only_candidate']} / {a['only_baseline']} / "
                         f"{b['only_baseline']} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    (PAPER / "tables" / "tab_families.tex").write_text("\n".join(lines) + "\n")


def setup_table(rows_by: dict) -> None:
    lines = ["\\begin{table}[t]", "\\centering\\small",
             ("\\caption{Fixed and conversion costs, QCEC corpus, \\emph{simulate} (median over "
             "circuits of the per-circuit medians, milliseconds). Setup: manager and variables "
             "(PolyBoRi: a fresh ring). Extraction: explicit monomials of all outputs.}"),
             "\\label{tab:setup}", "\\begin{tabular}{lrrr}", "\\toprule",
             "mode & setup & compute & extraction \\\\", "\\midrule"]
    rows = rows_by.get("qcec") or []
    for mode in ("zdd-native/fused", "zdd-native/loop", "polybori/loop", "cudd-bdd/loop",
                 "zdd-python/algebra", "sparse/algebra"):
        setup = medians(rows, mode, "simulate", "setup")
        compute = medians(rows, mode, "simulate", "compute")
        extract = {r["circuit"]: r["extract_seconds"] for r in rows
                   if r["mode"] == mode and r["workload"] == "simulate"
                   and r.get("status") == "ok" and r.get("extract_seconds") is not None}
        if not setup:
            continue
        lines.append(f"{MODE_LABEL[mode]} & {1e3 * statistics.median(setup.values()):.3f} & "
                     f"{1e3 * statistics.median(compute.values()):.3f} & "
                     f"{1e3 * statistics.median(extract.values()):.3f} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    (PAPER / "tables" / "tab_setup.tex").write_text("\n".join(lines) + "\n")


def order_table(macros: dict) -> None:
    lines = ["\\begin{table}[t]", "\\centering\\footnotesize",
             ("\\caption{Variable-order sensitivity of the native engine (\\emph{simulate}, "
              "fused loop, cold): identity, reversed and five seeded random orders per circuit. "
              "Node spread: largest over smallest number of ZDD nodes across the orders of one "
              "circuit. Fingerprints: hashes of the explicit output monomials, which must not "
              "depend on the order.}"),
             "\\label{tab:order}", "\\begin{tabular}{lrrrrr}", "\\toprule",
             "corpus & complete & equal & node spread & identity/best & identity \\\\",
             " & orders & fingerprints & geo.\\ / max & time (geo.) & best \\\\", "\\midrule"]
    for corpus, run in ORDER_RUNS.items():
        tag = {"qcec": "Q", "blind": "B"}[corpus]
        target = verified(run) if run else None
        if target is None:
            lines.append(f"{CORPUS_LABEL[corpus]} & \\multicolumn{{5}}{{l}}{{run not "
                         "available} \\\\")
            continue
        summary = json.loads((target / "summary.json").read_text())
        rows = [json.loads(line) for line in (target / "results.jsonl").read_text().splitlines()]
        circuits = summary["circuits"]
        complete = [c for c in circuits.values() if c["completed_orders"] == c["orders"]]
        time_ratio = statistics.geometric_mean([c["identity_over_best_time"] for c in complete])
        identity_best = sum(c["best_order"] == "identity" for c in complete)
        worst = max(complete, key=lambda c: c["node_spread"])
        worst_name = next(n for n, c in circuits.items() if c is worst).replace("_", "\\_")
        statuses = {}
        for row in rows:
            statuses[row["status"]] = statuses.get(row["status"], 0) + 1
        macros[f"{tag}OrderCells"] = str(len(rows))
        macros[f"{tag}OrderOk"] = str(statuses.get("ok", 0))
        macros[f"{tag}OrderComplete"] = str(len(complete))
        macros[f"{tag}OrderCircuits"] = str(len(circuits))
        macros[f"{tag}OrderCompared"] = str(summary["fingerprints_compared"])
        macros[f"{tag}OrderDisagree"] = str(len(summary["fingerprint_disagreements"]))
        macros[f"{tag}OrderSpreadGeo"] = f"{summary['node_spread_geomean']:.2f}"
        macros[f"{tag}OrderSpreadMax"] = f"{summary['node_spread_max']:.0f}"
        macros[f"{tag}OrderSpreadMaxCircuit"] = worst_name
        macros[f"{tag}OrderIdTimeGeo"] = f"{time_ratio:.2f}"
        macros[f"{tag}OrderIdTimeWorst"] = f"{worst['identity_over_best_time']:.1f}"
        macros[f"{tag}OrderIdBest"] = str(identity_best)
        macros[f"{tag}OrderCommit"] = run.split("_")[1]
        rescued = [n for n in circuits
                   if any(r["circuit"] == n and r["order"] == "identity" and r["status"] != "ok"
                          for r in rows)
                   and any(r["circuit"] == n and r["status"] == "ok" for r in rows)]
        macros[f"{tag}OrderRescued"] = str(len(rescued))
        macros[f"{tag}OrderRescuedList"] = ", ".join(
            f"\\texttt{{{n.replace('_', '{\\_}')}}}" for n in rescued) or "none"
        macros[f"{tag}OrderNone"] = str(sum(1 for c in circuits.values()
                                            if c["completed_orders"] == 0))
        lines.append(
            f"{CORPUS_LABEL[corpus]} & {len(complete)}/{len(circuits)} & "
            f"{summary['fingerprints_compared'] - len(summary['fingerprint_disagreements'])}/"
            f"{summary['fingerprints_compared']} & {summary['node_spread_geomean']:.2f} / "
            f"{summary['node_spread_max']:.0f} (\\texttt{{{worst_name}}}) & "
            f"{time_ratio:.2f} & {identity_best}/{len(complete)} \\\\")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}"]
    (PAPER / "tables" / "tab_order.tex").write_text("\n".join(lines) + "\n")


def scatter(rows_by: dict) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.0, 3.2), constrained_layout=True)
    for axis, baseline, title in ((axes[0], "polybori/loop", "PolyBoRi"),
                                  (axes[1], "cudd-bdd/loop", "CUDD BDD")):
        lo, hi = math.inf, 0.0
        for corpus, marker in (("qcec", "o"), ("blind", "^")):
            rows = rows_by.get(corpus) or []
            for workload, color in (("simulate", "tab:blue"), ("equiv", "tab:orange"),
                                    ("nonequiv", "tab:green")):
                a = medians(rows, "zdd-native/loop", workload, "compute")
                b = medians(rows, baseline, workload, "compute")
                common = sorted(set(a) & set(b))
                if not common:
                    continue
                xs = [1e3 * b[c] for c in common]
                ys = [1e3 * a[c] for c in common]
                lo, hi = min(lo, *xs, *ys), max(hi, *xs, *ys)
                axis.scatter(xs, ys, s=12, marker=marker, color=color, alpha=0.75,
                             label=f"{corpus}/{workload}")
        if hi > 0:
            axis.plot([lo, hi], [lo, hi], color="black", linewidth=0.6)
            axis.plot([lo, hi], [lo / 4, hi / 4], color="grey", linewidth=0.5, linestyle=":")
        axis.set_xscale("log")
        axis.set_yscale("log")
        axis.set_xlabel(f"{title}, minimal loop (ms)")
        axis.set_ylabel("symq native, minimal loop (ms)")
        axis.set_title(f"cold compute: symq vs {title}", fontsize=9)
    axes[0].legend(fontsize=6, loc="upper left")
    fig.savefig(PAPER / "figures" / "scatter_matched.pdf")
    plt.close(fig)


def numbers(summaries: dict, rows_by: dict) -> None:
    macros = {}

    def put(name: str, value: str) -> None:
        macros[name] = value

    for corpus, summary in summaries.items():
        tag = {"qcec": "Q", "blind": "B"}[corpus]
        if summary is None:
            continue
        put(f"N{tag}Circuits", str(len(summary["circuits"])))
        c = summary["correctness"]
        put(f"{tag}Groups", str(c["groups_checked"]))
        put(f"{tag}Disagree", str(len(c["fingerprint_disagreements"])))
        put(f"{tag}Wrong", str(len(c["wrong_verdicts"])))
        put(f"{tag}BadWitness", str(len(c["invalid_witnesses"])))
        put(f"{tag}Commit", summary["environment"]["symq_commit"][:12])
        for key, (candidate, baseline) in {
            "PB": ("zdd-native/loop", "polybori/loop"),
            "PBFused": ("zdd-native/fused", "polybori/best"),
            "BDD": ("zdd-native/loop", "cudd-bdd/loop"),
            "Fusion": ("zdd-native/fused", "zdd-native/loop-sorted"),
            "Sorting": ("zdd-native/loop-sorted", "zdd-native/loop"),
            "Driver": ("zdd-native/loop", "zdd-native/algebra"),
            "Core": ("zdd-native/algebra", "zdd-python/algebra"),
            "QCEC": ("zdd-native/fused", "qcec"),
        }.items():
            for workload in WORKLOADS:
                for phase, suffix in (("compute", ""), ("warm:compute", "Warm")):
                    try:
                        item = find(summary, candidate, baseline, workload, phase)
                    except KeyError:
                        continue
                    if not item["n"]:
                        continue
                    w = {"simulate": "Sim", "equiv": "Eq", "nonequiv": "Neq"}[workload]
                    put(f"{tag}{key}{w}{suffix}", f"{item['geomean']:.2f}")
                    put(f"{tag}{key}{w}{suffix}Lo", f"{item['ci95'][0]:.2f}")
                    put(f"{tag}{key}{w}{suffix}Hi", f"{item['ci95'][1]:.2f}")
                    put(f"{tag}{key}{w}{suffix}N", str(item["n"]))
                    put(f"{tag}{key}{w}{suffix}Wins", str(item["wins"]))
                    put(f"{tag}{key}{w}{suffix}Min", f"{item['min']:.2f}")
                    put(f"{tag}{key}{w}{suffix}Max", f"{item['max']:.2f}")
    for corpus, tag in (("qcec", "Q"), ("blind", "B")):
        for workload in WORKLOADS:
            item = paired(rows_by.get(corpus) or [], "zdd-native/fused", "zdd-native/loop",
                          workload)
            if item is None:
                continue
            w = {"simulate": "Sim", "equiv": "Eq", "nonequiv": "Neq"}[workload]
            put(f"{tag}FusedVsLoop{w}", f"{item['geomean']:.2f}")
            put(f"{tag}FusedVsLoop{w}Lo", f"{item['ci95'][0]:.2f}")
            put(f"{tag}FusedVsLoop{w}Hi", f"{item['ci95'][1]:.2f}")
            put(f"{tag}FusedVsLoop{w}Wins", str(item["wins"]))
            put(f"{tag}FusedVsLoop{w}N", str(item["n"]))
    for mode, key in (("zdd-native/fused", "NativeFused"), ("zdd-native/loop", "NativeLoop"),
                      ("polybori/loop", "PBLoop"), ("cudd-bdd/loop", "BDDLoop"),
                      ("qcec", "QCEC")):
        for corpus, tag in (("qcec", "Q"), ("blind", "B")):
            selected = [r for r in rows_by.get(corpus) or [] if r["mode"] == mode]
            if not selected:
                continue
            put(f"{tag}{key}Cells", str(len(selected)))
            put(f"{tag}{key}Ok", str(sum(r["status"] == "ok" for r in selected)))
            put(f"{tag}{key}Unfinished",
                str(sum(r["status"] in ("timeout", "timeout_censored") for r in selected)))
    for corpus, tag in (("qcec", "Q"), ("blind", "B")):
        terms = [r["output_terms"] for r in rows_by.get(corpus) or []
                 if r["mode"].startswith("zdd-native") and r.get("output_terms") is not None]
        if terms:
            put(f"{tag}MaxTerms", f"{max(terms):,}".replace(",", "\\,"))
    rows = rows_by.get("qcec") or []
    for mode, name in (("polybori/loop", "SetupPB"), ("zdd-native/loop", "SetupNative"),
                       ("cudd-bdd/loop", "SetupBDD")):
        values = medians(rows, mode, "simulate", "setup")
        if values:
            put(name, f"{1e3 * statistics.median(values.values()):.3f}")
    order_table(macros)
    lines = ["% Generated by paper/tools/make_tables.py from sealed results; do not edit.",
             "\\newif\\ifblindrun",
             "\\blindruntrue" if summaries.get("blind") else "\\blindrunfalse"]
    for name, value in sorted(macros.items()):
        safe = name.translate(str.maketrans("0123456789", "ABCDEFGHIJ"))
        lines.append(f"\\newcommand{{\\{safe}}}{{{value}}}")
    (PAPER / "tables" / "numbers.tex").write_text("\n".join(lines) + "\n")


def main() -> int:
    loaded = {corpus: load(run) for corpus, run in RUNS.items()}
    summaries = {corpus: data[0] for corpus, data in loaded.items()}
    rows_by = {corpus: data[1] for corpus, data in loaded.items()}
    (PAPER / "tables").mkdir(exist_ok=True)
    (PAPER / "figures").mkdir(exist_ok=True)
    comparison_table(
        summaries,
        [("zdd-native/loop", "polybori/loop"), ("zdd-native/loop-sorted", "polybori/loop-sorted"),
         ("zdd-native/fused", "polybori/best"), ("zdd-native/loop", "cudd-bdd/loop"),
         ("zdd-native/loop", "cudd-bdd-static/loop")],
        "compute", "tab_matched.tex",
        "Matched drivers, cold caches, compute phase. Geometric mean of the paired ratio "
        "baseline/candidate ($>1$: symq faster) with a 95\\% bootstrap interval; in "
        "parentheses, wins/circuits completed by both, and circuits not completed (n/c) by at "
        "least one side.", "tab:matched")
    comparison_table(
        summaries,
        [("zdd-native/loop", "polybori/loop"), ("zdd-native/fused", "polybori/best"),
         ("zdd-native/loop", "cudd-bdd/loop")],
        "warm:compute", "tab_matched_warm.tex",
        "Same comparison with warm caches: one manager reused across runs after a filling "
        "run (re-verification of the same circuit).", "tab:warm")
    comparison_table(
        summaries,
        [("zdd-native/algebra", "zdd-python/algebra"), ("zdd-native/loop", "zdd-native/algebra"),
         ("zdd-native/loop-sorted", "zdd-native/loop"),
         ("zdd-native/fused", "zdd-native/loop-sorted"),
         ("zdd-native/fused", "zdd-python/algebra")],
        "compute", "tab_ablation.tex",
        "Ablation of the native engine (cold compute phase). Each row changes one thing: the "
        "engine (C instead of Python, same driver), the driver (minimal loop instead of "
        "symq's \\texttt{Algebra} layer), factor sorting, and fusing the loop in C. Ratios "
        "below 1 are slowdowns.", "tab:ablation")
    comparison_table(
        summaries, [("zdd-native/fused", "qcec")], "compute", "tab_qcec.tex",
        "symq native (both simulations and the comparison) against MQT QCEC's alternating "
        "decision-diagram checker on pre-built circuits. QCEC answers unitary equality and "
        "builds no polynomial; \\emph{simulate} does not apply.", "tab:qcec")
    status_table(summaries, rows_by)
    family_table(summaries.get("blind"))
    setup_table(rows_by)
    scatter(rows_by)
    numbers(summaries, rows_by)
    print("tables and figures written; runs:",
          {c: (s or {}).get("environment", {}).get("symq_commit") for c, s in summaries.items()})
    return 0


if __name__ == "__main__":
    sys.exit(main())
