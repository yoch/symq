"""Before/after campaign for the lazy bounded cache (issue: constructor cost of cache_limit)."""
import json
import random
import statistics
import sys
import time

sys.path.insert(0, "src")
from pathlib import Path

from symq import simulate
from symq.backends.zdd_native import NativeZDDAlgebra
from symq.corpus import load_corpus
from symq.generators import random_circuit
from symq.resources import Budget


def best_time(circuit, limit, repeats):
    best = float("inf")
    for _ in range(repeats):
        a = NativeZDDAlgebra(circuit.width, Budget(max_nodes=80_000_000, max_seconds=150).start(),
                             cache_limit=limit)
        t = time.perf_counter(); simulate(circuit, a); best = min(best, time.perf_counter() - t)
    return best

rows = []
corpus = load_corpus(Path("benchmarks/corpus/qcec/MANIFEST.json"))
for e in corpus.entries:
    if not e.supported: continue
    c = e.load()
    if c.width > 24 or len(c.gates) > 400: continue
    row = {"case": e.name, "width": c.width, "gates": len(c.gates)}
    for label, limit in (("lossless", None), ("bounded_1M", 1 << 20)):
        row[label] = best_time(c, limit, 5)
    row["ratio"] = row["bounded_1M"] / row["lossless"]
    rows.append(row)
for w, g in ((10, 100), (11, 120), (12, 140)):
    c = random_circuit(w, g, random.Random(11))
    row = {"case": f"rand{w}x{g}", "width": w, "gates": g}
    for label, limit in (("lossless", None), ("bounded_1M", 1 << 20)):
        row[label] = best_time(c, limit, 3)
    row["ratio"] = row["bounded_1M"] / row["lossless"]
    rows.append(row)
small = [r["ratio"] for r in rows if r["case"].startswith(("5xp1","C7552","add6","alu1","apla","cm150","dk17","dk27","example2","mlp4","pcler8"))]
dense = [r["ratio"] for r in rows if r["case"].startswith("rand")]
print(f"small structured: geomean bounded/lossless = {statistics.geometric_mean(small):.2f} (n={len(small)})")
print(f"dense random:     geomean bounded/lossless = {statistics.geometric_mean(dense):.2f} (n={len(dense)})")
out = Path("research/engineering/2026-10-28/RESULTS_CACHE.json")
out.write_text(json.dumps({"small_geomean": statistics.geometric_mean(small),
                           "dense_geomean": statistics.geometric_mean(dense),
                           "rows": rows}, indent=2) + "\n")
