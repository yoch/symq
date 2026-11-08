"""Pinned bounded KMB cache splice with a new reset-prepared wire and private bit.

Global context accepts the resource-frontier grammar; selected windows are flat
signed monomial instructions (INFO_TAGs retained). No prefix state is assumed.
The theorem is original tensor reset on one new wire, after forgetting one new
classical result. The returned plan/candidate never promotes or submits itself.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat
import struct
from contextlib import nullcontext
from pathlib import Path

from symq.errors import ResourceLimitExceeded, UnsupportedOperation
from symq.experimental.serialization import parse_json
from symq.hashing import canonical_sha256
from symq.labs import kmb_resource_frontier as frontier
from symq.labs import kmb_window as binary
from symq.labs.channel_composition import HybridFragment
from symq.labs.reset_cache import _columns, cache_request, prove_reset_cache
from symq.labs.rewrite import ReceiptMismatch, call_budget
from symq.resources import Budget, VerificationSession

__all__ = ["prove_kmb_reset_cache", "replay_kmb_reset_cache"]
_KIND = "symq_kmb_reset_cache_site"
_GROUPS = {3: (2, 3, 4), 2: (5, 6), 1: (7,)}


def _extract(np, view, info, packets, a, b, guard):
    # Counts/depth are streamed from the origin. No prefix circuit is materialized.
    counts, raw, low, depths = [0] * 5, 0, 0, {}
    for at in range(0, b, 1 << 20):
        guard.check_time()
        end = min(b, at + (1 << 20))
        types = np.frombuffer(view[packets[1] + at:packets[1] + end], dtype='u1')
        before, raw, low = frontier._depths(np, types, raw, low)
        if at <= a < end:
            depths[a] = int(before[a - at])
        if end == b:
            depths[b] = raw - min(0, low)
        prefix = types[:max(0, min(end, a) - at)]
        for pos, arity in enumerate((3, 2, 1)):
            counts[pos] += int(np.count_nonzero((prefix & 48) == 16 * arity))
        counts[3] += int(np.count_nonzero(prefix & 64))
        counts[4] += int(np.count_nonzero(prefix & 128))
    if depths != {a: 0, b: 0}:
        raise UnsupportedOperation('cache window must have an empty outer condition stack at both cuts')
    initial, records = list(counts), []
    for i in range(a, b):
        guard.check_time()
        code = view[packets[1] + i]
        if code in (1, 129):
            raise UnsupportedOperation('condition-stack operations inside the local window are not supported')
        arity = (code & 48) // 16
        qs = ()
        if arity:
            pos = 3 - arity
            qs = tuple(struct.unpack_from('<I', view, packets[p] + 4 * counts[pos])[0] for p in _GROUPS[arity])
            counts[pos] += 1
        bits = []
        for flag, packet, pos in ((64, 8, 3), (128, 9, 4)):
            bit = None
            if code & flag:
                bit = struct.unpack_from('<I', view, packets[packet] + 4 * counts[pos])[0]
                counts[pos] += 1
            bits.append(bit)
        records.append((code, qs, *bits))
    return records, initial


def _fragment(records, wires):
    mapping = {q: i for i, q in enumerate(wires)}
    ops, inputs, written, positions = [], set(), set(), []
    for i, (code, qs, bit, condition) in enumerate(records):
        if code == 6:
            continue
        kind = binary._OPS[code]
        op = binary._hop(kind, qs, bit, condition, mapping)
        for read in (op.condition.removeprefix('!') if op.condition else None,
                     op.slot if op.kind == 'invert' else None):
            if read is not None and read not in written:
                inputs.add(read)
        if op.slot is not None:
            written.add(op.slot)
        positions.append(i)
        ops.append(op)
    return HybridFragment(len(wires), tuple(ops), tuple(sorted(inputs))), positions


def _buffers(records):
    values = {k: bytearray() for k in range(1, 10)}
    for code, qs, bit, condition in records:
        values[1].append(code)
        for packet, q in zip(_GROUPS.get(len(qs), ()), qs):
            values[packet].extend(struct.pack('<I', q))
        for packet, value in ((8, bit), (9, condition)):
            if value is not None:
                values[packet].extend(struct.pack('<I', value))
    return values


def _candidate_records(records, pair, q, m):
    out = [(18, (q,), None, None)]
    for i, record in enumerate(records):
        _code, qs, _bit, _cond = record
        if i == pair[0]:
            out += [(49, (*qs[:2], q), None, None), (33, (q, qs[2]), None, None)]
        elif i == pair[1]:
            out += [(33, (q, qs[2]), None, None), (80, (q,), m, None), (160, qs[:2], None, m)]
        else:
            out.append(record)
    return out


def _emit(view, packets, old, new, start, counts, guard, destination):
    # Only bounded windows are encoded. Unchanged packet spans stream verbatim.
    before, after = _buffers(old), _buffers(new)
    header = list(binary._HEADER.unpack_from(view))
    header[2] += 1
    header[3] += 1
    for field, packet, unit in ((5, 1, 1), (6, 2, 4), (7, 5, 4), (8, 7, 4), (9, 8, 4), (10, 9, 4)):
        header[field] += (len(after[packet]) - len(before[packet])) // unit
    offsets = {1: start, 2: counts[0] * 4, 3: counts[0] * 4, 4: counts[0] * 4,
               5: counts[1] * 4, 6: counts[1] * 4, 7: counts[2] * 4, 8: counts[3] * 4, 9: counts[4] * 4}
    digest, size = hashlib.sha256(), 0
    output = destination
    try:
        def write(data):
            nonlocal size
            for at in range(0, len(data), 1 << 20):
                guard.check_time()
                block = data[at:at + (1 << 20)]
                if output is not None:
                    output.write(block)
                digest.update(block)
                size += len(block)
        write(binary._HEADER.pack(*header))
        for at in range(binary._HEADER.size, packets[1] - 16, 1 << 20):
            write(view[at:min(at + (1 << 20), packets[1] - 16)])
        for packet in range(1, 12):
            start_payload = packets[packet]
            length = struct.unpack_from('<Q', view, start_payload - 8)[0]
            if packet > 9:
                write(struct.pack('<QQ', packet, length))
                # Bounded slices avoid copying a whole packet in Python.
                for at in range(0, length, 1 << 20):
                    write(view[start_payload + at:start_payload + min(at + (1 << 20), length)])
                continue
            old_size, new_size = len(before[packet]), len(after[packet])
            write(struct.pack('<QQ', packet, length - old_size + new_size))
            split = offsets[packet]
            for lo, hi in ((0, split),):
                for at in range(lo, hi, 1 << 20):
                    write(view[start_payload + at:start_payload + min(at + (1 << 20), hi)])
            write(after[packet])
            for at in range(split + old_size, length, 1 << 20):
                write(view[start_payload + at:start_payload + min(at + (1 << 20), length)])
        if output is not None:
            output.flush()
        guard.check_time()
        return digest.hexdigest(), size, header[5]
    finally:
        if output is not None:
            output.close()


def _relation(candidate, pair_controls, n, guard):
    from itertools import product

    # Prove the actual cache value, not merely stability of its dependencies.
    event = next(i for i, op in enumerate(candidate.ops) if op.kind == 'hmr')
    for bits in product((0, 1), repeat=len(candidate.classical_inputs)):
        memory = dict(zip(candidate.classical_inputs, bits))
        for value in range(1 << n):
            state, _, _ = _columns(candidate.ops[:event], value, memory, 0, guard)
            if (state >> n & 1) != ((state >> pair_controls[0] & 1) & (state >> pair_controls[1] & 1)):
                return False
    return True


def prove_kmb_reset_cache(path, request, *, expected_source_sha256, expected_request_sha256,
                          output_path=None, budget: Budget | None = None) -> dict:
    """Rebuild a complete-source channel-extension plan and optional full KMB candidate."""
    created = False
    try:
        with VerificationSession(call_budget(budget)) as guard:
            if any(getattr(guard.budget, k) is not None for k in ('max_nodes', 'max_terms', 'max_bytes')):
                raise ValueError('use fixed source/window caps and a shared time budget')
            binary._pin(expected_source_sha256)
            binary._pin(expected_request_sha256)
            raw = json.dumps(request, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            if len(raw) > 2_000_000:
                raise ResourceLimitExceeded('site request bytes', 2_000_000, len(raw))
            request = parse_json(raw)
            if (type(request) is not dict or set(request) != {'kind', 'schema_version', 'source_file_sha256',
                    'window', 'pair', 'wires', 'fresh_wire', 'fresh_bit', 'local_request', 'domain', 'observation'}
                    or request['kind'] != _KIND or type(request['schema_version']) is not int or request['schema_version'] != 1):
                raise ValueError('closed KMB reset-cache site request required')
            if canonical_sha256(request) != expected_request_sha256 or request['source_file_sha256'] != expected_source_sha256:
                raise ReceiptMismatch('source/site request differs from independent pins')
            if (request['domain'] != 'all_original_quantum_states_and_arbitrary_classical_values'
                    or request['observation'] != 'all_original_outputs_new_hmr_result_forgotten'):
                raise UnsupportedOperation('only the full original input domain and private new HMR observation are supported')
            span, pair, wires = (request[k] for k in ('window', 'pair', 'wires'))
            if (type(span) is not list or len(span) != 2 or any(type(i) is not int for i in span)
                    or not 0 <= span[0] < span[1] or span[1] - span[0] > 4096):
                raise ValueError('ordered raw window of at most 4096 operations required')
            if (type(pair) is not list or len(pair) != 2 or any(type(i) is not int for i in pair)
                    or not span[0] <= pair[0] < pair[1] < span[1]):
                raise ValueError('ordered raw cache coordinates inside window required')
            if (type(wires) is not list or not wires or len(wires) > 12
                    or any(type(q) is not int or q < 0 for q in wires) or len(set(wires)) != len(wires)):
                raise ValueError('explicit injective data mapping of at most 12 wires required')
            import numpy as np

            fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0))
            with os.fdopen(fd, 'rb') as stream:
                status = os.fstat(stream.fileno())
                if not stat.S_ISREG(status.st_mode) or status.st_size > 2 * 1024**3:
                    raise UnsupportedOperation('regular source of at most 2 GiB required')
                deadline = guard.deadline if guard.deadline is not None else float('inf')
                with binary._private_snapshot(stream, status.st_size, deadline=deadline,
                        max_seconds=guard.remaining_seconds() or 30) as (view, pin):
                    if pin != expected_source_sha256:
                        raise ReceiptMismatch('complete private source snapshot differs from pin')
                    info, packets = binary._layout(view, max_registers=100_000, max_register_entries=5_000_000,
                        max_ops=100_000_000, max_seconds_deadline=deadline)
                    if span[1] > info['num_ops']:
                        raise ValueError('window beyond complete source')
                    if (type(request['fresh_wire']) is not int or type(request['fresh_bit']) is not int
                            or request['fresh_wire'] != info['num_qubits'] or request['fresh_bit'] != info['num_bits']):
                        raise ValueError('fresh resources must be exactly the next source quantum/classical indices')
                    validation = {"cut_op": 0, "lease_stop_op": 0, "wires": [0], "initial_constants": []}
                    _, work = frontier._scan(np, view, info, packets, validation, guard, frontier.FrontierLimits())
                    records, counts = _extract(np, view, info, packets, *span, guard)
                    if set(wires) != {q for _, qs, _, _ in records for q in qs}:
                        raise ReceiptMismatch('mapping must cover exactly the complete local window support')
                    reference, positions = _fragment(records, wires)
                    local_pair = tuple(positions.index(i - span[0]) for i in pair)
                    local = cache_request(reference, local_pair, fresh_slot=f"b{request['fresh_bit']}")
                    if not frontier._same(request['local_request'], local, guard):
                        raise ReceiptMismatch('complete window, mapping or pinned replacement differs from the source recipe')
                    proof = prove_reset_cache(local, expected_request_sha256=canonical_sha256(local), budget=guard.remaining_budget())
                    if proof['outcome'] != 'equivalent':
                        return {'kind': _KIND, 'schema_version': 1, 'outcome': proof['outcome'], 'local_proof': proof,
                                'global_substitution_authorized': False}
                    from symq.labs.rewrite_request import fragment_from_dict

                    candidate = fragment_from_dict(local['candidate'])
                    controls = tuple(wires.index(q) for q in records[pair[1] - span[0]][1][:2])
                    if not _relation(candidate, controls, len(wires), guard):
                        raise ValueError('actual cache product relation failed')
                    dependencies = frontier._dependencies(np, guard)
                    dependencies['site_adapter_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
                    replacement = _candidate_records(records, [i - span[0] for i in pair], request['fresh_wire'], request['fresh_bit'])
                    definition = span[0] + next(i for i, op in enumerate(replacement) if op[0] == 80 and op[2] == request['fresh_bit'])
                    reads = [span[0] + i for i, op in enumerate(replacement) if op[3] == request['fresh_bit']]
                    if output_path is not None and Path(output_path).exists():
                        raise FileExistsError('candidate destination already exists')
                    with (Path(output_path).open('xb') if output_path is not None else nullcontext(None)) as destination:
                        created = destination is not None
                        candidate_pin, candidate_bytes, candidate_ops = _emit(view, packets, records, replacement,
                            span[0], counts, guard, destination)
                guard.check_time()
                return {'kind': _KIND, 'schema_version': 1, 'outcome': 'equivalent_channel_extension',
                        'source_file_sha256': expected_source_sha256, 'request_sha256': expected_request_sha256,
                        'request': request, 'source_ops': info['num_ops'], 'candidate_ops': candidate_ops,
                        'source_bytes': status.st_size, 'candidate_bytes': candidate_bytes,
                        'candidate_file_sha256': candidate_pin, 'quantum_local_to_global': wires + [info['num_qubits']],
                        'new_classical_slot': f"b{info['num_bits']}", 'new_classical_version': 1,
                        'candidate_window': [span[0], span[0] + len(replacement)],
                        'measurement_definition_candidate_raw_op': definition,
                        'measurement_reads_candidate_raw_ops': reads,
                        'initial_domain': 'all original quantum states and arbitrary initial classical values',
                        'reference_extension': 'tensor explicit reset on one new quantum wire',
                        'candidate_observation': 'all original quantum/classical outputs; new HMR result forgotten',
                        'resource_obligations': {'entry_zero_by_explicit_reset': True, 'source_reservation': span,
                            'fresh_indices_outside_all_source_operands': True, 'cache_relation_at_hmr': True,
                            'return_pure_zero': True, 'new_bit_first_write_hmr': True, 'new_bit_no_reads_outside_window': True},
                        'composition': 'exact common KMB prefix/suffix; local channel identity extends through arbitrary hybrid context',
                        'global_substitution_authorized': False, 'independent_certificate': False,
                        'local_proof': proof, 'dependencies': dependencies, 'work': work}
    except (ResourceLimitExceeded, UnsupportedOperation, ImportError) as error:
        if created:
            Path(output_path).unlink(missing_ok=True)
        return {'kind': _KIND, 'schema_version': 1, 'outcome': 'inconclusive' if isinstance(error, ResourceLimitExceeded) else 'unsupported',
                'reason': str(error), 'global_substitution_authorized': False}
    except BaseException:
        if created:
            Path(output_path).unlink(missing_ok=True)
        raise


def replay_kmb_reset_cache(path, request, receipt, *, expected_source_sha256, expected_request_sha256,
                           candidate_path=None, budget: Budget | None = None):
    try:
        with VerificationSession(call_budget(budget)) as guard:
            fresh = prove_kmb_reset_cache(path, request, expected_source_sha256=expected_source_sha256,
                expected_request_sha256=expected_request_sha256, budget=guard.remaining_budget())
            if fresh['outcome'] == 'equivalent_channel_extension':
                if not frontier._same(receipt, fresh, guard):
                    raise ReceiptMismatch('site receipt differs from fresh source extraction, proof and candidate reconstruction')
                if candidate_path is not None:
                    digest = hashlib.sha256()
                    with Path(candidate_path).open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1 << 20), b''):
                            guard.check_time()
                            digest.update(chunk)
                    if digest.hexdigest() != fresh['candidate_file_sha256']:
                        raise ReceiptMismatch('complete candidate differs from reconstructed byte stream')
            guard.check_time()
            return fresh
    except ResourceLimitExceeded as error:
        return {'kind': _KIND, 'schema_version': 1, 'outcome': 'inconclusive', 'reason': str(error),
                'global_substitution_authorized': False}
