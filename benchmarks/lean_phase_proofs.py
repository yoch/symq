"""Generate source-bound proof data, then qualify Lean after removing the SAT package.

Only a selected small corpus is checked here; ordinary kernel reduction may be
costly. Every Lean process receives locally generated numeral/list-only text.
The Lean theorem is about that exact CNF, not the full quantum implementation.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import re
import subprocess
import time
from pathlib import Path

from symq.labs.lrat_lean import LEAN_COMMIT, LEAN_TOOLCHAIN, emit_lean

SELECTED = (0, 27, 31, 63, 95, 127, 191, 255)
ALLOWED_AXIOMS = {'propext', 'Quot.sound', 'Classical.choice'}


def digest(text):
    return hashlib.sha256(text.encode('ascii')).hexdigest()


def generate(destination):
    from pysat.examples.genhard import PHP

    from symq.labs.lrat_export import prove_cnf
    from symq.labs.phase_proof_bundle import describe_factored_obligation, export_factored_proof
    from tests.test_lrat_rup import dimacs
    from tests.test_phase_proof_bundle import source_case

    destination.mkdir(parents=True, exist_ok=True)
    rows = []

    def save(name, cnf, lrat, expected, pins=None, values=None):
        emitted = emit_lean(cnf, lrat, expected_cnf_sha256=digest(cnf))
        assert emitted['status'] == 'emitted' and not emitted['verified_unsat'], emitted
        (destination / f'{name}.cnf').write_text(cnf)
        (destination / f'{name}.lrat').write_text(lrat)
        (destination / f'{name}.lean').write_text(emitted['lean_source'])
        rows.append({'name': name, 'expected_unsat_proof': expected,
                     'cnf_sha256': digest(cnf), 'lrat_sha256': digest(lrat),
                     'lean_sha256': emitted['lean_sha256'], 'pins': pins, 'values': values,
                     'steps': emitted['steps'], 'clauses': emitted['input_clauses']})

    for index in SELECTED:
        values = tuple((index >> (2 * j)) & 3 for j in (3, 2, 1, 0))
        left, right, dephaser, candidate, support = source_case(values)
        pins = describe_factored_obligation(left, right, dephaser, candidate, support=support)
        assert pins['status'] == 'ready', pins
        produced = export_factored_proof(left, right, dephaser, candidate, support=support)
        assert produced['status'] == 'proved', produced
        bundle = produced['bundle']
        assert bundle['cnf'] == pins['cnf'] and bundle['cnf_sha256'] == pins['cnf_sha256']
        name = f'phase_{index:03}'
        (destination / f'{name}.json').write_text(json.dumps(bundle, indent=2) + '\n')
        save(name, bundle['cnf'], bundle['lrat'], True,
             {key: pins[key] for key in ('source_sha256', 'certificate_sha256', 'cnf_sha256')}, values)
    php = PHP(nof_holes=3)
    cnf = dimacs(php.nv, php.clauses)
    proof = prove_cnf(cnf)
    assert proof['status'] == 'proof_checked' and proof['proof_steps'] > 1, proof
    save('pigeonhole', cnf, proof['lrat'], True)
    save('empty_input_clause', 'p cnf 0 1\n0\n', '2 0 1 0\n', True)
    save('unused_variable_holes', 'p cnf 9 2\n9 0\n-9 0\n', '3 0 1 2 0\n', True)
    # Syntax-valid but semantically invalid certificates. A compiler failure
    # caused by bad environment is not counted as the requested rejection.
    save('bad_missing_conflict', 'p cnf 1 2\n1 0\n-1 0\n', '3 0 1 0\n', False)
    save('bad_nonunit_hints', 'p cnf 2 2\n1 2 0\n-1 2 0\n', '3 0 1 2 0\n', False)
    save('bad_changed_polarity', 'p cnf 1 2\n1 0\n1 0\n', '3 0 1 2 0\n', False)
    report = {'generated': True, 'proof_checked_by_lean': False, 'rows': rows,
              'toolchain': LEAN_TOOLCHAIN, 'lean_source_commit': LEAN_COMMIT,
              'selection': list(SELECTED), 'source_cases': len(SELECTED)}
    (destination / 'manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def axiom_audit(text, theorem):
    if theorem not in text or 'sorryAx' in text or 'Lean.ofReduce' in text or 'Lean.trustCompiler' in text:
        raise AssertionError('missing theorem or unexpected axiom in Lean output')
    matches = re.findall(r'depends on axioms:\s*\[([^\]]*)\]', text, re.DOTALL)
    if not matches and 'does not depend on any axioms' not in text:
        raise AssertionError('no axiom report found')
    used = {entry.strip() for group in matches for entry in group.split(',') if entry.strip()}
    if not used <= ALLOWED_AXIOMS:
        raise AssertionError(f'unexpected axioms: {used - ALLOWED_AXIOMS}')
    return sorted(used)


def refusal_source(positive_skeleton):
    """Fixed second theorem: the well-typed invalid trace is rejected by LRAT."""
    old = ('theorem claim : formula.Unsat :=\n'
           '  Std.Tactic.BVDecide.LRAT.check_sound witness formula (by decide +kernel)\n\n'
           '#print axioms claim')
    new = ('theorem rejection : Std.Tactic.BVDecide.LRAT.check witness formula = false := by\n'
           '  decide +kernel\n\n#print axioms rejection')
    if positive_skeleton.count(old) != 1:
        raise AssertionError('unexpected generated proof skeleton')
    return positive_skeleton.replace(old, new)


def qualify(destination, formal_directory):
    # Genuine package absence, not only an import monkeypatch.
    assert importlib.util.find_spec('pysat') is None
    from symq.labs.phase_proof_bundle import check_factored_proof, describe_factored_obligation
    from tests.test_phase_proof_bundle import source_case

    destination, formal_directory = destination.resolve(), formal_directory.resolve()
    version = subprocess.run(['lean', '--version'], cwd=formal_directory, capture_output=True,
                             text=True, timeout=30, check=True).stdout.strip()
    assert 'version 4.19.0' in version and LEAN_COMMIT[:12] in version, version
    manifest = json.loads((destination / 'manifest.json').read_text())
    assert manifest['toolchain'] == LEAN_TOOLCHAIN and manifest['lean_source_commit'] == LEAN_COMMIT
    assert manifest['source_cases'] == len(SELECTED) and manifest['selection'] == list(SELECTED)
    assert len(manifest['rows']) == len(SELECTED) + 6
    expected_names = {f'phase_{i:03}' for i in SELECTED} | {
        'pigeonhole', 'empty_input_clause', 'unused_variable_holes',
        'bad_missing_conflict', 'bad_nonunit_hints', 'bad_changed_polarity'}
    assert {row['name'] for row in manifest['rows']} == expected_names
    for item in manifest['rows']:
        assert type(item['expected_unsat_proof']) is bool
        assert item['expected_unsat_proof'] is (not item['name'].startswith('bad_'))
        if item['name'].startswith('phase_'):
            index = int(item['name'].split('_')[1])
            assert item['values'] == [(index >> (2 * j)) & 3 for j in (3, 2, 1, 0)]
        else:
            assert item['values'] is None and item['pins'] is None
    gate_start = time.perf_counter()
    gates = subprocess.run(['lean', 'GateLemmas.lean'], cwd=formal_directory,
                           capture_output=True, text=True, timeout=90, check=False)
    (destination / 'gate-lemmas.log').write_text(gates.stdout + gates.stderr)
    assert gates.returncode == 0, (gates.stdout, gates.stderr)
    gate_axioms = axiom_audit(gates.stdout, 'SymQPortable.fibre_constancy')
    gate_seconds = time.perf_counter() - gate_start
    rows = []
    for item in manifest['rows']:
        row = {**item, 'qualified': False, 'lean_kernel_accepted': False}
        name = item['name']
        assert re.fullmatch(r'[a-zA-Z0-9_]+', name), name
        try:
            cnf = (destination / f'{name}.cnf').read_text()
            proof = (destination / f'{name}.lrat').read_text()
            assert digest(cnf) == item['cnf_sha256'] and digest(proof) == item['lrat_sha256']
            rendered = emit_lean(cnf, proof, expected_cnf_sha256=item['cnf_sha256'])
            assert rendered['status'] == 'emitted'
            # Never execute a Lean file that does not equal the fixed renderer's
            # numeral/list-only output, even if a manifest claims it is trusted.
            lean_text = (destination / f'{name}.lean').read_text()
            assert lean_text == rendered['lean_source']
            assert digest(lean_text) == item['lean_sha256']
            if item['values'] is not None:
                left, right, d, candidate, support = source_case(tuple(item['values']))
                current = describe_factored_obligation(left, right, d, candidate, support=support)
                assert current['status'] == 'ready' and current['cnf'] == cnf
                assert {key: current[key] for key in item['pins']} == item['pins']
                bundle = json.loads((destination / f'{name}.json').read_text())
                checked = check_factored_proof(left, right, d, candidate, bundle, support=support,
                    expected_source_sha256=current['source_sha256'],
                    expected_certificate_sha256=current['certificate_sha256'])
                assert checked['status'] == 'proved' and checked['independent_unsat_checked']
                row['solver_free_source_check'] = checked
            before = time.perf_counter()
            proc = subprocess.run(['lean', f'--root={destination}', '-o', str(destination / f'{name}.olean'),
                                   str(destination / f'{name}.lean')], cwd=formal_directory,
                                  capture_output=True, text=True, timeout=90, check=False)
            row['lean_seconds'] = time.perf_counter() - before
            output = proc.stdout + proc.stderr
            (destination / f'{name}.log').write_text(output)
            row['exit_code'] = proc.returncode
            if item['expected_unsat_proof']:
                assert proc.returncode == 0, output
                row['axioms'] = axiom_audit(output, 'SymQPortable.claim')
                row['lean_kernel_accepted'] = True
            else:
                assert proc.returncode != 0 and 'error:' in output and 'decide' in output, output
                assert not any(s in output for s in ('unknown module', 'unknown identifier', 'file not found')), output
                # An arbitrary failure is not enough: separately prove the actual
                # Boolean checker returns false, using the SAME literal data.
                rejected_text = refusal_source(lean_text)
                rejected_path = destination / f'{name}_rejected.lean'
                rejected_path.write_text(rejected_text)
                refused = subprocess.run(['lean', f'--root={destination}', '-o',
                                          str(destination / f'{name}_rejected.olean'),
                                          str(rejected_path)], cwd=formal_directory,
                                         capture_output=True, text=True, timeout=90, check=False)
                rejected_log = refused.stdout + refused.stderr
                (destination / f'{name}_rejected.log').write_text(rejected_log)
                assert refused.returncode == 0, rejected_log
                row['rejection_axioms'] = axiom_audit(rejected_log, 'SymQPortable.rejection')
                row['rejection_lean_sha256'] = digest(rejected_text)
                row['checker_rejection_proved'] = True
                row['semantic_proof_refused'] = True
            row['qualified'] = True
        except Exception as error:  # noqa: BLE001 - retain every failed proof or infrastructure check
            row['error'] = f'{type(error).__name__}: {error}'
        rows.append(row)
    root = Path(__file__).resolve().parents[1]
    paths = ('src/symq/labs/lrat_lean.py', 'src/symq/labs/lrat_rup.py',
             'src/symq/labs/phase_proof_bundle.py', 'benchmarks/lean_phase_proofs.py',
             'formal/portable_lrat/GateLemmas.lean', 'formal/portable_lrat/lean-toolchain')
    return {'passed': len(rows) == len(SELECTED) + 6 and all(r['qualified'] for r in rows),
            'lean_version': version, 'lean_source_commit': LEAN_COMMIT,
            'pysat_absent': True, 'rows': rows, 'gate_lemmas_axioms': gate_axioms,
            'gate_lemmas_seconds': gate_seconds,
            'kernel_accepted_count': sum(r['lean_kernel_accepted'] for r in rows),
            'python': platform.python_version(), 'platform': platform.platform(),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'Lean theorem for rendered CNF; no end-to-end formal source/encoder/Python theorem'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['generate', 'check'])
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--formal-directory', type=Path, default=Path('formal/portable_lrat'))
    args = parser.parse_args()
    if not __debug__:
        raise RuntimeError('qualification requires assertions')
    args.output_dir.mkdir(parents=True, exist_ok=True)
    try:
        report = generate(args.output_dir) if args.mode == 'generate' else qualify(args.output_dir, args.formal_directory)
    except Exception as error:  # noqa: BLE001 - keep setup failures
        report = {'passed': False, 'generated': False, 'error': f'{type(error).__name__}: {error}'}
    name = 'generation.json' if args.mode == 'generate' else 'lean-qualification.json'
    (args.output_dir / name).write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('rows', 'sources')}))
    return 0 if report.get('generated' if args.mode == 'generate' else 'passed', False) else 1


if __name__ == '__main__':
    raise SystemExit(main())
