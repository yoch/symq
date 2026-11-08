"""Whole-small-source instrument oracle, exact splice identity and adversarial pins."""
from __future__ import annotations

import copy
import hashlib
import struct
from itertools import product

import pytest
from test_kmb_window import _packets
from testkit.kraus_oracle import independent_kraus

pytest.importorskip('numpy')

from symq.experimental.hybrid import HOp, HybridProgram
from symq.hashing import canonical_sha256
from symq.labs.channel_composition import HybridFragment
from symq.labs.kmb_reset_cache import prove_kmb_reset_cache, replay_kmb_reset_cache
from symq.labs.kmb_window import extract_kmb_window
from symq.labs.reset_cache import cache_request
from symq.labs.rewrite import ReceiptMismatch
from symq.labs.rewrite_request import fragment_from_dict
from symq.resources import Budget


def fixture(tmp_path):
    source = tmp_path / 'source.kmb'
    # Arbitrary entangled inputs on all four original wires. HMR and adaptive
    # context remain outside the window; b0 is arbitrary at the local interface.
    ops = [(80, (3,), 0, None), (49, (0, 1, 2), None, None), (144, (2,), None, 0),
           (49, (0, 1, 2), None, None), (161, (0, 3), None, 0)]
    raw = _packets(*ops)
    source.write_bytes(raw)
    pin = hashlib.sha256(raw).hexdigest()
    wires = [2, 0, 1]
    reference = HybridFragment(3, (HOp('ccx', (1, 2, 0)), HOp('z', (0,), condition='b0'),
                                    HOp('ccx', (1, 2, 0))), ('b0',))
    request = {'kind': 'symq_kmb_reset_cache_site', 'schema_version': 1, 'source_file_sha256': pin,
                   'window': [1, 4], 'pair': [1, 3], 'wires': wires, 'fresh_wire': 4, 'fresh_bit': 1,
                   'domain': 'all_original_quantum_states_and_arbitrary_classical_values',
                   'observation': 'all_original_outputs_new_hmr_result_forgotten',
                   'local_request': cache_request(reference, (0, 2), fresh_slot='b1')}
    return source, request


def pins(request):
    return {'expected_source_sha256': request['source_file_sha256'], 'expected_request_sha256': canonical_sha256(request)}


def test_global_hybrid_context_and_added_dirty_wire_match_every_instrument_matrix_unit(tmp_path):
    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'
    proof = prove_kmb_reset_cache(source, request, **pins(request), output_path=output)
    assert proof['outcome'] == 'equivalent_channel_extension'
    assert proof['candidate_file_sha256'] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert proof['measurement_definition_candidate_raw_op'] < min(proof['measurement_reads_candidate_raw_ops'])
    assert proof['resource_obligations']['cache_relation_at_hmr']
    assert not proof['global_substitution_authorized']
    # Independent scalar Kraus evolution of complete before/after circuits,
    # with all original classical outputs observed. New b1 is forgotten.
    old = extract_kmb_window(source, start_op=0, stop_op=5, expected_source_sha256=request['source_file_sha256'])
    new = extract_kmb_window(output, start_op=0, stop_op=9, expected_source_sha256=proof['candidate_file_sha256'])
    reference = HybridProgram(5, 0, [HOp('reset', (4,)), *fragment_from_dict(old['fragment']).ops])
    candidate = HybridProgram(5, 0, list(fragment_from_dict(new['fragment']).ops))
    for x, y in product(range(32), repeat=2):
        assert independent_kraus(reference, x, y, ('b0',)) == independent_kraus(candidate, x, y, ('b0',))
    assert replay_kmb_reset_cache(source, request, proof, candidate_path=output, **pins(request)) == proof


def test_mutations_positions_mapping_resources_replacement_and_domain_are_not_accepted(tmp_path):
    source, request = fixture(tmp_path)
    proof = prove_kmb_reset_cache(source, request, **pins(request))
    for change in (
        lambda d: d.update(fresh_wire=3), lambda d: d.update(fresh_bit=0),
        lambda d: d.update(wires=[0, 1, 2]), lambda d: d.update(pair=[1, 2]),
        lambda d: d.update(domain='zero_inputs'),
        lambda d: d['local_request']['candidate']['ops'].pop(),
    ):
        mutation = copy.deepcopy(request)
        change(mutation)
        with pytest.raises((ReceiptMismatch, ValueError)):
            prove_kmb_reset_cache(source, mutation, **pins(request))
    forged = copy.deepcopy(proof)
    forged['resource_obligations']['entry_zero_by_explicit_reset'] = False
    with pytest.raises(ReceiptMismatch):
        replay_kmb_reset_cache(source, request, forged, **pins(request))
    output = tmp_path / 'candidate.kmb'
    prove_kmb_reset_cache(source, request, output_path=output, **pins(request))
    output.write_bytes(output.read_bytes() + b'forged')
    with pytest.raises(ReceiptMismatch):
        replay_kmb_reset_cache(source, request, proof, candidate_path=output, **pins(request))


def test_context_drift_unsupported_outside_window_and_timeout_do_not_emit(tmp_path):
    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'
    result = prove_kmb_reset_cache(source, request, output_path=output, **pins(request), budget=Budget(absolute_deadline=0))
    assert result['outcome'] == 'inconclusive' and not output.exists()
    old = source.read_bytes()
    source.write_bytes(old + b'drift outside selected window')
    with pytest.raises(ReceiptMismatch):
        prove_kmb_reset_cache(source, request, **pins(request))
    source.write_bytes(_packets((7, (), None, None), (49, (0, 1, 2), None, None),
                               (144, (2,), None, 0), (49, (0, 1, 2), None, None), (161, (0, 3), None, 0)))
    request['source_file_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    assert prove_kmb_reset_cache(source, request, **pins(request))['outcome'] == 'unsupported'


def test_outer_conditions_metadata_and_repinned_semantic_mutants(tmp_path):
    source, request = fixture(tmp_path)
    source.write_bytes(_packets((80, (3,), 0, None), (129, (), None, 0),
        (49, (0, 1, 2), None, None), (144, (2,), None, 0),
        (49, (0, 1, 2), None, None), (1, (), None, None), (161, (0, 3), None, 0)))
    request.update(source_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), window=[2, 5], pair=[2, 4])
    assert prove_kmb_reset_cache(source, request, **pins(request))['outcome'] == 'unsupported'
    source, request = fixture(tmp_path)
    for update in ({'fresh_wire': 3}, {'fresh_bit': 0}, {'wires': [0, 1, 2]}):
        mutation = copy.deepcopy(request)
        mutation.update(update)
        with pytest.raises((ValueError, ReceiptMismatch)):
            prove_kmb_reset_cache(source, mutation, **pins(mutation))
    mutation = copy.deepcopy(request)
    mutation['local_request']['schema_version'] = True
    with pytest.raises(ReceiptMismatch):
        prove_kmb_reset_cache(source, mutation, **pins(mutation))
    # Metadata stays in order and still occupies raw coordinates after streaming.
    raw = source.read_bytes()
    header = list(struct.unpack_from('<16sIIII9Q', raw))
    header[5] += 1
    header[12:14] = [1, 3]
    at, packets = 104, []
    for _ in range(11):
        kind, size = struct.unpack_from('<QQ', raw, at)
        payload = raw[at + 16:at + 16 + size]
        if kind == 1:
            payload = payload[:2] + bytes([6]) + payload[2:]
        elif kind == 11:
            payload = struct.pack('<QQ', 1, 3) + b'tag'
        packets.append(struct.pack('<QQ', kind, len(payload)) + payload)
        at += 16 + size
    source.write_bytes(struct.pack('<16sIIII9Q', *header) + b''.join(packets))
    request.update(source_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), window=[1, 5], pair=[1, 4])
    output = tmp_path / 'with-info.kmb'
    result = prove_kmb_reset_cache(source, request, **pins(request), output_path=output)
    assert result['outcome'] == 'equivalent_channel_extension'
    encoded = output.read_bytes()
    header = struct.unpack_from('<16sIIII9Q', encoded)
    at, payloads = 104, {}
    for _ in range(11):
        kind, size = struct.unpack_from('<QQ', encoded, at)
        payloads[kind] = encoded[at + 16:at + 16 + size]
        at += 16 + size
    assert at == len(encoded) and header[5] == len(payloads[1]) == 10
    assert payloads[1][4] == 6 and payloads[1][0] == 80 and payloads[1][-1] == 161
    assert payloads[11] == struct.pack('<QQ', 1, 3) + b'tag'
    assert replay_kmb_reset_cache(source, request, result, candidate_path=output, **pins(request)) == result


def test_late_expiration_removes_owned_candidate_and_existing_outputs_survive(tmp_path, monkeypatch):
    import symq.labs.kmb_reset_cache as api
    from symq.errors import ResourceLimitExceeded

    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'
    original = api._emit
    def expired(*args, **kw):
        original(*args, **kw)
        raise ResourceLimitExceeded('seconds', 1, 2)
    monkeypatch.setattr(api, '_emit', expired)
    result = prove_kmb_reset_cache(source, request, **pins(request), output_path=output)
    assert result['outcome'] == 'inconclusive'
    assert not output.exists()
    output.write_bytes(b'preexisting file')
    with pytest.raises(FileExistsError):
        prove_kmb_reset_cache(source, request, **pins(request), output_path=output)
    assert output.read_bytes() == b'preexisting file'


def test_overwritten_product_is_a_local_obligation_failure_without_global_witness(tmp_path):
    source, request = fixture(tmp_path)
    source.write_bytes(_packets((80, (3,), 0, None), (49, (0, 1, 2), None, None),
        (17, (0,), None, None), (49, (0, 1, 2), None, None), (161, (0, 3), None, 0)))
    reference = HybridFragment(3, (HOp('ccx', (1, 2, 0)), HOp('x', (1,)), HOp('ccx', (1, 2, 0))))
    request.update(source_file_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                   local_request=cache_request(reference, (0, 2), fresh_slot='b1'))
    output = tmp_path / 'candidate.kmb'
    result = prove_kmb_reset_cache(source, request, **pins(request), output_path=output)
    assert result['outcome'] == 'local_obligation_failed'
    assert result['local_proof']['witness']['scope'] == 'local_column_only'
    assert not result['global_substitution_authorized'] and not output.exists()
