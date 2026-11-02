"""Reproducible development qualification of exact source-bound CEGIS discovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from fractions import Fraction
from itertools import product
from pathlib import Path

from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.nonlinear_phase_bits import check_nonlinear_phase
from symq.labs.phase_discovery import discover_phase_certificate
from symq.phase import PhaseProgram
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import candidate, fixture


def run():
    if not __debug__:
        raise RuntimeError('qualification requires assertions enabled')
    report = {'passed': True, 'rows': [], 'counts': {}, 'scale': [],
              'scope': 'constructed development, no holdout or comparative-speed claim'}
    began = time.perf_counter()
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        truth = same_channel(left, right, d, columns=support.columns)
        certificate = candidate(values)
        for degree in (1, 2):
            expected = 'dictionary_exhausted' if degree == 1 and any(3 in p for p in certificate) else 'proved'
            row = {'values': values, 'degree': degree, 'expected': expected, 'qualified': False}
            try:
                result = discover_phase_certificate(left, right, d, support=support, max_degree=degree)
                row['result'] = result
                assert truth and result['status'] == expected, result
                assert result['rounds'] <= result['feature_count'] + 1
                if expected == 'proved':
                    assert result['fresh_verified'] is True and result['certificate'] is not None
                    # External fresh recheck, distinct from the learner's internal gate.
                    planes = tuple(tuple(p) for p in result['certificate'])
                    fresh = check_nonlinear_phase(left, right, d, planes, support=support)
                    row['external_recheck'] = fresh
                    assert fresh['status'] == 'proved'
                    assert fresh['source_sha256'] == result['source_sha256']
                else:
                    assert result['certificate'] is None and result['witness'] is None
                    feature_xor = label_xor = 0
                    for sample in result['obstruction']['samples']:
                        x = sample['input']
                        h = (x & 1) * (x >> 1 & 1) | ((x >> 1 & 1) * (x >> 2 & 1) << 1)
                        assert h == sample['signature'] and sample['delta'] == values[h]
                        feature_xor ^= 1 | ((h & 1) << 1) | ((h >> 1 & 1) << 2)
                        label_xor ^= values[h]
                    assert feature_xor == 0 and label_xor != 0
                row['qualified'] = True
                label = f'degree{degree}_{expected}'
                report['counts'][label] = report['counts'].get(label, 0) + 1
            except Exception as error:  # noqa: BLE001 - retain every failed case, continue cohort
                row['error'] = f'{type(error).__name__}: {error}'
                report['passed'] = False
            report['rows'].append(row)
    for width in (8, 24, 48):
        left = DyadicPhaseProgram(width, k=3).s(0).z(5).phase(width - 1, Fraction(1, 8))
        right, d = DyadicPhaseProgram(width, k=3), PhaseProgram(width, 1)
        for q in range(width):
            d.cx(q, width).hmr(width)
        row = {'width': width, 'qualified': False}
        try:
            result = discover_phase_certificate(left, right, d, max_degree=1)
            row['result'] = result
            assert result['status'] == 'proved' and result['fresh_verified'] is True
            assert result['feature_count'] == width + 1 and result['sample_count'] <= width + 1
            row['qualified'] = True
        except Exception as error:  # noqa: BLE001 - preserve scaling failures
            row['error'] = f'{type(error).__name__}: {error}'
            report['passed'] = False
        report['scale'].append(row)
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/phase_discovery.py', 'src/symq/labs/nonlinear_phase_bits.py',
             'src/symq/labs/affine_phase.py', 'src/symq/labs/kraus_graph.py',
             'benchmarks/phase_discovery.py', 'tests/testkit/nonlinear_phase_cases.py',
             'tests/testkit/affine_phase_oracle.py')
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
    except Exception as error:  # noqa: BLE001 - setup failures must produce JSON too
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'sources')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
