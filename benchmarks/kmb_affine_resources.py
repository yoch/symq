"""MIT synthetic affine-resource qualification; no external performance claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import tempfile
import time
from pathlib import Path

from symq.hashing import canonical_sha256
from symq.labs.kmb_affine_resources import assess_affine_kmb_resources, replay_affine_kmb_resources
from symq.resources import Budget, VerificationSession

from .environment import machine, receipt


def fixture():
    # Independent tiny SOA writer: HMR(q2)->b0; CX(q0,q2); CCX(q0,q1,q3); CZ(q0,q1).
    header = struct.pack('<16sIIII9Q', bytes.fromhex('d750c7d5c329d326e3cc9f6834f2b8bf'),
                         2, 4, 1, 0, 4, 1, 2, 1, 1, 0, 0, 0, 0)
    packets = {1: bytes([80, 33, 49, 32]), 2: struct.pack('<I', 0), 3: struct.pack('<I', 1),
        4: struct.pack('<I', 3), 5: struct.pack('<2I', 0, 0), 6: struct.pack('<2I', 2, 1),
        7: struct.pack('<I', 2), 8: bytes(4), 11: bytes(8)}
    return header + b''.join(struct.pack('<QQ', k, len(packets.get(k, b''))) + packets.get(k, b'')
                             for k in range(1, 12))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / 'source.kmb'
        raw = fixture()
        source.write_bytes(raw)
        pin = hashlib.sha256(raw).hexdigest()
        for repetition in range(3):
            for parents, expected in (([0], 'proved'), ([], 'not_proved')):
                request = {'kind': 'symq_kmb_affine_resources', 'schema_version': 1,
                    'source_file_sha256': pin, 'analysis_window': [0, 2], 'reservation_window': [2, 4],
                    'domain': 'all_source_quantum_states_and_classical_values',
                    'resources': [{'wire': 2, 'parents': parents, 'constant': 0}]}
                pins = {'expected_source_sha256': pin, 'expected_request_sha256': canonical_sha256(request)}
                wall, cpu = time.perf_counter(), time.process_time()
                try:
                    with VerificationSession(Budget(max_seconds=15)) as guard:
                        proof = assess_affine_kmb_resources(source, request, **pins, budget=guard.remaining_budget())
                        replay = replay_affine_kmb_resources(source, request, proof, **pins, budget=guard.remaining_budget())
                        guard.check_time()
                    # Scalar support oracle on every input basis and both HMR outcomes.
                    graph_values = []
                    for initial in range(16):
                        for _measurement in (0, 1):
                            state = initial & ~(1 << 2)
                            state ^= (state & 1) << 2
                            graph_values.append((state >> 2 & 1) ^ sum(state >> p & 1 for p in parents) % 2)
                    exact = 'proved' if not any(graph_values) else 'not_proved'
                    ok = proof['outcome'] == expected == exact and replay == proof
                    rows.append({'repetition': repetition, 'expected': expected, 'oracle_ok': ok,
                        'cpu_seconds': time.process_time() - cpu, 'wall_seconds': time.perf_counter() - wall,
                        'receipt': proof})
                except Exception as error:  # noqa: BLE001 - retain failed trials
                    rows.append({'repetition': repetition, 'expected': expected, 'oracle_ok': False,
                                 'reason': f'{type(error).__name__}: {error}'})
    result = {'kind': 'symq_affine_resource_development', 'schema_version': 1,
        'machine': machine(), 'software': receipt(), 'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'MIT synthetic development, positive graph/negative clean assumption; no real-source or speedup claim',
        'rows': rows, 'all_oracles_ok': all(r['oracle_ok'] for r in rows)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'trials': len(rows), 'all_oracles_ok': result['all_oracles_ok']}))
    if not result['all_oracles_ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
