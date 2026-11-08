"""Reproducible synthetic resource-frontier development campaign; no speedup claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import resource
import struct
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

from symq.hashing import canonical_sha256
from symq.labs.kmb_resource_frontier import assess_kmb_resources, replay_kmb_resources
from symq.resources import Budget

from .environment import machine, receipt

SEED = 2026110804


def fixture(flips: int, interference: bool) -> bytes:
    """Original MIT synthetic SOA writer, independent of the analyzer/reader."""
    header = struct.pack('<16sIIII9Q', bytes.fromhex('d750c7d5c329d326e3cc9f6834f2b8bf'),
                         2, 3, 0, 1, flips + 2, 0, 1, flips + 1, 0, 0, 0, 0, 0)
    packets = {1: bytes([18]) + bytes([17]) * flips + bytes([33]),
               5: struct.pack('<I', 1), 6: struct.pack('<I', 0 if interference else 2),
               7: bytes(4 * (flips + 1)), 11: bytes(8)}
    register = struct.pack('<II3I', 0, 3, 0x80000000, 0x80000001, 0x80000002)
    header += struct.pack('<QQ', 0, len(register)) + register
    return header + b''.join(struct.pack('<QQ', k, len(packets.get(k, b'')))
                             + packets.get(k, b'') for k in range(1, 12))


def trial(flips: int, interference: bool, repetition: int) -> dict:
    with tempfile.TemporaryDirectory(prefix='symq-resource-benchmark-') as directory:
        source = Path(directory) / 'synthetic.kmb'
        started, cpu = time.perf_counter(), time.process_time()
        raw = fixture(flips, interference)
        source.write_bytes(raw)
        pin = hashlib.sha256(raw).hexdigest()
        creation = {'wall_seconds': time.perf_counter() - started,
                    'cpu_seconds': time.process_time() - cpu, 'source_bytes': len(raw)}
        del raw
        request = {'kind': 'symq_kmb_resource_frontier', 'schema_version': 1,
                   'source_file_sha256': pin, 'cut_op': flips + 1, 'lease_stop_op': flips + 2,
                   'wires': [0, 1, 2], 'initial_constants': []}
        pins = {'expected_source_sha256': pin, 'expected_request_sha256': canonical_sha256(request)}
        observations = []
        for occurrence in range(2):
            started, cpu = time.perf_counter(), time.process_time()
            result = assess_kmb_resources(source, request, **pins, budget=Budget(max_seconds=30))
            scan = {'wall_seconds': time.perf_counter() - started,
                    'cpu_seconds': time.process_time() - cpu}
            started, cpu = time.perf_counter(), time.process_time()
            replay = replay_kmb_resources(source, request, result, **pins, budget=Budget(max_seconds=30))
            scan.update(replay_wall_seconds=time.perf_counter() - started,
                        replay_cpu_seconds=time.process_time() - cpu)
            ok = (result['status'] == replay['status'] == 'assessed'
                  and [f['value'] for f in result['facts']] == [flips % 2, None, None]
                  and result['available_zero_wires'] == ([0] if flips % 2 == 0 and not interference else [])
                  and not result['candidate_authorized'])
            observations.append({'occurrence': occurrence, 'timing': scan, 'receipt': result,
                                 'replay_equal': replay == result, 'oracle_ok': ok})
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return {'flips': flips, 'interference': interference, 'repetition': repetition,
                'outcome': 'complete', 'creation_write_hash': creation,
                'process_cumulative_peak_rss_bytes': int(rss if sys.platform == 'darwin' else rss * 1024),
                'disk': {'source_bytes': source.stat().st_size, 'private_snapshot_bytes_per_call': source.stat().st_size,
                         'index_bytes': 0}, 'observations': observations,
                'oracle_ok': all(o['oracle_ok'] and o['replay_equal'] for o in observations)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.repetitions <= 20:
        parser.error('repetitions must be 1..20')
    schedule = [(n, interference, rep) for rep in range(args.repetitions)
                for n, interference in ((10_000, False), (100_000, False), (100_001, True))]
    random.Random(SEED).shuffle(schedule)
    trials = []
    for n, interference, rep in schedule:
        try:
            trials.append(trial(n, interference, rep))
        except Exception as error:  # noqa: BLE001 - retain failed trials
            trials.append({'flips': n, 'interference': interference, 'repetition': rep,
                           'outcome': 'error', 'oracle_ok': False,
                           'reason': f'{type(error).__name__}: {error}'})
    result = {'kind': 'symq_resource_frontier_development', 'schema_version': 1,
              'scope': 'original MIT synthetic development fixtures, no holdout or speedup claim',
              'timing': 'serial randomized schedule; first/repeated scans, no controlled cold OS cache',
              'work': 'snapshot copy+hash in each call; buffer bytes are logical reads, not physical I/O',
              'machine': machine(), 'software': receipt(), 'seed': SEED,
              'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'outcomes': dict(Counter(t['outcome'] for t in trials)), 'trials': trials,
              'all_oracles_ok': all(t['oracle_ok'] for t in trials)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'outcomes': result['outcomes'], 'all_oracles_ok': result['all_oracles_ok']}))
    if not result['all_oracles_ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
