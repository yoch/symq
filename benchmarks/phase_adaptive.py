"""Paired development campaign for adaptive versus fixed phase dictionaries."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import time
from fractions import Fraction
from functools import partial
from itertools import product
from pathlib import Path

from symq.labs.affine_phase import AffineSupport
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.nonlinear_phase_bits import check_nonlinear_phase
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.labs.phase_discovery import discover_phase_certificate
from symq.phase import PhaseProgram
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture


def sparse_family(size):
    """Nonlinear disjoint-pair signature; three intentionally sparse phase bits."""
    if size < 4:
        raise ValueError('at least four signature coordinates')
    free, width = 2 * size, 2 * size + 1
    left, right = DyadicPhaseProgram(width, k=3), DyadicPhaseProgram(width, k=3)
    d = PhaseProgram(width, 1)
    for i in range(size):
        d.ccx(2 * i, 2 * i + 1, width)
        d.hmr(width)
    subsets = ((0, 1, 2), (1, 2, size - 1), (size - 2, size - 1))
    for bit, subset in enumerate(subsets):
        controls = tuple(q for j in subset for q in (2 * j, 2 * j + 1))
        left.mcx(*controls, free).phase(free, Fraction(1 << bit, 8)).mcx(*controls, free)
    return left, right, d, AffineSupport(width, 0, tuple(1 << i for i in range(free)))


def validate_growth(result):
    masks = list(result['initial_dictionary'])
    for event in result['growth']:
        row_xor = labels = 0
        for index in event['sample_indices']:
            sample = result['samples'][index]
            row_xor ^= sum(int(sample['signature'] & mask == mask) << j for j, mask in enumerate(masks))
            labels ^= sample['delta']
        assert row_xor == 0 and labels == event['xor_labels'] != 0
        assert sum(h & event['added_mask'] == event['added_mask'] for h in event['signature_words']) % 2
        assert event['rank_after'] > event['rank_before']
        assert event['added_mask'] not in masks
        masks.append(event['added_mask'])
    assert sorted(masks) == result['dictionary']


def fresh(left, right, d, support, result):
    assert result['fresh_verified'] is True
    planes = tuple(tuple(p) for p in result['certificate'])
    answer = check_nonlinear_phase(left, right, d, planes, support=support)
    assert answer['status'] == 'proved' and answer['source_sha256'] == result['source_sha256']
    return answer


def run():
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    began = time.perf_counter()
    report = {'passed': True, 'rows': [], 'paired': [], 'counts': {},
              'scope': 'constructed development, not holdout or external performance comparison'}
    methods = {
        'fixed_linear': lambda a, b, d, s: discover_phase_certificate(a, b, d, support=s, max_degree=1),
        'fixed_quadratic': lambda a, b, d, s: discover_phase_certificate(a, b, d, support=s, max_degree=2),
        'adaptive': lambda a, b, d, s: discover_adaptive_phase(a, b, d, support=s),
    }
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        oracle_equal = same_channel(left, right, d, columns=support.columns)
        assert oracle_equal
        for method, call in methods.items():
            row = {'values': values, 'method': method, 'qualified': False}
            try:
                result = call(left, right, d, support)
                row['result'] = result
                if method == 'fixed_linear':
                    assert result['status'] in ('proved', 'dictionary_exhausted')
                else:
                    assert result['status'] == 'proved', result
                if result['status'] == 'proved':
                    row['external_recheck'] = fresh(left, right, d, support, result)
                if method == 'adaptive':
                    validate_growth(result)
                    assert result['feature_count'] <= 4
                    for sample in result['samples']:
                        x = sample['input']
                        h = (x & 1) * (x >> 1 & 1) | ((x >> 1 & 1) * (x >> 2 & 1) << 1)
                        assert sample['signature'] == h and sample['delta'] == values[h]
                key = f"{method}_{result['status']}"
                report['counts'][key] = report['counts'].get(key, 0) + 1
                row['qualified'] = True
            except Exception as error:  # noqa: BLE001 - retain failed rows
                row['error'] = f'{type(error).__name__}: {error}'
                report['passed'] = False
            report['rows'].append(row)
    for size in (4, 8, 16, 24):
        left, right, d, support = sparse_family(size)
        calls = {
            'fixed_cubic': partial(discover_phase_certificate, left, right, d, support=support,
                                   max_degree=3, max_features=256),
            'adaptive': partial(discover_adaptive_phase, left, right, d, support=support, max_features=256),
        }
        for method, call in calls.items():
            row = {'signature_width': size, 'physical_data': 2 * size + 1, 'method': method,
                   'dense_degree3_features': sum(math.comb(size, j) for j in range(4)),
                   'trials': [], 'qualified': False}
            try:
                for _ in range(3):
                    result = call()
                    # Limits stay limits. This constructed family has equal channels, so no difference is allowed.
                    assert result['status'] in ('proved', 'inconclusive'), result
                    trial = {'result': result}
                    if result['status'] == 'proved':
                        trial['external_recheck'] = fresh(left, right, d, support, result)
                        if method == 'adaptive':
                            validate_growth(result)
                    row['trials'].append(trial)
                row['qualified'] = True
            except Exception as error:  # noqa: BLE001 - preserve resource and correctness failures separately
                row['error'] = f'{type(error).__name__}: {error}'
                report['passed'] = False
            report['paired'].append(row)
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/phase_adaptive.py', 'src/symq/labs/phase_discovery.py',
             'src/symq/labs/nonlinear_phase_bits.py', 'src/symq/labs/kraus_graph.py',
             'src/symq/labs/affine_phase.py', 'benchmarks/phase_adaptive.py',
             'tests/testkit/affine_phase_oracle.py', 'tests/testkit/nonlinear_phase_cases.py')
    report.update(seconds=time.perf_counter() - began, python=platform.python_version(),
                  platform=platform.platform(),
                  sources={p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths})
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
    except Exception as error:  # noqa: BLE001 - setup failures must leave evidence
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'paired', 'sources')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
