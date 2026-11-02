"""Paired development qualification of reference ANF, streaming ANF and streaming SAT.

Synthetic cohorts, no external-system comparison or holdout. Every non-resource
verdict in the small random cohort is checked on all coherent matrix units.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import random
import time
import tracemalloc
from itertools import product
from pathlib import Path

from benchmarks.anchored_kraus import (
    chain,
    contract,
    ideal,
    image,
    operation,
    program,
    random_source,
    states,
)
from symq.labs import anchored_kraus, anchored_stream, kraus_graph


def dense_case(n, mutant=False):
    """Same conjunction, two control orders; ANF expands products of affine XORs."""
    controls = tuple(2 * i + 1 for i in range(n))
    ops = [operation('cx', 2 * i, 2 * i + 1) for i in range(n)]
    ops.append(operation('mcx', *controls, 2 * n + 1))
    if not mutant:
        ops.append(operation('mcx', *reversed(controls), 2 * n + 1))
    ops += [operation('cx', 2 * i, 2 * i + 1) for i in reversed(range(n))]
    return program(2 * n + 1, 1, ops), contract(
        2 * n + 2, address=(0,), target=(2 * n,), clean=(2 * n + 1,),
        borrowed=tuple(range(1, 2 * n)), table=(0, 0))


def run_method(method, src, spec):
    if method == 'reference':
        return anchored_kraus.verify(src, spec, max_terms=5000, max_seconds=10)
    return anchored_stream.verify_stream(src, spec, backend=method,
                                         max_terms=5000, max_seconds=10)


def run(programs=400, seed=311):
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    if type(programs) is not int or not 1 <= programs <= 10000:
        raise ValueError('programs must be in 1..10000')
    rng = random.Random(seed)
    counts = {b: {'cases': 0, 'equivalent': 0, 'not_proved': 0, 'witnesses': 0}
              for b in ('anf', 'sat')}
    began = time.perf_counter()
    for _ in range(programs):
        src = random_source(rng)
        images = {(x, y): image(src, x, y) for x, y in product(range(8), repeat=2)}
        for table in product(range(2), repeat=2):
            for legal in ((0,), (1,), (0, 1)):
                spec = contract(table=table, legal=legal)
                inputs = states(spec)
                truth = all(images[x, y] == {(ideal(spec, x), ideal(spec, y)): 1}
                            for x, y in product(inputs, repeat=2))
                for method in counts:
                    result = run_method(method, src, spec)
                    assert result['status'] in ('equivalent', 'not_proved'), result
                    assert (result['status'] == 'equivalent') == truth
                    counts[method]['cases'] += 1
                    counts[method][result['status']] += 1
                    if not truth:
                        witness = result['witness']
                        x = witness['input']
                        y = x if result['obligation'] == 'outputs' else witness['anchor']
                        assert x in inputs and y in inputs
                        assert images[x, y] != {(ideal(spec, x), ideal(spec, y)): 1}
                        counts[method]['witnesses'] += 1
    samples = []
    src = program(13, ops=[operation('measure_z', q, slot=f'b{q}') for q in range(12)])
    spec = contract(13, address=(0,), target=(12,), clean=(), borrowed=tuple(range(1, 12)), table=(0, 0))
    cases = [('leaking_z12', src, spec, ('inconclusive', 'not_proved', 'not_proved'))]
    src = program(2, 1, [operation('measure_z', 2, slot=f'b{i}') for i in range(128)])
    spec = contract(3, borrowed=(), clean=(2,), table=(0, 0))
    cases.append(('known_zero_z128', src, spec, ('inconclusive', 'equivalent', 'equivalent')))
    src, spec = chain(256)
    cases.append(('corrected_hmr256', src, spec, ('equivalent',) * 3))
    for n in (16, 32):
        for mutant in (False, True):
            src, spec = dense_case(n, mutant)
            cases.append((f'dense{n}_mutant{int(mutant)}', src, spec,
                          ('inconclusive', 'inconclusive', 'not_proved' if mutant else 'equivalent')))
    for name, src, spec, expected in cases:
        for method, outcome in zip(('reference', 'anf', 'sat'), expected):
            trials = []
            for _ in range(3):
                start = time.perf_counter()
                result = run_method(method, src, spec)
                elapsed = time.perf_counter() - start
                assert result['status'] == outcome, (name, method, result)
                trials.append({'seconds': elapsed, 'result': result})
            # Allocation instrumentation is separate from timed trials.
            tracemalloc.start()
            try:
                memory_result = run_method(method, src, spec)
                peak = tracemalloc.get_traced_memory()[1]
            finally:
                tracemalloc.stop()
            assert memory_result['status'] == outcome
            samples.append({'case': name, 'method': method, 'trials': trials,
                            'python_peak_bytes': peak})
    root = Path(__file__).resolve().parents[1]
    paths = ['benchmarks/anchored_stream.py', 'benchmarks/anchored_kraus.py',
             'src/symq/labs/anchored_stream.py', 'src/symq/labs/anchored_kraus.py',
             str(Path(kraus_graph.__file__).resolve().relative_to(root))]
    return {'passed': True, 'seed': seed, 'programs': programs, 'differential': counts,
            'paired': samples, 'seconds': time.perf_counter() - began,
            'python': platform.python_version(), 'platform': platform.platform(),
            'python_sat': importlib.metadata.version('python-sat'),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'constructed development; no holdout or external speedup; timing excludes import'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--programs', type=int, default=400)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.programs)
    except Exception as error:  # noqa: BLE001 - failed qualification must retain evidence
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'paired'}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
