"""Original synthetic signed-column cache qualification; no performance claim."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import random
import resource
import sys
import time
from pathlib import Path

from symq.experimental.hybrid import HOp
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import HybridFragment
from symq.labs.reset_cache import cache_request, prove_reset_cache, replay_reset_cache
from symq.resources import Budget

from .environment import machine, receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    tasks = [(n, r) for n in (3, 6, 9, 12) for r in range(3)]
    random.Random(2026110805).shuffle(tasks)
    rows = []
    for n, repetition in tasks:
        try:
            reference = HybridFragment(n, (HOp('ccx', (0, 1, 2)),
                *[HOp('x', (n - 1,)) for _ in range(20)], HOp('ccx', (0, 1, 2))))
            request = cache_request(reference, (0, 21))
            pin = canonical_sha256(request)
            start, cpu = time.perf_counter(), time.process_time()
            proof = prove_reset_cache(request, expected_request_sha256=pin, budget=Budget(max_seconds=20))
            timing = {'proof_wall_seconds': time.perf_counter() - start,
                          'proof_cpu_seconds': time.process_time() - cpu}
            start, cpu = time.perf_counter(), time.process_time()
            replay = replay_reset_cache(request, proof, expected_request_sha256=pin, budget=Budget(max_seconds=20))
            timing.update(replay_wall_seconds=time.perf_counter() - start,
                          replay_cpu_seconds=time.process_time() - cpu)
            mutant = copy.deepcopy(request)
            mutant['candidate']['ops'].pop()
            refusal = prove_reset_cache(mutant, expected_request_sha256=canonical_sha256(mutant))
            ok = proof['outcome'] == 'equivalent' and replay == proof and refusal['outcome'] == 'not_proved'
            rows.append({'width': n, 'repetition': repetition, 'outcome': proof['outcome'], 'oracle_ok': ok,
                             'timing': timing, 'proof': proof, 'missing_correction': refusal})
        except Exception as error:  # noqa: BLE001 - retain failed/unsupported trials
            rows.append({'width': n, 'repetition': repetition, 'outcome': 'error', 'oracle_ok': False,
                             'reason': f'{type(error).__name__}: {error}'})
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = {'kind': 'symq_reset_cache_development', 'schema_version': 1, 'seed': 2026110805,
                  'scope': 'original MIT synthetic development, no holdout or speedup claim',
                  'machine': machine(), 'software': receipt(), 'rows': rows,
                  'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'cumulative_peak_rss_bytes': int(rss if sys.platform == 'darwin' else rss * 1024),
                  'all_oracles_ok': all(r['oracle_ok'] for r in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'trials': len(rows), 'all_oracles_ok': result['all_oracles_ok']}))
    if not result['all_oracles_ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
