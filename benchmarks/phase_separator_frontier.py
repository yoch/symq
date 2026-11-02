"""Retained negative frontier: low-degree refinement can require exponentially many samples."""
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
from benchmarks.phase_separator import validate_bound
from symq.labs.affine_phase import AffineSupport
from symq.labs.dyadic_phase import DyadicPhaseProgram
from symq.labs.phase_adaptive import discover_adaptive_phase
from symq.phase import PhaseProgram


def conjunction_family(size):
    """Full signature image h_i=a_i*b_i; delta=product(h_i) mod8 is one monomial."""
    if type(size) is not int or not 2 <= size <= 16:
        raise ValueError('research fixture size must be in 2..16')
    free, width = 2 * size, 2 * size + 1
    left, right = DyadicPhaseProgram(width, k=3), DyadicPhaseProgram(width, k=3)
    dephaser = PhaseProgram(width, 1)
    for i in range(size):
        dephaser.ccx(2 * i, 2 * i + 1, width).hmr(width)
    controls = tuple(range(free))
    left.mcx(*controls, free).phase(free, Fraction(1, 8)).mcx(*controls, free)
    return left, right, dephaser, AffineSupport(width, 0, tuple(1 << i for i in range(free)))


def run():
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    rows = []
    rng = random.Random(16605)
    began = time.perf_counter()
    for degree in (3, 5, 7, 9):
        left, right, d, support = conjunction_family(degree)
        # A common finite cap is deliberate: do not silently relax it for one method.
        for repetition in range(3):
            order = ['greedy', 'halving']
            rng.shuffle(order)
            for method in order:
                row = {'degree': degree, 'method': method, 'repetition': repetition,
                       'sample_cap': 64, 'necessary_halving_samples': 1 << degree,
                       'qualified': False}
                before = time.perf_counter()
                try:
                    result = discover_adaptive_phase(left, right, d, support=support,
                                                      separator_strategy=method,
                                                      max_samples=64, max_features=256)
                    row.update(seconds=time.perf_counter() - before, result=result)
                    assert result['status'] in ('proved', 'inconclusive'), result
                    if result['status'] == 'proved':
                        row['external_recheck'] = fresh(left, right, d, support, result)
                        if method == 'halving':
                            assert result['sample_count'] >= 1 << degree
                            validate_bound(result)
                    if method == 'halving' and degree >= 7:
                        assert result['status'] == 'inconclusive', result
                    row['qualified'] = True
                except Exception as error:  # noqa: BLE001 - evidence retains regressions
                    row['error'] = f'{type(error).__name__}: {error}'
                rows.append(row)
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/phase_separator.py', 'src/symq/labs/phase_adaptive.py',
             'src/symq/labs/phase_discovery.py', 'src/symq/labs/nonlinear_phase_bits.py',
             'src/symq/labs/affine_phase.py', 'src/symq/labs/kraus_graph.py',
             'benchmarks/phase_separator_frontier.py')
    return {'passed': all(r['qualified'] for r in rows), 'rows': rows,
            'seconds': time.perf_counter() - began, 'python': platform.python_version(),
            'platform': platform.platform(),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'constructed negative frontier; not a general sparse-learning lower bound'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
    except Exception as error:  # noqa: BLE001 - retain setup failure
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'sources')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
