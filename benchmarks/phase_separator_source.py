"""Paired source-monomial seeding on the retained high-degree discovery frontier."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import random
import time
from fractions import Fraction
from pathlib import Path

from benchmarks.phase_adaptive import fresh
from symq.labs.affine_phase import AffineSupport
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.phase import PhaseProgram


def family(degree):
    data = 2 * degree + 1
    left, right = DyadicPhaseProgram(data, k=3), DyadicPhaseProgram(data, k=3)
    d = PhaseProgram(data, 1)
    for i in range(degree):
        d.ccx(2 * i, 2 * i + 1, data).hmr(data)
    controls = tuple(range(2 * degree))
    left.mcx(*controls, data - 1).phase(data - 1, Fraction(1, 8)).mcx(*controls, data - 1)
    return left, right, d, AffineSupport(data, 0, tuple(1 << i for i in range(2 * degree)))


def run():
    if not __debug__:
        raise RuntimeError('assertions required')
    rng = random.Random(16607)
    began = time.perf_counter()
    rows = []
    for degree in (3, 5, 7, 9, 16, 32):
        left, right, d, support = family(degree)
        for repetition in range(3):
            modes = [(False, 'greedy'), (False, 'halving'), (True, 'greedy'), (True, 'halving')]
            rng.shuffle(modes)
            for seeded, separator in modes:
                row = {'degree': degree, 'source_seeded': seeded, 'separator': separator,
                       'repetition': repetition, 'sample_cap': 64, 'qualified': False}
                before = time.perf_counter()
                try:
                    answer = discover_adaptive_phase(left, right, d, support=support,
                                                      source_monomials=seeded, separator_strategy=separator,
                                                      max_samples=64, max_features=256)
                    row.update(seconds=time.perf_counter() - before, result=answer)
                    assert answer['status'] in ('proved', 'inconclusive'), answer
                    if seeded:
                        assert answer['status'] == 'proved', answer
                        assert answer['feature_count'] == degree + 2
                        assert answer['sample_count'] <= degree + 2
                        assert answer['source_seed_records'] == [
                            {'feature': (1 << degree) - 1, 'source_monomial': (1 << (2 * degree)) - 1}]
                        assert not answer['growth']
                    if answer['status'] == 'proved':
                        row['external_recheck'] = fresh(left, right, d, support, answer)
                    row['qualified'] = True
                except Exception as error:  # noqa: BLE001 - retain failures
                    row['error'] = f'{type(error).__name__}: {error}'
                rows.append(row)
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/phase_separator.py', 'src/symq/labs/phase_adaptive.py',
             'src/symq/labs/phase_discovery.py', 'src/symq/labs/nonlinear_phase_bits.py',
             'src/symq/labs/affine_phase.py', 'src/symq/labs/kraus_graph.py',
             'benchmarks/phase_separator_source.py')
    return {'passed': all(r['qualified'] for r in rows), 'rows': rows,
            'seconds': time.perf_counter() - began, 'python': platform.python_version(),
            'platform': platform.platform(),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'constructed single-monomial development case; seeding is restricted, not generic sparse learning'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
    except Exception as error:  # noqa: BLE001 - write failures
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'sources')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
