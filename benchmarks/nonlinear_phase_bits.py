"""Development qualification for source-bound nonlinear signature bit certificates."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import time
from fractions import Fraction
from itertools import product
from pathlib import Path

from symq.labs.nonlinear_phase_bits import check_nonlinear_phase
from tests.testkit.affine_phase_oracle import same_channel
from tests.testkit.nonlinear_phase_cases import candidate, fixture


def run():
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    began = time.perf_counter()
    rows = []
    for values in product(range(4), repeat=4):
        left, right, d, support = fixture(values)
        result = check_nonlinear_phase(left, right, d, candidate(values), support=support)
        oracle_ok = same_channel(left, right, d, columns=support.columns)
        assert result['status'] == 'proved' and oracle_ok, (values, result)
        rows.append({'values': values, 'oracle_ok': oracle_ok, 'result': result})
    mutations = []
    for values in ((0, 1, 2, 3), (0, 1, 0, 1), (3, 1, 2, 0), (1, 3, 0, 2)):
        left, right, d, support = fixture(values)
        left.phase(0, Fraction(1, 4))
        result = check_nonlinear_phase(left, right, d, candidate(values), support=support)
        oracle_ok = not same_channel(left, right, d, columns=support.columns)
        assert result['status'] == 'not_proved' and oracle_ok
        mutations.append({'values': values, 'oracle_difference': oracle_ok, 'result': result})
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/nonlinear_phase_bits.py', 'src/symq/labs/kraus_graph.py',
             'src/symq/labs/affine_phase.py', 'benchmarks/nonlinear_phase_bits.py',
             'tests/testkit/nonlinear_phase_cases.py', 'tests/testkit/affine_phase_oracle.py')
    return {'passed': True, 'positive_cases': len(rows), 'positive_matrix_units': len(rows) * 64,
            'negative_cases': len(mutations), 'rows': rows, 'mutations': mutations,
            'seconds': time.perf_counter() - began, 'python': platform.python_version(),
            'platform': platform.platform(),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'constructed development; no synthesis, holdout, general scaling or independent UNSAT proof'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run()
    except Exception as error:  # noqa: BLE001 - preserve failed qualification
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'mutations')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
