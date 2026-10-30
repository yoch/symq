"""Reproducible bounded sharing study; records successes and exponential limits."""
from __future__ import annotations

import hashlib
import json
import platform
import time
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from symq.experimental.hybrid import HybridProgram, coherence_image, coherence_image_shared
from symq.resources import ResourceLimitExceeded


def program(family, events):
    result = HybridProgram(1, 1)
    for event in range(events):
        result.hmr(1, "b0" if family == "dead" else f"b{event}")
    if family == "live":
        for event in range(events):
            result.x(0, condition=f"b{event}")
    return result


def main():
    root = Path(__file__).resolve().parents[2]
    records = []
    for family, events in (("dead", 6), ("dead", 12), ("dead", 40),
                           ("live", 4), ("live", 8)):
        start = time.perf_counter()
        p = program(family, events)
        construction_seconds = time.perf_counter() - start
        digest = hashlib.sha256(json.dumps([asdict(op) for op in p.ops],
                                          sort_keys=True).encode()).hexdigest()
        for repetition in range(7):
            images = {}
            # Alternate order to avoid fixing one evaluator first in every pair.
            engines = ("reference", "shared") if repetition % 2 == 0 else ("shared", "reference")
            for engine in engines:
                tracemalloc.start()
                started = time.perf_counter()
                status, reason = "completed", None
                try:
                    if engine == "reference":
                        images[engine] = coherence_image(p, 0, 1, max_events=64, max_branches=128)
                    else:
                        images[engine] = coherence_image_shared(
                            p, 0, 1, max_events=64, max_branches=128).get((), {})
                except ResourceLimitExceeded as exc:
                    status, reason = "inconclusive", str(exc)
                seconds = time.perf_counter() - started
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
                records.append({"family": family, "events": events, "engine": engine,
                                "repetition": repetition, "status": status, "reason": reason,
                                "seconds": seconds, "python_tracemalloc_peak_bytes": peak,
                                "construction_seconds": construction_seconds,
                                "program_sha256": digest})
            if len(images) == 2 and images["reference"] != images["shared"]:
                raise AssertionError("differential channel image mismatch")
    cpu = next((line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                if line.startswith("model name")), "unknown")
    payload = {
        "claim": "bounded exactness and concrete sharing limitation; no external speedup claim",
        "corpus": "development synthetic; no untouched holdout or external comparison",
        "python": platform.python_version(), "platform": platform.platform(), "cpu": cpu,
        "repetitions": 7, "quantum_width": 2, "basis_coherence": [0, 1],
        "caps": {"max_width": 6, "max_events": 64, "max_branches": 128},
        "code_sha256": {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in (root / "src/symq/experimental/hybrid.py", Path(__file__))},
        "records": records,
    }
    target = Path(__file__).with_name("sharing_results.json")
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"{len(records)} runs recorded in {target}")


if __name__ == "__main__":
    main()
