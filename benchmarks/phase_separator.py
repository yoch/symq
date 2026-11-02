"""Paired phase-discovery qualification with logarithmic-degree feature refinement.

Synthetic development: pure separator counterexamples and whole-source trials
are different cohorts. All rows, refusals and unfavorable timings are retained.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import time
from itertools import product
from pathlib import Path

from benchmarks.phase_adaptive import fresh, sparse_family, validate_growth
from symq.labs.phase_adaptive import _separator, discover_adaptive_phase
from symq.labs.phase_separator import halving_separator
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def validate_bound(result):
    validate_growth(result)
    for event in result['growth']:
        assert event['added_mask'].bit_count() <= len(event['signature_words']).bit_length() - 1


def run():
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    start = time.perf_counter()
    report = {'passed': True, 'rows': [], 'paired': [], 'kernels': [],
              'scope': 'constructed development, not holdout, minimum-degree search or external speedup'}
    for width in (5, 7, 15, 31, 63, 127, 255):
        full = (1 << width) - 1
        words = tuple(sorted({0, full, *(full ^ (1 << j) for j in range(width)),
                              *(1 << j for j in range(width))}))
        for method, call in (('greedy', _separator), ('halving', halving_separator)):
            row = {'width': width, 'samples': len(words), 'method': method, 'trials': []}
            for _ in range(3):
                count = [0]

                def tick(counter=count):
                    counter[0] += 1

                before = time.perf_counter()
                mask = call(words, tick)
                elapsed = time.perf_counter() - before
                assert sum(word & mask == mask for word in words) % 2 == 1
                assert mask.bit_count() == (width if method == 'greedy' else 3)
                row['trials'].append({'degree': mask.bit_count(), 'mask': mask,
                                      'budget_callbacks': count[0], 'seconds': elapsed})
            report['kernels'].append(row)
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        assert same_channel(left, right, d, columns=support.columns)
        for method in ('greedy', 'halving'):
            row = {'values': values, 'method': method, 'qualified': False}
            try:
                result = discover_adaptive_phase(left, right, d, support=support, separator_strategy=method)
                row['result'] = result
                assert result['status'] == 'proved' and result['fresh_verified']
                row['external_recheck'] = fresh(left, right, d, support, result)
                (validate_bound if method == 'halving' else validate_growth)(result)
                row['qualified'] = True
            except Exception as error:  # noqa: BLE001 - retain failure rows
                row['error'] = f'{type(error).__name__}: {error}'
                report['passed'] = False
            report['rows'].append(row)
    rng = random.Random(16604)
    for width in (4, 8, 16, 24):
        left, right, d, support = sparse_family(width)
        pair = {'signature_width': width, 'trials': []}
        for repetition in range(5):
            order = ['greedy', 'halving']
            rng.shuffle(order)
            for method in order:
                trial = {'repetition': repetition, 'method': method, 'qualified': False}
                before = time.perf_counter()
                try:
                    result = discover_adaptive_phase(left, right, d, support=support,
                                                      separator_strategy=method, max_features=256)
                    trial.update(seconds=time.perf_counter() - before, result=result)
                    assert result['status'] in ('proved', 'inconclusive'), result
                    if result['status'] == 'proved':
                        trial['external_recheck'] = fresh(left, right, d, support, result)
                        (validate_bound if method == 'halving' else validate_growth)(result)
                    trial['qualified'] = True
                except Exception as error:  # noqa: BLE001 - preserve failures and resource refusals
                    trial['error'] = f'{type(error).__name__}: {error}'
                    report['passed'] = False
                pair['trials'].append(trial)
        report['paired'].append(pair)
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/phase_separator.py', 'src/symq/labs/phase_adaptive.py',
             'src/symq/labs/phase_discovery.py', 'src/symq/labs/nonlinear_phase_bits.py',
             'src/symq/labs/affine_phase.py', 'src/symq/labs/kraus_graph.py',
             'benchmarks/phase_separator.py', 'benchmarks/phase_adaptive.py',
             'tests/testkit/affine_phase_oracle.py', 'tests/testkit/nonlinear_phase_cases.py')
    report.update(seconds=time.perf_counter() - start, python=platform.python_version(),
                  platform=platform.platform(),
                  sources={p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
    except Exception as error:  # noqa: BLE001 - setup failure must produce evidence
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'paired', 'kernels', 'sources')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
