"""Factored phase qualification: affine mixing, independent channels and representation size."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import time
from fractions import Fraction
from itertools import product
from pathlib import Path

from symq.labs.affine_phase import AffineSupport
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.labs.phase_factored import check_factored_phase, discover_factored_phase
from symq.phase import PhaseProgram
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import fixture

MATRICES = ((1, 2), (2, 1), (1, 3), (3, 1), (2, 3), (3, 2))
VALUES = ((0, 1, 2, 3), (3, 1, 2, 0), (0, 0, 0, 1), (1, 0, 1, 3),
          (2, 2, 2, 2), (0, 0, 0, 0), (0, 3, 1, 2), (1, 3, 3, 2))


def small_mixed(values, matrix=(1, 3), offset=0):
    left, right, _original, support = fixture(values)
    d = PhaseProgram(4, 1)
    for i, row in enumerate(matrix):
        if offset >> i & 1:
            d.x(4)
        for j, wires in enumerate(((0, 1), (1, 2))):
            if row >> j & 1:
                d.ccx(*wires, 4)
        d.hmr(4)
    return left, right, d, support


def mixed_family(degree, kind='star', offset=0):
    if type(degree) is not int or not 2 <= degree <= 32:
        raise ValueError('degree must be in 2..32')
    free, width = 2 * degree, 2 * degree + 1
    left, right = DyadicPhaseProgram(width, k=3), DyadicPhaseProgram(width, k=3)
    d = PhaseProgram(width, 1)
    for i in range(degree):
        if kind == 'star':
            terms = (i, degree - 1) if i < degree - 1 else (i,)
        elif kind == 'chain':
            terms = (i, i + 1) if i < degree - 1 else (i,)
        else:
            raise ValueError('unknown affine mixing')
        if offset >> i & 1:
            d.x(width)
        for j in terms:
            d.ccx(2 * j, 2 * j + 1, width)
        d.hmr(width)
    controls = tuple(range(free))
    left.mcx(*controls, free).phase(free, Fraction(1, 8)).mcx(*controls, free)
    return left, right, d, AffineSupport(width, 0, tuple(1 << i for i in range(free)))


def recheck(left, right, d, support, result):
    cert = tuple((c, tuple(tuple(p) for p in ps)) for c, ps in result['certificate'])
    fresh = check_factored_phase(left, right, d, cert, support=support)
    assert fresh['status'] == 'proved'
    assert fresh['source_sha256'] == result['source_sha256']
    assert fresh['certificate_sha256'] == result['certificate_sha256']
    return fresh


def run():
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    began = time.perf_counter()
    rows, negative, paired = [], [], []
    for matrix, offset, values in product(MATRICES, range(4), VALUES):
        left, right, d, support = small_mixed(values, matrix, offset)
        answer = discover_factored_phase(left, right, d, support=support)
        assert answer['status'] == 'proved' and same_channel(left, right, d, columns=support.columns)
        rows.append({'matrix': matrix, 'offset': offset, 'values': values, 'result': answer,
                     'external_recheck': recheck(left, right, d, support, answer), 'oracle_equal': True})
    for matrix, offset in product(MATRICES, range(4)):
        left, right, d, support = small_mixed((0, 1, 2, 3), matrix, offset)
        good = discover_factored_phase(left, right, d, support=support)
        left.phase(0, Fraction(1, 4))
        bad = check_factored_phase(left, right, d, good['certificate'], support=support)
        found = discover_factored_phase(left, right, d, support=support)
        assert bad['status'] == 'not_proved' and found['status'] == 'not_proved'
        assert not same_channel(left, right, d, columns=support.columns)
        negative.append({'matrix': matrix, 'offset': offset, 'check': bad, 'discovery': found,
                         'oracle_different': True})
    rng = random.Random(16610)
    for degree in (3, 5, 8, 12, 16, 32):
        for repetition in range(3):
            for kind in ('star', 'chain'):
                left, right, d, support = mixed_family(degree, kind)
                modes = ['factored', 'expanded_cegis']
                rng.shuffle(modes)
                for mode in modes:
                    before = time.perf_counter()
                    if mode == 'factored':
                        answer = discover_factored_phase(left, right, d, support=support, max_items=10000)
                    else:
                        answer = discover_adaptive_phase(left, right, d, support=support,
                                                          source_monomials=True, max_samples=64,
                                                          max_features=256)
                    row = {'degree': degree, 'kind': kind, 'mode': mode, 'repetition': repetition,
                           'expanded_anf_terms': 1 << (degree - 1),
                           'seconds': time.perf_counter() - before, 'result': answer}
                    if mode == 'factored':
                        assert answer['status'] == 'proved', answer
                        assert len(answer['certificate']) == 1
                        assert len(answer['certificate'][0][1]) == 1
                        assert len(answer['certificate'][0][1][0]) == degree
                        row['external_recheck'] = recheck(left, right, d, support, answer)
                    else:
                        assert answer['status'] in ('proved', 'inconclusive'), answer
                        if answer['status'] == 'proved':
                            from benchmarks.phase_adaptive import fresh

                            row['external_recheck'] = fresh(left, right, d, support, answer)
                    row['qualified'] = True
                    paired.append(row)
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/phase_factored.py', 'src/symq/labs/phase_discovery.py',
             'src/symq/labs/nonlinear_phase_bits.py', 'src/symq/labs/affine_phase.py',
             'src/symq/labs/kraus_graph.py', 'src/symq/labs/phase_adaptive.py',
             'src/symq/labs/phase_separator.py', 'benchmarks/phase_factored.py',
             'tests/test_phase_factored.py', 'tests/testkit/affine_phase_oracle.py',
             'tests/testkit/nonlinear_phase_cases.py')
    return {'passed': True, 'positive_cases': len(rows), 'negative_cases': len(negative),
            'rows': rows, 'negative': negative, 'paired': paired,
            'seconds': time.perf_counter() - began, 'python': platform.python_version(),
            'platform': platform.platform(),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'constructed development, no holdout, real loader or uniform speedup'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
    except Exception as error:  # noqa: BLE001 - preserve failed qualifications
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'negative', 'paired', 'sources')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
