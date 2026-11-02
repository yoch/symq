"""Independent rational density oracle and reproducible development campaign."""
import argparse
import copy
import hashlib
import json
import platform
import random
import time
from fractions import Fraction
from itertools import product
from pathlib import Path

from symq.labs.anchored_kraus import verify


def operation(kind, *wires, slot=None, condition=None, source=None, value=None):
    return {'kind': kind, 'wires': list(wires), 'slot': slot, 'condition': condition, 'source': source, 'value': value}


def program(data, ancillas=0, ops=()):
    return {'kind': 'hybrid', 'schema_version': 1, 'data': data, 'ancillas': ancillas, 'ops': list(ops)}


def contract(width=4, address=(0,), target=(1,), clean=(3,), borrowed=(2,), table=(0, 1), legal=(0, 1), targets=None):
    return {'kind': 'symq_hmr_table_contract', 'schema_version': 1, 'width': width, 'address_wires': list(address), 'target_wires': list(target), 'clean_wires': list(clean), 'borrowed_wires': list(borrowed), 'table': list(table), 'legal_addresses': list(legal), 'target_values': None if targets is None else list(targets), 'bit_order': 'lsb_first', 'records': 'forgotten', 'outputs': 'all_retained'}


def states(spec):
    def pack(wires, v):
        return sum(((v >> j & 1) << q for j, q in enumerate(wires)))
    targets = range(1 << len(spec['target_wires'])) if spec['target_values'] is None else spec['target_values']
    return [pack(spec['address_wires'], a) | pack(spec['target_wires'], z) | pack(spec['borrowed_wires'], d) for a, z, d in product(spec['legal_addresses'], targets, range(1 << len(spec['borrowed_wires'])))]


def ideal(spec, x):
    a = sum(((x >> q & 1) << i for i, q in enumerate(spec['address_wires'])))
    row = spec['table'][a]
    return x ^ sum(((row >> i & 1) << q for i, q in enumerate(spec['target_wires'])))


def image(src, x, y):
    """E(|x><y|) as a sparse exact density matrix, NOT a ket-trajectory check."""
    terms = {(x, y, ()): Fraction(1)}
    for op in src['ops']:
        out = {}

        def add(r, c, m, v, out=out):
            key = (r, c, tuple(sorted(m.items())))
            out[key] = out.get(key, Fraction(0)) + v
            if not out[key]:
                del out[key]
        for (r, c, items), amplitude in terms.items():
            memory = dict(items)
            name = op['condition']
            cond = True if name is None else not memory[name[1:]] if name.startswith('!') else bool(memory[name])
            kind, ws = (op['kind'], op['wires'])
            if kind in ('hmr', 'measure_z', 'reset'):
                q = ws[0]
                br = r >> q & 1
                bc = c >> q & 1
                bit = 1 << q
                if kind == 'hmr':
                    for event in (0, 1):
                        mem = dict(memory)
                        mem[op['slot']] = event
                        factor = Fraction(-1 if event and br != bc else 1, 2)
                        add(r & ~bit, c & ~bit, mem, amplitude * factor)
                elif br == bc:
                    if kind == 'measure_z':
                        memory[op['slot']] = br
                        add(r, c, memory, amplitude)
                    else:
                        add(r & ~bit, c & ~bit, memory, amplitude)
            elif kind in ('store', 'invert', 'oxor'):
                if kind == 'store':
                    memory[op['slot']] = op['value']
                elif kind == 'invert':
                    memory[op['slot']] ^= int(cond)
                else:
                    memory[op['slot']] ^= memory[op['source']]
                add(r, c, memory, amplitude)
            elif not cond:
                add(r, c, memory, amplitude)
            elif kind in ('z', 'cz', 'ccz', 'neg'):
                sign_r = all(r >> q & 1 for q in ws)
                sign_c = all(c >> q & 1 for q in ws)
                add(r, c, memory, -amplitude if sign_r != sign_c else amplitude)
            else:
                def perm(v, kind=kind, ws=ws):
                    if kind in ('x', 'cx', 'ccx', 'mcx'):
                        return v ^ 1 << ws[-1] if all(v >> q & 1 for q in ws[:-1]) else v
                    a, b = ws[-2:]
                    enable = kind == 'swap' or bool(v >> ws[0] & 1)
                    return v ^ (1 << a | 1 << b) if enable and (v >> a ^ v >> b) & 1 else v
                add(perm(r), perm(c), memory, amplitude)
        terms = out
    out = {}
    for (r, c, _), v in terms.items():
        out[r, c] = out.get((r, c), Fraction(0)) + v
    return {key: v for key, v in out.items() if v}


def random_source(rng):
    src = program(3, 1)
    ops = src['ops']
    slots = []
    for _ in range(rng.randrange(1, 10)):
        action = rng.randrange(10)
        cond = rng.choice(slots + [None]) if slots else None
        if cond is not None and rng.random() < 0.3:
            cond = '!' + cond
        if action < 3:
            k = rng.choice(('x', 'cx', 'ccx', 'swap', 'cswap'))
            n = {'x': 1, 'cx': 2, 'ccx': 3, 'swap': 2, 'cswap': 3}[k]
            ops.append(operation(k, *rng.sample(range(4), n), condition=cond))
        elif action < 5:
            k = rng.choice(('z', 'cz', 'ccz', 'neg'))
            n = {'z': 1, 'cz': 2, 'ccz': 3, 'neg': 0}[k]
            ops.append(operation(k, *rng.sample(range(4), n), condition=cond))
        elif action < 8:
            k = rng.choice(('hmr', 'measure_z', 'reset'))
            if k == 'reset':
                ops.append(operation(k, rng.randrange(4)))
            else:
                slot = rng.choice(slots) if slots and rng.random() < 0.3 else 'b' + str(len(slots))
                ops.append(operation(k, rng.randrange(4), slot=slot))
                if slot not in slots:
                    slots.append(slot)
        elif action == 8 and slots:
            dest = rng.choice(slots)
            if rng.random() < 0.5:
                ops.append(operation('invert', slot=dest, condition=cond))
            else:
                ops.append(operation('oxor', slot=dest, source=rng.choice(slots)))
        else:
            slot = 'b' + str(len(slots))
            slots.append(slot)
            ops.append(operation('store', slot=slot, value=rng.randrange(2)))
    return src


def chain(h):
    src = program(4, 1)
    for j in range(h):
        name = f'b{j}'
        src['ops'] += [operation('ccx', 0, 1, 4), operation('cx', 4, 2), operation('hmr', 4, slot=name), operation('cz', 0, 1, condition=name)]
    spec = contract(5, address=(0, 1), target=(2,), clean=(4,), borrowed=(3,), table=(0, 0, 0, h % 2), legal=(0, 1, 2, 3))
    return (src, spec)


def campaign(programs=200, seed=159):
    if not __debug__:
        raise RuntimeError('qualification requires assertions enabled')
    if type(programs) is not int or not 1 <= programs <= 10000:
        raise ValueError('programs must be an integer in 1..10000')
    rng = random.Random(seed)
    checked = 0
    positives = 0
    refutations = 0
    witnesses = 0
    cases = []
    began = time.perf_counter()
    for _index in range(programs):
        src = random_source(rng)
        images = {(x, y): image(src, x, y) for x, y in product(range(8), repeat=2)}
        for table in product(range(2), repeat=2):
            for legal in ((0,), (1,), (0, 1)):
                spec = contract(table=table, legal=legal)
                inputs = states(spec)
                correct = all((images[x, y] == {(ideal(spec, x), ideal(spec, y)): 1} for x, y in product(inputs, repeat=2)))
                result = verify(src, spec)
                assert result['status'] in ('equivalent', 'not_proved'), result
                assert (result['status'] == 'equivalent') == correct, (src, spec, result)
                if correct:
                    positives += 1
                else:
                    refutations += 1
                    w = result['witness']
                    x = w['input']
                    y = x if result['obligation'] == 'outputs' else w['anchor']
                    assert x in inputs and y in inputs
                    assert images[x, y] != {(ideal(spec, x), ideal(spec, y)): 1}, (src, spec, result)
                    witnesses += 1
                checked += 1
    for h in (1, 4, 16, 32, 64, 128, 256):
        src, spec = chain(h)
        trials = [verify(src, spec) for _ in range(3)]
        assert all(t['status'] == 'equivalent' for t in trials)
        if h <= 4:
            assert all((image(src, x, y) == {(ideal(spec, x), ideal(spec, y)): 1} for x, y in product(states(spec), repeat=2)))
        bad = copy.deepcopy(src)
        bad['ops'].pop()
        fail = verify(bad, spec)
        assert fail['status'] == 'not_proved' and fail['obligation'] == 'branch_phase', fail
        cases.append({'hmr': h, 'branches': str(2 ** h), 'trial_seconds': [r['seconds'] for r in trials], 'peak_terms': [r['peak_terms'] for r in trials], 'products': [r['products'] for r in trials], 'negative_status': fail['status']})
    n = 12
    src = program(n + 1, 0, [operation('measure_z', q, slot=f'b{q}') for q in range(n)])
    spec = contract(n + 1, address=(0,), target=(n,), clean=(), borrowed=tuple(range(1, n)), table=(0, 0))
    adverse = verify(src, spec, max_terms=5000, max_products=100000)
    assert adverse['status'] == 'inconclusive', adverse
    assert image(src, 0, 1) != {(0, 1): 1}
    src, spec = chain(1)
    assert verify(src, spec, max_seconds=1e-12)['status'] == 'inconclusive'
    for key, val in [('legal_addresses', []), ('table', [0]), ('width', True), ('records', 'visible')]:
        altered = copy.deepcopy(spec)
        altered[key] = val
        try:
            verify(src, altered)
        except ValueError:
            pass
        else:
            raise AssertionError(('invalid accepted', key))
    out = {'passed': True, 'seed': seed, 'programs': programs, 'differential_cases': checked, 'positives': positives, 'refutations': refutations, 'checked_witnesses': witnesses, 'scaling': cases, 'adverse': adverse, 'seconds': time.perf_counter() - began, 'python': platform.python_version(), 'platform': platform.platform(), 'scope': 'synthetic development only; not a holdout or external comparison', 'sources': {'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), 'engine_sha256': hashlib.sha256(Path(verify.__code__.co_filename).read_bytes()).hexdigest()}}
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--programs', type=int, default=400)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        result = campaign(args.programs)
    except Exception as error:
        result = {'passed': False, 'error': repr(error)}
        args.output.write_text(json.dumps(result, indent=2) + '\n')
        raise
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'scaling'}, indent=2))
    for row in result['scaling']:
        print(row)
