"""Fresh-process full-call performance probe for the restricted HMR channel.

One scenario is not a performance claim. Repeat on pinned *real* circuit
families with held-out data, CPU/RSS records and a source-cleared corpus.
"""
from __future__ import annotations

import argparse
import json
import resource
import subprocess
import sys
import time

from research.hmr_native_channel.native_channel import check_full_channel
from symq.phase import PhaseProgram


def case(data: int, hmr: int) -> tuple[PhaseProgram, PhaseProgram]:
    program = PhaseProgram(data, 1)
    for index in range(hmr):
        q = index % data
        program.cx(q, data)
        m = program.hmr(data)
        program.z_if(m, q)
    return program, PhaseProgram(data, 1)


def worker(backend: str, data: int, hmr: int) -> dict:
    left, right = case(data, hmr)
    started = time.perf_counter()
    verdict = check_full_channel(left, right, backend=backend)
    elapsed = time.perf_counter() - started
    return {
        "backend": backend,
        "equivalent": verdict.equivalent,
        "data": data,
        "hmr": hmr,
        "full_call_wall_seconds": elapsed,
        "maxrss_kib_unix": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "note": "platform-specific RSS; not a matched native speedup assertion",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--backend", default="zdd-native", choices=("zdd-native", "zdd"))
    parser.add_argument("--data", type=int, default=8)
    parser.add_argument("--hmr", type=int, default=130)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(args.backend, args.data, args.hmr), sort_keys=True))
        return 0
    all_results = []
    for backend in ("zdd", "zdd-native"):
        for _ in range(args.repetitions):
            command = [sys.executable, "-m", __package__ + ".benchmark", "--worker",
                       "--backend", backend, "--data", str(args.data),
                       "--hmr", str(args.hmr)]
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            if result.returncode:
                all_results.append({"backend": backend, "unsupported_or_error": result.stderr})
                break
            all_results.append(json.loads(result.stdout))
    print(json.dumps(all_results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
