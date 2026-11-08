"""Original tiny full-source KMB splice benchmark; no real-source speed claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path

from symq.experimental.hybrid import HOp
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import HybridFragment
from symq.labs.kmb_reset_cache import prove_kmb_reset_cache, replay_kmb_reset_cache
from symq.labs.reset_cache import cache_request
from symq.resources import Budget

from .environment import machine, receipt


def fixture():
    import struct

    header = struct.pack('<16sIIII9Q', bytes.fromhex('d750c7d5c329d326e3cc9f6834f2b8bf'),
                         2, 4, 1, 0, 24, 2, 0, 22, 1, 1, 0, 0, 0)
    packets = {1: bytes([80, 49] + [17] * 20 + [49, 144]),
               2: struct.pack('<2I', 0, 0), 3: struct.pack('<2I', 1, 1), 4: struct.pack('<2I', 2, 2),
               7: struct.pack('<22I', 3, *([2] * 20), 0), 8: bytes(4), 9: bytes(4), 11: bytes(8)}
    return header + b''.join(struct.pack('<QQ', k, len(packets.get(k, b'')))
                            + packets.get(k, b'') for k in range(1, 12))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'source.kmb'
        raw = fixture()
        source.write_bytes(raw)
        source_pin = hashlib.sha256(raw).hexdigest()
        fragment = HybridFragment(3, (HOp('ccx', (0, 1, 2)), *[HOp('x', (2,)) for _ in range(20)], HOp('ccx', (0, 1, 2))))
        request = {'kind': 'symq_kmb_reset_cache_site', 'schema_version': 1, 'source_file_sha256': source_pin,
                   'window': [1, 23], 'pair': [1, 22], 'wires': [0, 1, 2], 'fresh_wire': 4, 'fresh_bit': 1,
                   'domain': 'all_original_quantum_states_and_arbitrary_classical_values',
                   'observation': 'all_original_outputs_new_hmr_result_forgotten',
                   'local_request': cache_request(fragment, (0, 21), fresh_slot='b1')}
        pins = {'expected_source_sha256': source_pin, 'expected_request_sha256': canonical_sha256(request)}
        for repetition in range(3):
            try:
                output = Path(directory) / f'candidate-{repetition}.kmb'
                wall, cpu = time.perf_counter(), time.process_time()
                proof = prove_kmb_reset_cache(source, request, **pins, output_path=output, budget=Budget(max_seconds=20))
                timing = {'proof_apply_wall_seconds': time.perf_counter() - wall, 'proof_apply_cpu_seconds': time.process_time() - cpu}
                wall, cpu = time.perf_counter(), time.process_time()
                replay = replay_kmb_reset_cache(source, request, proof, **pins, candidate_path=output, budget=Budget(max_seconds=20))
                timing.update(replay_wall_seconds=time.perf_counter() - wall, replay_cpu_seconds=time.process_time() - cpu)
                ok = proof['outcome'] == 'equivalent_channel_extension' and replay == proof
                rows.append({'repetition': repetition, 'oracle_ok': ok, 'proof': proof, 'timing': timing,
                             'source_bytes': source.stat().st_size, 'candidate_bytes': output.stat().st_size})
            except Exception as error:  # noqa: BLE001 - preserve failed trials
                rows.append({'repetition': repetition, 'oracle_ok': False, 'reason': f'{type(error).__name__}: {error}'})
    result = {'kind': 'symq_kmb_cache_development', 'schema_version': 1, 'machine': machine(), 'software': receipt(),
              'scope': 'MIT synthetic development; original HMR/adaptive context; no cold-cache, real-source or speedup claim',
              'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'rows': rows,
              'all_oracles_ok': all(r['oracle_ok'] for r in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'trials': len(rows), 'all_oracles_ok': result['all_oracles_ok']}))
    if not result['all_oracles_ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
