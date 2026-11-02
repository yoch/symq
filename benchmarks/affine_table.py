"""Synthetic wide correlated-target loader, independent literal table and qualification.

No private data or external compiler emission is included. The large fixture
is a representation regression, not certification of a production loader.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import platform
import random
import time
from itertools import product
from pathlib import Path

from benchmarks.anchored_kraus import contract, ideal, image, operation, program, random_source
from symq.labs.affine_table import affine_target_from_equations, verify_affine_table


def v2(spec, target_space):
    out = copy.deepcopy(spec)
    out.pop('target_values')
    out.update(kind='symq_affine_hmr_table_contract', schema_version=2, target_space=target_space)
    return out


def physical_inputs(spec):
    """Small independent enumeration used ONLY by the density oracle."""
    space = spec['target_space']
    words = []
    for u in range(1 << len(space['columns'])):
        word = space['offset']
        for j, column in enumerate(space['columns']):
            if u >> j & 1:
                word ^= column
        words.append(word)

    def pack(value, wires):
        return sum(((value >> j & 1) << q) for j, q in enumerate(wires))

    return [pack(a, spec['address_wires']) | pack(z, spec['target_wires']) | pack(d, spec['borrowed_wires'])
            for a, z, d in product(spec['legal_addresses'], words, range(1 << len(spec['borrowed_wires'])))]


def wide_fixture():
    """128 wires, 40 target bits of rank35, 1363 addresses, 89 HMR+89 zero resets."""
    equations = [[(1 << (8 * j + 6)) | (1 << (8 * j + 7)), 0] for j in range(5)]
    space = affine_target_from_equations(40, equations)
    # Literal specification computed arithmetically, not by simulating the candidate.
    table = []
    for address in range(2048):
        value = 0
        for word in range(5):
            low7 = sum(((address >> ((7 * word + bit) % 11) & 1) << bit) for bit in range(7))
            value |= (low7 | ((low7 >> 6) << 7)) << (8 * word)
        table.append(value if address < 1363 else None)
    spec = v2(contract(128, address=tuple(range(11)), target=tuple(range(11, 51)),
                       clean=tuple(range(51, 128)), borrowed=(), table=table,
                       legal=tuple(range(1363))), space)
    ops = []
    # This dephasing is harmless only on the declared repeated-bit subspace.
    ops.extend([operation('cx', 17, 51), operation('cx', 18, 51),
                operation('hmr', 51, slot='b0'), operation('reset', 51)])
    for event in range(1, 89):
        q = 51 + event % 77
        a, b = event % 11, (event + 1) % 11
        slot = f'b{event}'
        ops.extend([operation('ccx', a, b, q), operation('hmr', q, slot=slot),
                    operation('cz', a, b, condition=slot), operation('reset', q)])
    for word in range(5):
        for bit in range(8):
            ops.append(operation('cx', (7 * word + min(bit, 6)) % 11, 11 + 8 * word + bit))
    return program(51, 77, ops), spec


def run(programs=100, backends=('anf', 'sat')):
    if not __debug__:
        raise RuntimeError('assertions required for qualification')
    if type(programs) is not int or not 1 <= programs <= 1000:
        raise ValueError('programs must be in 1..1000')
    if not backends or any(b not in ('anf', 'sat') for b in backends):
        raise ValueError('explicit nonempty backend selection required')
    rng = random.Random(40589)
    counts = {b: {'cases': 0, 'positive': 0, 'negative': 0, 'witnesses': 0} for b in backends}
    spaces = [(0, (3,)), (1, (3,)), (2, (1,)), (3, ()), (0, (1, 2)), (1, (3, 2))]
    start = time.perf_counter()
    for _ in range(programs):
        src = random_source(rng)
        for offset, columns in spaces:
            spec = v2(contract(4, address=(0,), target=(1, 2), borrowed=(), clean=(3,),
                               table=(rng.randrange(4), rng.randrange(4))),
                      {'kind': 'affine_image', 'offset': offset, 'columns': list(columns)})
            inputs = physical_inputs(spec)
            outputs = {(x, y): image(src, x, y) for x, y in product(inputs, repeat=2)}
            truth = all(value == {(ideal(spec, x), ideal(spec, y)): 1} for (x, y), value in outputs.items())
            for backend, count in counts.items():
                result = verify_affine_table(src, spec, backend=backend)
                assert result['status'] in ('equivalent', 'not_proved'), result
                assert result['status'] == ('equivalent' if truth else 'not_proved')
                count['cases'] += 1
                count['positive' if truth else 'negative'] += 1
                if not truth:
                    witness = result['witness']
                    x, y = witness['input'], witness['anchor']
                    if result['obligation'] == 'outputs':
                        y = x
                    assert x in inputs and y in inputs
                    assert outputs[x, y] != {(ideal(spec, x), ideal(spec, y)): 1}
                    count['witnesses'] += 1
    src, spec = wide_fixture()
    large = []
    for backend in backends:
        trials = [verify_affine_table(src, spec, backend=backend, max_seconds=30) for _ in range(3)]
        assert all(r['status'] == 'equivalent' for r in trials), trials
        assert all(r['eliminated_events'] == 89 and r['target_dimension'] == 35 for r in trials)
        wide = copy.deepcopy(spec)
        wide['target_space'] = affine_target_from_equations(40, [])
        invalid = verify_affine_table(src, wide, backend=backend, max_seconds=30)
        assert invalid['status'] == 'not_proved', invalid
        large.append({'backend': backend, 'trials': trials, 'widened_target': invalid})
    paths = ['src/symq/labs/affine_table.py', 'src/symq/labs/anchored_stream.py',
             'src/symq/labs/anchored_kraus.py', 'src/symq/labs/kraus_graph.py',
             'benchmarks/affine_table.py', 'benchmarks/anchored_kraus.py']
    root = Path(__file__).resolve().parents[1]
    return {'passed': True, 'random_seed': 40589, 'differential': counts, 'wide': large,
            'seconds': time.perf_counter() - start, 'python': platform.python_version(),
            'platform': platform.platform(),
            'sources': {p: hashlib.sha256((root / p).read_bytes()).hexdigest() for p in paths},
            'scope': 'synthetic development only; real loader neither imported nor certified'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--programs', type=int, default=100)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = run(args.programs)
    except Exception as error:  # noqa: BLE001 - preserve failed qualification
        report = {'passed': False, 'error': f'{type(error).__name__}: {error}'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k not in ('wide', 'sources')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
