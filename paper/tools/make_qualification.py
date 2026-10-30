"""Derive current qualification tables/figures from the unmodified v1 raw artifact.

Run after the protocol has been executed and sealed. Historical E1--E5 files are
not read, merged, overwritten or relabeled by this generator.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import random
import re
import statistics
from collections import Counter, defaultdict
from pathlib import Path

PAPER = Path(__file__).resolve().parents[1]
GOOD = {"ok"}
TASKS = ("simulate", "anf_export", "equivalence", "counterexample")
STATUS = ("ok", "timeout", "oom", "unsupported", "not_run", "inconclusive", "killed", "error")
PUBLIC = "public_api_end_to_end"
CASE_CLASSES = {"fresh_stochastic_holdout", "development_calibration", "fresh_adverse_holdout"}
HOLDOUT_CLASSES = CASE_CLASSES - {"development_calibration"}


def tex(value):
    substitutions = {"\\": r"\textbackslash{}", "_": r"\_", "&": r"\&", "%": r"\%",
                     "#": r"\#", "{": r"\{", "}": r"\}", "$": r"\$"}
    return "".join(substitutions.get(c, c) for c in str(value))


def geometric(values):
    return math.exp(statistics.mean(math.log(v) for v in values)) if values else None


def read_artifact(source):
    """Hash the published artifact and decode its original, unmodified JSON bytes."""
    artifact = source.read_bytes()
    raw = gzip.decompress(artifact) if source.suffix == ".gz" else artifact
    return raw, hashlib.sha256(artifact).hexdigest()


def validate_classification(data, classification):
    """Bind the separate adjudication to measured identities without editing raw labels."""
    if classification.get("schema") != "symq/case-classification/v1":
        raise ValueError("unrecognized case classification")
    if classification.get("measured_source_commit") != data["source"]["commit"]:
        raise ValueError("classification source differs from measured source")
    if classification.get("raw_manifest_sha256") != data["manifest_sha256"]:
        raise ValueError("classification manifest differs from measured manifest")
    mapping = classification.get("classification", {})
    cases = {case["id"]: case for case in data["cases"]}
    row_cases = {row["case_id"] for row in data["rows"]}
    if set(mapping) != set(cases) or row_cases != set(cases):
        raise ValueError("classification must cover exactly all planned and recorded cases")
    for case_id, item in mapping.items():
        if item.get("classification") not in CASE_CLASSES or not item.get("reason"):
            raise ValueError("unknown or unexplained adjudicated case classification")
        if item.get("raw_split") != cases[case_id]["split"]:
            raise ValueError("classification does not preserve the raw case split")
    for row in data["rows"]:
        if row["split"] != mapping[row["case_id"]]["raw_split"]:
            raise ValueError("classification does not preserve a raw trial split")
    return mapping


def holdout_sensitivity(data, classification):
    mapping = validate_classification(data, classification)
    # A post-audit sensitivity, not a replacement of the preregistered mixed study.
    rows = [row for row in data["rows"]
            if mapping[row["case_id"]]["classification"] in HOLDOUT_CLASSES]
    return summarise({"rows": rows})


def summarise(data):
    """Independent derivation: paired repeats -> case effects -> equal-family effects."""
    rows = data["rows"]
    if not isinstance(rows, list):
        raise TypeError("raw rows must be an array")
    seen = set()
    for row in rows:
        key = tuple(row[k] for k in ("case_id", "task", "boundary", "backend", "repetition"))
        if key in seen:
            raise ValueError(f"duplicate raw trial {key}")
        seen.add(key)
        if row["task"] not in TASKS:
            raise ValueError("unrecognized task")
        if row["status"] not in STATUS:
            raise ValueError("unrecognized trial status")
        if row["status"] in GOOD:
            value = row["service_seconds"]
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError("completed service time is missing or invalid")
            if row.get("source_hash_checked") is not True:
                raise ValueError("completed trial has no successful source pin check")
            if row["task"] == "anf_export" and row.get("exported") is not True:
                raise ValueError("ANF export success without exported output")
            if row["task"] == "counterexample" and row.get("witness_checked") is not True:
                raise ValueError("counterexample success without concrete replay")
    coverage = []
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["task"], row["boundary"], row["backend"], row["family"])].append(row)
    for key, group in sorted(grouped.items()):
        counts = Counter("ok" if r["status"] in GOOD else r["status"] for r in group)
        coverage.append(dict(zip(("task", "boundary", "backend", "family"), key),
                             trials=len(group), cases=len({r["case_id"] for r in group}),
                             statuses=dict(sorted(counts.items())),
                             service_completed=sum(r.get("service_completed") is True for r in group),
                             validation_outcomes=dict(Counter(r.get("validation_status", "not_run") for r in group)),
                             oracle_checked=sum(r.get("oracle_checked") is True for r in group),
                             witness_checked=sum(r.get("witness_checked") is True for r in group)))
    effects = []
    by_task = defaultdict(list)
    for row in rows:
        by_task[(row["task"], row["boundary"])].append(row)
    for (task, boundary), group in sorted(by_task.items()):
        backends = sorted({r["backend"] for r in group})
        candidates = [b for b in ("zdd-native-fused", "zdd-native") if b in backends]
        if not candidates:
            continue
        for candidate in candidates:
            for baseline in backends:
                if baseline == candidate:
                    continue
                native = {(r["case_id"], r["repetition"]): r for r in group
                          if r["backend"] == candidate}
                other = {(r["case_id"], r["repetition"]): r for r in group
                         if r["backend"] == baseline}
                per_case = defaultdict(list)
                families = {}
                for key in native.keys() & other.keys():
                    a, b = native[key], other[key]
                    if (a["status"] in GOOD and b["status"] in GOOD
                            and a.get("oracle_checked") is True and b.get("oracle_checked") is True
                            and a["service_seconds"] > 0 and b["service_seconds"] > 0):
                        per_case[key[0]].append(b["service_seconds"] / a["service_seconds"])
                        families[key[0]] = a["family"]
                family_cases = defaultdict(list)
                for case, ratios in per_case.items():
                    family_cases[families[case]].append(statistics.median(ratios))
                family_effects = {f: geometric(v) for f, v in sorted(family_cases.items())}
                values = list(family_effects.values())
                lofo = [geometric(values[:i] + values[i + 1:]) for i in range(len(values))]
                lofo = [v for v in lofo if v is not None]
                interval = None
                if len(values) >= 2:
                    rng = random.Random(20261030)
                    draws = sorted(geometric([values[rng.randrange(len(values))] for _ in values])
                                   for _ in range(2000))
                    interval = [draws[int(0.025 * 1999)], draws[int(0.975 * 1999)]]
                effects.append({"task": task, "boundary": boundary, "candidate": candidate,
                                "baseline": baseline, "common_cases": len(per_case),
                                "requested_cases": len({r["case_id"] for r in group}),
                                "paired_successes": sum(map(len, per_case.values())),
                                "family_effects": family_effects,
                                "family_common_cases": {f: len(v) for f, v in family_cases.items()},
                                "family_requested_cases": {f: len({r["case_id"] for r in group if r["family"] == f}) for f in family_effects},
                                "family_balanced_ratio": geometric(values),
                                "descriptive_family_resampling": interval,
                                "leave_one_family_out": [min(lofo), max(lofo)] if lofo else None})
    return {"coverage": coverage, "effects": effects,
            "trials": len(rows), "statuses": dict(Counter(
                "ok" if r["status"] in GOOD else r["status"] for r in rows)),
            "case_count": len({r["case_id"] for r in rows}),
            "family_count": len({r["family"] for r in rows}),
            "attempted_trials": sum(r["status"] != "not_run" for r in rows),
            "attempted_cases": len({r["case_id"] for r in rows if r["status"] != "not_run"}),
            "attempted_families": len({r["family"] for r in rows if r["status"] != "not_run"})}


def table(path, caption, label, columns, headings, body):
    lines = [r"\begin{table}[tbp]", r"\centering\scriptsize",
             r"\setlength{\tabcolsep}{3pt}", r"\caption{" + caption + "}",
             r"\label{" + label + "}", r"\begin{tabular}{" + columns + "}",
             r"\toprule", " & ".join(headings) + r" \\", r"\midrule"]
    lines += [" & ".join(row) + r" \\" for row in body]
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    path.write_text("\n".join(lines) + "\n")


def generate(source, output, classification_source=None):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    raw, artifact_sha256 = read_artifact(source)
    data = json.loads(raw)
    if data.get("schema") != "symq/qualification/v1":
        raise ValueError("unrecognized qualification protocol")
    source_info = data.get("source", {})
    native_info = source_info.get("native", {})
    if (data.get("complete") is not True
            or not re.fullmatch(r"[0-9a-f]{40}", source_info.get("commit", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", native_info.get("binary_sha256", ""))
            or not re.fullmatch(r"[0-9a-f]{64}", data.get("manifest_sha256", ""))):
        raise ValueError("complete, pinned source/binary/manifest evidence required")
    for row in data["rows"]:
        if row["status"] in GOOD and (
                row.get("source_commit") != source_info["commit"]
                or row.get("native_sha256") != native_info["binary_sha256"]):
            raise ValueError("trial provenance differs from pinned source")
    classification_source = classification_source or source.with_name("case-classification.json")
    classification_raw = classification_source.read_bytes()
    classification = json.loads(classification_raw)
    mapping = validate_classification(data, classification)
    derived = summarise(data)
    derived["case_adjudication"] = classification
    derived["case_adjudication_sha256"] = hashlib.sha256(classification_raw).hexdigest()
    derived["holdout_only_sensitivity"] = holdout_sensitivity(data, classification)
    derived["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    derived["artifact_sha256"] = artifact_sha256
    derived["artifact_encoding"] = "gzip" if source.suffix == ".gz" else "identity"
    derived["source"] = data["source"]
    derived["manifest_sha256"] = data["manifest_sha256"]
    derived["limits"] = data["limits"]
    derived["analysis"] = {
        "primary": "zdd-native-fused (shipped public gate loop)",
        "secondary": "zdd-native (explicit matched Python-loop configuration)",
        "ratio": "baseline/candidate on same case/task/boundary/repetition with successful exhaustive oracle checks",
        "aggregation": "median paired ratio per case; geometric mean of cases per family; equal-family geometric mean",
        "resampling": "2000 descriptive family draws, seed 20261030; no population confidence claim",
        "coverage": "requested trial outcomes, separate service checkpoints; repetitions are not extra programs",
        "study_classification": "original mixed-study aggregate retained; deterministic increment is calibration despite raw new_holdout label; holdout-only result is a post-audit sensitivity",
    }
    output.mkdir(parents=True, exist_ok=True)
    (output / "derived.json").write_text(json.dumps(derived, sort_keys=True, indent=2) + "\n")
    aggregate = defaultdict(Counter)
    service_counts = Counter()
    for item in derived["coverage"]:
        if item["boundary"] == PUBLIC:
            aggregate[(item["task"], item["backend"])].update(item["statuses"])
            service_counts[(item["task"], item["backend"])] += item["service_completed"]
    body = []
    for (task, backend), counts in sorted(aggregate.items()):
        failures = sum(v for k, v in counts.items() if k not in STATUS)
        body.append([tex(task), tex(backend), str(service_counts[(task, backend)]), str(counts["ok"]), str(sum(counts.values())),
                     str(counts["unsupported"]), str(counts["not_run"]),
                     str(counts["timeout"]), str(counts["oom"]),
                     str(counts["inconclusive"]), str(counts["killed"]), str(counts["error"] + failures)])
    table(output / "coverage.tex", "Current qualification, public service boundary. Counts are worker trials, not independent circuits. S: successful service checkpoint; ok: complete qualified trial. S overlaps outcome columns and is not added to total. Every requested status stays in the denominator; U: unsupported; NR: not run; T: timeout; O: OOM; I: inconclusive; K: killed; E: error/other failure.",
          "tab:current-coverage", "llrrrrrrrrrr", ["task", "backend", "S", "ok", "total", "U", "NR", "T", "O", "I", "K", "E"], body)
    symbols = {"ok": "ok", "timeout": "T", "oom": "O", "unsupported": "U",
               "not_run": "NR", "inconclusive": "I", "killed": "K", "error": "E"}
    adverse_body = []
    for case_id, item in sorted(mapping.items()):
        if item["classification"] != "fresh_adverse_holdout":
            continue
        case_rows = [r for r in data["rows"] if r["case_id"] == case_id and r["boundary"] == PUBLIC]
        for backend in sorted({r["backend"] for r in case_rows}):
            counts = []
            for task in ("equivalence", "counterexample"):
                outcomes = Counter(r["status"] for r in case_rows
                                   if r["backend"] == backend and r["task"] == task)
                counts.append(", ".join(f"{outcomes[status]} {symbols[status]}" for status in STATUS if outcomes[status]))
            adverse_body.append([tex(case_id), tex(backend), *counts])
    table(output / "adverse.tex", "Adverse-case public decision and witness services, retained separately. Counts include every requested repeat. T: timeout; I: inconclusive; U: unsupported. All observed I entries here hit the native allocated-manager-node guard, not a final-reachable-DAG size bound or wall-time estimate. QCEC's verdict does not supply the concrete witness required by the last column. These cases lack exhaustive-oracle timing eligibility and never enter the conditional speed ratios.",
          "tab:current-adverse", "p{3.4cm}p{3.2cm}rr", ["case", "backend", "equivalence", "counterexample"], adverse_body)
    primary = "zdd-native-fused" if any(r["backend"] == "zdd-native-fused" for r in data["rows"]) else "zdd-native"
    body = []
    for item in derived["effects"]:
        if item["boundary"] != PUBLIC or item["candidate"] != primary or not item["common_cases"]:
            continue
        if item["task"] not in {"equivalence", "anf_export"}:
            continue
        if item["baseline"] not in {"zdd", "polybori", "cudd-bdd", "sat", "pysat"}:
            continue
        for family, ratio in item["family_effects"].items():
            body.append([tex(item["task"]), tex(item["baseline"]), tex(family),
                         f"{ratio:.2f}", str(item["family_common_cases"][family]) + "/" + str(item["family_requested_cases"][family])])
    table(output / "families.tex", "Current conditional service-time ratio, baseline/shipped-native-fused ($>1$: shipped native faster), by family. Each circuit contributes its median paired-repeat ratio; no population generalization. The last column counts distinct common oracle-checked/planned cases within that family, including unrun cases in the planned denominator; repeats are not independent cases.",
          "tab:current-families", "lllrr", ["task", "baseline", "family", "ratio", "common/planned"], body)
    matched_body = []
    for item in derived["effects"]:
        if (item["boundary"] != PUBLIC or item["candidate"] != "zdd-native"
                or not item["common_cases"]
                or item["task"] not in {"equivalence", "anf_export"}
                or item["baseline"] not in {"zdd", "polybori", "cudd-bdd", "sat"}):
            continue
        lofo = item["leave_one_family_out"]
        matched_body.append([tex(item["task"]), tex(item["baseline"]),
                             f"{item['family_balanced_ratio']:.2f}",
                             str(len(item["family_effects"])),
                             f"{item['common_cases']}/{item['requested_cases']}",
                             "---" if lofo is None else f"{lofo[0]:.2f}--{lofo[1]:.2f}"])
    table(output / "matched.tex", "Secondary matched-Python-loop native configuration, not the shipped fused default. Public-boundary baseline/native ratio, equal-family aggregate over common independently oracle-checked cases. The planned denominator includes unrun cases; attempted cases are \\QualRunCases{}/\\QualCases{}. F: represented families; LOFO: leave-one-family-out range. This is a distinct configuration, not a post-hoc best mode.",
          "tab:current-matched", "llrrrr", ["task", "baseline", "ratio", "F", "common/planned", "LOFO"], matched_body)
    classification_body = [[tex(case_id), tex(item["classification"]), tex(item["raw_split"])]
                           for case_id, item in sorted(mapping.items())]
    table(output / "classification.tex", "Case-level adjudication of the measured manifest. Raw labels and trials are preserved. Increment is deterministic development calibration; new seeds do not create unseen programs when the generator ignores them. Full reasons and the timestamped discovery are in the separate hashed sidecar.",
          "tab:current-classification", "p{3.4cm}p{4.8cm}p{2.8cm}", ["case", "adjudicated class", "raw split"], classification_body)
    holdout_body = []
    for item in derived["holdout_only_sensitivity"]["effects"]:
        if (item["boundary"] != PUBLIC or item["candidate"] != primary
                or not item["common_cases"]
                or item["task"] not in {"equivalence", "anf_export"}
                or item["baseline"] not in {"zdd", "polybori", "cudd-bdd", "sat"}):
            continue
        lofo = item["leave_one_family_out"]
        holdout_body.append([tex(item["task"]), tex(item["baseline"]),
                             f"{item['family_balanced_ratio']:.2f}",
                             str(len(item["family_effects"])),
                             f"{item['common_cases']}/{item['requested_cases']}",
                             "---" if lofo is None else f"{lofo[0]:.2f}--{lofo[1]:.2f}"])
    sensitivity = derived["holdout_only_sensitivity"]
    table(output / "holdout.tex", "Post-audit adjudicated holdout-only sensitivity, excluding deterministic increment calibration without replacing or rerunning cases. Baseline/shipped-native-fused ratio, same estimator and exhaustive-oracle gate as the original mixed study. The planned denominator includes unrun cases; attempted cases are "
          + f"{sensitivity['attempted_cases']}/{sensitivity['case_count']}. "
          + "Only two small stochastic families qualify for ratios; the adverse family remains in coverage. This is not population inference or a new preregistered primary analysis.",
          "tab:current-holdout", "llrrrr", ["task", "baseline", "ratio", "F", "common/planned", "LOFO"], holdout_body)
    task_order = [t for t in TASKS if any(t == k[0] for k in aggregate)]
    columns = min(2, max(1, len(task_order)))
    nrows = math.ceil(max(1, len(task_order)) / columns)
    fig, axes = plt.subplots(nrows, columns, figsize=(3.5 * columns, 3.0 * nrows), squeeze=False)
    for ax, task in zip(axes.flat, task_order):
        entries = sorted((b, counts) for (t, b), counts in aggregate.items() if t == task)
        names = [b for b, _ in entries]
        bottoms = [0] * len(names)
        for status in STATUS:
            values = [counts[status] for _, counts in entries]
            ax.barh(names, values, left=bottoms, label=status)
            bottoms = [a + b for a, b in zip(bottoms, values)]
        ax.set_title(task)
        ax.set_xlabel("worker trials")
        ax.tick_params(labelsize=7)
    for ax in list(axes.flat)[len(task_order):]:
        ax.set_visible(False)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="lower center", ncol=min(7, len(labels)), fontsize=7)
    fig.tight_layout(rect=(0, 0.12, 1, 1))
    fig.savefig(output / "coverage.pdf", metadata={"CreationDate": None})
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(6.7, 3.3))
    points = defaultdict(list)
    for row in data["rows"]:
        if (row["task"] == "anf_export" and row["boundary"] == PUBLIC
                and row["status"] in GOOD and row.get("peak_rss_bytes")
                and row["service_seconds"] > 0):
            points[row["backend"]].append((row["service_seconds"], row["peak_rss_bytes"] / 1024**2))
    for backend, values in sorted(points.items()):
        ax.scatter([v[0] for v in values], [v[1] for v in values], s=12, alpha=0.35, label=backend)
    ax.set_xscale("log")
    ax.set_xlabel("ANF-export public service time (s, log scale)")
    ax.set_ylabel("whole-worker peak RSS (MiB)")
    ax.grid(alpha=0.2)
    if points:
        ax.legend(fontsize=7)
    fig.tight_layout()
    fig.savefig(output / "cost_rss.pdf", metadata={"CreationDate": None})
    plt.close(fig)
    counts = derived["statuses"]
    status_text = ", ".join(f"{value} {tex(status)}" for status, value in sorted(counts.items()))
    checked = sum(r.get("oracle_checked") is True for r in data["rows"] if r["status"] in GOOD)
    replayed = sum(r.get("witness_checked") is True for r in data["rows"] if r["status"] in GOOD)
    interpretation = [
        r"\paragraph{Observed status and evidence.} The raw records contain " + status_text + ". "
        + f"Among successful trials, {checked} record an independent small-domain oracle check "
        + f"and {replayed} record concrete witness replay. These are different evidence counts, "
        + "not additional independent programs. Unrun cases provide no measured "
        + "representation frontier, and unsupported requests do not establish slowness. Actual failures on attempted cases remain measured evidence under their stated limits.",
        r"\paragraph{Conditional family effects.} Ratios below concern only the public API "
        + "boundary and common successful, independently oracle-checked paired repetitions. Native means the predeclared shipped "
        + "\\texttt{zdd-native-fused} public configuration, not a post-hoc best native mode. "
        + "Each family receives one aggregate vote. Intervals are descriptive cluster resampling, "
        + "not justified cross-family population confidence. These original aggregates describe "
        + "the mixed study, including deterministic increment calibration, rather than a pure untouched holdout. "
        + r"Table~\ref{tab:current-holdout} separately reports the post-audit holdout-only sensitivity.",
    ]
    absolute = []
    for backend in ("zdd-native-fused", "zdd", "polybori", "cudd-bdd", "sat"):
        values = [row["service_seconds"] for row in data["rows"]
                  if row["boundary"] == PUBLIC and row["task"] == "equivalence"
                  and row["backend"] == backend and row["status"] in GOOD
                  and row.get("oracle_checked") is True]
        if values:
            absolute.append(tex(backend) + f": {1000 * statistics.median(values):.3f}\\,ms")
    interpretation.append(r"\paragraph{Absolute cost and boundary.} Median public equivalence "
                          + "service time over oracle-checked repeat rows is " + "; ".join(absolute) + ". "
                          + "These are tiny programs and complete configured API calls including per-call manager "
                          + "construction, with process startup/imports excluded. Their large ratios against optional "
                          + "packages do not isolate a C-kernel advantage or establish larger-workload competitiveness. "
                          + r"Table~\ref{tab:current-adverse} shows the distinct adverse decision/witness frontier; "
                          + "the native node guard is an observed manager-allocation frontier under the declared policy, "
                          + "not a final-DAG lower bound or proof that different orders or collection cannot help.")
    family_rows = defaultdict(list)
    for row in data["rows"]:
        if row["boundary"] == PUBLIC:
            family_rows[row["family"]].append(row)
    family_text = []
    for family, rows in sorted(family_rows.items()):
        family_counts = Counter(r["status"] for r in rows)
        attempted = [r for r in rows if r["status"] != "not_run"]
        counts_text = ", ".join(f"{count} {tex(status)}" for status, count in sorted(family_counts.items()))
        family_text.append(tex(family) + ": "
                           + f"{len({r['case_id'] for r in attempted})}/{len({r['case_id'] for r in rows})} "
                           + "attempted/planned cases, " + counts_text + ".")
    interpretation.append(r"\paragraph{Family coverage and censures.} " + " ".join(family_text)
                          + " These counts retain all backends and tasks; repetition counts do not measure independent workload diversity.")
    for item in derived["effects"]:
        if (item["boundary"] != PUBLIC or item["candidate"] != primary or not item["common_cases"]
                or item["task"] not in {"equivalence", "anf_export"}
                or item["baseline"] not in {"zdd", "polybori", "cudd-bdd", "sat"}):
            continue
        ratio = item["family_balanced_ratio"]
        interval = item["descriptive_family_resampling"]
        lofo = item["leave_one_family_out"]
        text = (tex(item["task"]) + " against " + tex(item["baseline"]) + ": "
                + f"{ratio:.2f} on {item['common_cases']}/{item['requested_cases']} common/planned cases "
                + f"and {item['paired_successes']} successful repeat pairs")
        if interval is not None:
            text += f", descriptive interval [{interval[0]:.2f}, {interval[1]:.2f}]"
        if lofo is not None:
            text += f", leave-one-family-out range [{lofo[0]:.2f}, {lofo[1]:.2f}]"
        interpretation.append(text + ".")
    interpretation.append(
        "This bounded synthetic qualification establishes only the observed protocol behavior. "
        "They do not determine competitiveness on larger compiler-generated circuits, "
        "a broad SAT/BDD/PolyBoRi ranking, or the cause of an operation-level effect.")
    (output / "interpretation.tex").write_text("\n\n".join(interpretation) + "\n")
    source_info = data["source"]
    commit = source_info.get("commit", "unrecorded")
    native = source_info.get("native") or {}
    summary = [r"\newcommand{\QualTrials}{" + str(derived["trials"]) + "}",
               r"\newcommand{\QualCases}{" + str(derived["case_count"]) + "}",
               r"\newcommand{\QualFamilies}{" + str(derived["family_count"]) + "}",
               r"\newcommand{\QualRunTrials}{" + str(derived["attempted_trials"]) + "}",
               r"\newcommand{\QualRunCases}{" + str(derived["attempted_cases"]) + "}",
               r"\newcommand{\QualRunFamilies}{" + str(derived["attempted_families"]) + "}",
               r"\newcommand{\QualMaxTerms}{" + str(data["limits"]["max_terms"]) + "}",
               r"\newcommand{\QualMaxNodes}{" + str(data["limits"]["max_nodes"]) + "}",
               r"\newcommand{\QualCommit}{\texttt{" + tex(commit) + "}}",
               r"\newcommand{\QualNative}{\texttt{" + tex(native.get("binary_sha256", "unrecorded")) + "}}",
               r"\newcommand{\QualRawHash}{\texttt{" + derived["raw_sha256"] + "}}",
               r"\newcommand{\QualArtifactHash}{\texttt{" + artifact_sha256 + "}}",
               r"\newcommand{\QualClassificationHash}{\texttt{" + derived["case_adjudication_sha256"] + "}}"]
    (output / "numbers.tex").write_text("\n".join(summary) + "\n")
    print(json.dumps({"raw_sha256": derived["raw_sha256"], "trials": derived["trials"],
                      "statuses": derived["statuses"], "output": str(output)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=PAPER / "qualification")
    parser.add_argument("--classification", type=Path,
                        help="required adjudication sidecar; defaults to case-classification.json beside results")
    args = parser.parse_args()
    generate(args.results, args.output, args.classification)
