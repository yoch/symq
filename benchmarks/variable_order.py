"""Variable-order sensitivity of the native monomial ZDD (experiment E4) and order invariance
of its outputs (E5).

For every supported circuit of a frozen corpus and every variable order (identity, reversed,
and ``--random-orders`` seeded random permutations), one fresh pinned worker process builds a
native ZDD manager with that order, runs the fused ``simulate`` of the circuit with a budget,
and records the time (one warmup, then the median of up to ``--repetitions`` cold runs, each on
a fresh manager), the number of ZDD nodes created, the output monomial counts and the peak RSS.

Outputs are extracted to explicit monomials (at most 2e6 terms) and hashed: the ANF of a
circuit does not depend on the variable order, so every order must give the same fingerprint.
A difference is an engine bug and is reported as such.

Cells of one (family, order) run in increasing size; after a budget refusal or a timeout the
larger circuits of that family are recorded as ``censored`` for that order.

Usage: python benchmarks/variable_order.py --corpus qcec --pin 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from matched import CORPORA, family
from run import git

from symq import Budget
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.corpus import load_corpus, sha256_hex
from symq.resources import ResourceLimitExceeded

ROOT = Path(__file__).resolve().parent
EXTRACT_MAX_TERMS = 2_000_000
MAX_NODES = 20_000_000


def orders(name: str, width: int, count: int) -> dict[str, list[int]]:
    result = {"identity": list(range(width)), "reversed": list(range(width - 1, -1, -1))}
    for index in range(count):
        permutation = list(range(width))
        random.Random(f"{name}:order:{index}").shuffle(permutation)
        result[f"random{index}"] = permutation
    return result


def worker(cell: dict) -> dict:
    if cell["pin"] is not None:
        os.sched_setaffinity(0, {cell["pin"]})
    circuit = load_corpus(Path(cell["manifest"])).entries[cell["index"]].load()
    budget = Budget(max_nodes=MAX_NODES, max_seconds=cell["budget_seconds"])

    def run() -> tuple[float, NativeZDDAlgebra, tuple[int, ...]]:
        algebra = NativeZDDAlgebra(circuit.width, budget.start(), order=cell["order"])
        started = time.perf_counter()
        outputs = algebra.simulate(circuit)
        return time.perf_counter() - started, algebra, outputs

    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    try:
        first, algebra, outputs = run()
        times = []
        if first <= 1.0:
            for _ in range(cell["repetitions"]):
                seconds, algebra, outputs = run()
                times.append(seconds)
        else:
            times.append(first)
    except ResourceLimitExceeded as error:
        return {"status": "budget", "resource": error.resource}
    terms = [algebra.terms(value) for value in outputs]
    record = {
        "status": "ok", "seconds": times, "median_seconds": statistics.median(times),
        "nodes": algebra.node_count, "output_terms": sum(terms), "max_output_terms": max(terms),
        "rss_growth_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - rss_before,
        "fingerprint": None,
    }
    if sum(terms) <= EXTRACT_MAX_TERMS:
        digest = hashlib.sha256()
        for value in outputs:
            digest.update(",".join(map(str, sorted(algebra.to_anf(value).terms))).encode())
            digest.update(b";")
        record["fingerprint"] = digest.hexdigest()
    return record


def native_compiler(path: Path) -> list[str]:
    """Compiler identification strings of the ``.comment`` section of the built extension."""
    done = subprocess.run(["readelf", "-p", ".comment", str(path)], capture_output=True,
                          text=True, check=False)
    return [line.split("]", 1)[1].strip() for line in done.stdout.splitlines() if "]" in line]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    parser.add_argument("--corpus", choices=sorted(CORPORA), default="qcec")
    parser.add_argument("--random-orders", type=int, default=5)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--pin", type=int)
    parser.add_argument("--out", type=Path, default=ROOT / "results")
    parser.add_argument("--label", default="variable-order")
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(json.loads(args.worker))))
        return 0

    manifest = CORPORA[args.corpus]
    corpus = load_corpus(manifest)
    problems = corpus.verify()
    if problems:
        raise SystemExit("corpus verification failed:\n" + "\n".join(problems))
    if git("status", "--porcelain", "--untracked-files=no"):
        raise SystemExit("tracked files are modified; commit first")
    native = Path(sys.modules["symq.backends._zdd"].__file__)
    if native.parent != ROOT.parent / "src" / "symq" / "backends":
        raise SystemExit(f"symq is imported from {native.parent}, not from this checkout; "
                         "set PYTHONPATH=src")
    started = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = git("rev-parse", "HEAD")
    target = args.out / (f"{started.replace('-', '').replace(':', '')}_{commit[:12]}_"
                         f"{args.label}-{args.corpus}")
    target.mkdir(parents=True, exist_ok=False)
    environment = {
        "started_utc": started, "symq_commit": commit, "symq_dirty": False,
        "native_extension_sha256": sha256_hex(native.read_bytes()),
        "native_extension_compiler": native_compiler(native),
        "native_source_sha256": sha256_hex(
            (ROOT.parent / "src" / "symq" / "backends" / "_zdd.c").read_bytes()),
        "python": sys.version, "corpus": args.corpus,
        "corpus_manifest_sha256": sha256_hex(manifest.read_bytes()),
        "protocol": {
            "engine": "zdd-native, fused simulate", "workload": "simulate",
            "orders": ["identity", "reversed"] + [f"random{i}" for i in
                                                  range(args.random_orders)],
            "random_order_seed": "random.Random(f'{circuit}:order:{index}')",
            "warmup": 1, "repetitions": args.repetitions,
            "adaptive_repetitions": "1 if the warmup exceeds 1 s",
            "budget": {"max_nodes": MAX_NODES, "max_seconds": args.timeout - 5},
            "cell_timeout_seconds": args.timeout, "pinned_cpu": args.pin,
            "censoring": "per (family, order), increasing size; after budget or timeout the "
                         "larger circuits are censored",
            "extraction_max_terms": EXTRACT_MAX_TERMS,
        },
        "command": sys.argv,
    }
    (target / "environment.json").write_text(json.dumps(environment, indent=2) + "\n")

    entries = [(i, e) for i, e in enumerate(corpus.entries) if e.supported]
    entries.sort(key=lambda item: (family(item[1].name), item[1].width, item[1].gates,
                                   item[1].name))
    censored: set[tuple[str, str]] = set()
    rows = []
    with (target / "results.jsonl").open("w") as sink:
        for index, entry in entries:
            for label, order in orders(entry.name, entry.width, args.random_orders).items():
                base = {"circuit": entry.name, "family": family(entry.name),
                        "width": entry.width, "gates": entry.gates, "order": label}
                key = (family(entry.name), label) if args.corpus == "blind" else None
                if key in censored:
                    row = {**base, "status": "censored"}
                else:
                    cell = {"manifest": str(manifest), "index": index, "order": order,
                            "repetitions": args.repetitions, "pin": args.pin,
                            "budget_seconds": args.timeout - 5}
                    try:
                        done = subprocess.run(
                            [sys.executable, __file__, "--worker", json.dumps(cell)],
                            capture_output=True, text=True, timeout=args.timeout, check=False)
                        outcome = (json.loads(done.stdout) if done.returncode == 0
                                   else {"status": "error", "returncode": done.returncode,
                                         "stderr": done.stderr[-2000:]})
                    except subprocess.TimeoutExpired:
                        outcome = {"status": "timeout"}
                    row = {**base, **outcome}
                    if row["status"] != "ok" and key is not None:
                        censored.add(key)
                rows.append(row)
                sink.write(json.dumps(row) + "\n")
                sink.flush()
                print(f"{entry.name:15s} {label:9s} {row['status']:8s} "
                      f"{row.get('nodes', '')}", file=sys.stderr)

    summary = summarize(rows)
    (target / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    names = ["environment.json", "results.jsonl", "summary.json"]
    (target / "SHA256SUMS").write_text("".join(
        f"{sha256_hex((target / n).read_bytes())}  {n}\n" for n in names))
    print(json.dumps({k: v for k, v in summary.items() if k != "circuits"}, indent=2))
    print(target)
    return 1 if summary["fingerprint_disagreements"] else 0


def summarize(rows: list[dict]) -> dict:
    by_circuit: dict[str, list[dict]] = {}
    for row in rows:
        by_circuit.setdefault(row["circuit"], []).append(row)
    circuits, disagreements, spreads = {}, [], []
    for name, group in by_circuit.items():
        ok = [r for r in group if r["status"] == "ok"]
        prints = {r["fingerprint"] for r in ok if r["fingerprint"] is not None}
        counts = {r["output_terms"] for r in ok}
        if len(prints) > 1 or len(counts) > 1:
            disagreements.append(name)
        identity = next((r for r in ok if r["order"] == "identity"), None)
        entry = {"completed_orders": len(ok), "orders": len(group),
                 "statuses": sorted({r["status"] for r in group})}
        if identity and len(ok) > 1:
            nodes = [r["nodes"] for r in ok]
            times = [r["median_seconds"] for r in ok]
            entry.update({
                "identity_nodes": identity["nodes"], "min_nodes": min(nodes),
                "max_nodes": max(nodes), "node_spread": max(nodes) / min(nodes),
                "identity_seconds": identity["median_seconds"],
                "best_seconds": min(times), "worst_seconds": max(times),
                "identity_over_best_time": identity["median_seconds"] / min(times),
                "identity_over_best_nodes": identity["nodes"] / min(nodes),
                "best_order": min(ok, key=lambda r: r["nodes"])["order"],
            })
            if len(ok) == len(group):
                spreads.append(entry["node_spread"])
        circuits[name] = entry
    return {
        "circuits_total": len(by_circuit),
        "fingerprint_disagreements": disagreements,
        "fingerprints_compared": sum(1 for g in by_circuit.values()
                                     if sum(r.get("fingerprint") is not None for r in g) > 1),
        "all_orders_completed": len(spreads),
        "node_spread_geomean": (statistics.geometric_mean(spreads) if spreads else None),
        "node_spread_max": max(spreads) if spreads else None,
        "circuits": circuits,
    }


if __name__ == "__main__":
    sys.exit(main())
