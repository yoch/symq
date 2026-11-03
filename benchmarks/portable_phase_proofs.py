"""Installed-package transport qualification, offline kernel and source-level checks.

All cases are constructed development cases, not a holdout or a real KMB loader.
The emitted standard DIMACS/LRAT pair can also be checked by a third-party tool.
"""
from __future__ import annotations

import argparse
import builtins
import hashlib
import importlib.metadata
import json
import platform
import subprocess
import sys
import time
from itertools import product
from pathlib import Path

from symq.labs import lrat_export, lrat_rup, phase_proof_bundle
from tests.test_lrat_rup import dimacs
from tests.test_phase_proof_bundle import source_case
from tests.testkit.affine_phase_oracle import same_channel


def run(destination):
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    from pysat.examples.genhard import PHP

    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    start = time.perf_counter()
    original_import = builtins.__import__

    def without_solver(name, *args, **kwargs):
        if name == 'pysat' or name.startswith('pysat.'):
            raise AssertionError('consumer tried to import a SAT solver')
        return original_import(name, *args, **kwargs)

    for index, values in enumerate(product(range(4), repeat=4)):
        row = {'values': values, 'qualified': False}
        try:
            left, right, d, candidate, support = source_case(values)
            before = time.perf_counter()
            pins = phase_proof_bundle.describe_factored_obligation(left, right, d, candidate,
                                                                  support=support)
            row['preparation_seconds'] = time.perf_counter() - before
            assert pins['status'] == 'ready'
            result = phase_proof_bundle.export_factored_proof(left, right, d, candidate, support=support)
            assert result['status'] == 'proved', result
            bundle = result['bundle']
            row['export_seconds'] = result['seconds']
            row['cnf_bytes'] = len(bundle['cnf'])
            row['lrat_bytes'] = len(bundle['lrat'])
            row['cnf_sha256'] = bundle['cnf_sha256']
            row['lrat_sha256'] = bundle['lrat_sha256']
            row['source_sha256'] = pins['source_sha256']
            row['certificate_sha256'] = pins['certificate_sha256']
            builtins.__import__ = without_solver
            try:
                checked = phase_proof_bundle.check_factored_proof(
                    left, right, d, candidate, bundle, support=support,
                    expected_source_sha256=pins['source_sha256'],
                    expected_certificate_sha256=pins['certificate_sha256'])
            finally:
                builtins.__import__ = original_import
            assert checked['status'] == 'proved' and checked['independent_unsat_checked'], checked
            assert same_channel(left, right, d, columns=support.columns)
            row['source_check_without_solver'] = checked
            row['oracle_equal'] = True
            row['qualified'] = True
            # Retain all proof objects, not just selected success summaries.
            (destination / f'phase-{index:03}.json').write_text(json.dumps(bundle, indent=2) + '\n')
            if index == 27:
                (destination / 'phase.cnf').write_text(bundle['cnf'])
                (destination / 'phase.lrat').write_text(bundle['lrat'])
        except Exception as error:  # noqa: BLE001 - every failed source row remains evidence
            row['error'] = f'{type(error).__name__}: {error}'
        rows.append(row)
    # A genuinely non-unit SAT refutation, independent of the source simplifier.
    php = PHP(nof_holes=3)
    cnf = dimacs(php.nv, php.clauses)
    generic = lrat_export.prove_cnf(cnf)
    assert generic['status'] == 'proof_checked' and generic['proof_steps'] > 1, generic
    (destination / 'php.cnf').write_text(cnf)
    (destination / 'php.lrat').write_text(generic['lrat'])
    checker_file = destination / 'lrat_rup.py'
    checker_file.write_bytes(Path(lrat_rup.__file__).read_bytes())
    standalone = subprocess.run(
        [sys.executable, '-I', '-S', str(checker_file), str(destination / 'php.cnf'),
         str(destination / 'php.lrat'), '--expected-cnf-sha256', generic['cnf_sha256']],
        capture_output=True, text=True, check=False, timeout=30)
    assert standalone.returncode == 0, (standalone.stdout, standalone.stderr)
    check = json.loads(standalone.stdout)
    assert check['verified_unsat']
    (destination / 'standalone.json').write_text(json.dumps(check, indent=2) + '\n')
    root = Path(__file__).resolve().parents[1]
    paths = ['src/symq/labs/lrat_rup.py', 'src/symq/labs/lrat_export.py',
             'src/symq/labs/phase_proof_bundle.py', 'src/symq/labs/kraus_graph.py',
             'src/symq/labs/phase_factored.py', 'src/symq/labs/phase_discovery.py',
             'src/symq/labs/nonlinear_phase_bits.py', 'src/symq/labs/affine_phase.py',
             'benchmarks/portable_phase_proofs.py', 'tests/test_phase_proof_bundle.py',
             'tests/testkit/nonlinear_phase_cases.py', 'tests/testkit/affine_phase_oracle.py']
    return {'passed': len(rows) == 256 and all(row['qualified'] for row in rows),
            'phase_cases': len(rows), 'positive_matrix_units': sum(row['qualified'] for row in rows) * 64,
            'rows': rows, 'generic': generic, 'standalone': check,
            'seconds': time.perf_counter() - start, 'python': platform.python_version(),
            'python_sat': importlib.metadata.version('python-sat'),
            'platform': platform.platform(),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'synthetic development; independent proof checking is not formal semantic-code verification'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.output_dir)
    except Exception as error:  # noqa: BLE001 - failed qualification must leave a report
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'sources', 'generic')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
