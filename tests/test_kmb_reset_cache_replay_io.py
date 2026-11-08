"""Bound candidate file handling independently of the quantum proof runtime."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import textwrap

import pytest

pytest.importorskip('numpy')

from symq.labs import kmb_reset_cache as api
from symq.labs.rewrite import ReceiptMismatch
from symq.resources import Budget


def stub_proof(monkeypatch, data=b'good'):
    # The full source/proof path is covered by test_kmb_reset_cache. Stub only
    # its successful result to isolate the replay file boundary and its budget.
    receipt = {'outcome': 'equivalent_channel_extension', 'candidate_bytes': len(data),
               'candidate_file_sha256': hashlib.sha256(data).hexdigest()}
    monkeypatch.setattr(api, 'prove_kmb_reset_cache', lambda *a, **kw: receipt)
    return receipt


def replay(path, receipt):
    return api.replay_kmb_reset_cache('unused-source', {}, receipt,
        expected_source_sha256='0' * 64, expected_request_sha256='0' * 64,
        candidate_path=path, budget=Budget(max_seconds=1))


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='POSIX FIFO regression')
def test_fifo_candidate_is_rejected_without_blocking_outside_the_budget(tmp_path):
    fifo = tmp_path / 'candidate.fifo'
    os.mkfifo(fifo)
    # A child timeout makes a regression fail promptly instead of hanging pytest.
    code = textwrap.dedent('''
        import json, sys
        from symq.labs import kmb_reset_cache as api
        from symq.resources import Budget
        receipt = {'outcome': 'equivalent_channel_extension', 'candidate_bytes': 0,
                   'candidate_file_sha256': '0' * 64}
        api.prove_kmb_reset_cache = lambda *a, **kw: receipt
        result = api.replay_kmb_reset_cache('unused-source', {}, receipt,
            expected_source_sha256='0' * 64, expected_request_sha256='0' * 64,
            candidate_path=sys.argv[1], budget=Budget(max_seconds=1))
        print(json.dumps(result))
    ''')
    completed = subprocess.run([sys.executable, '-c', code, str(fifo)],
                               capture_output=True, text=True, timeout=5, check=True)
    result = json.loads(completed.stdout)
    assert result['outcome'] == 'unsupported'
    assert 'regular file' in result['reason']
    assert result['global_substitution_authorized'] is False


def test_directory_candidate_is_rejected_and_preserved(tmp_path, monkeypatch):
    receipt = stub_proof(monkeypatch)
    result = replay(tmp_path, receipt)
    assert result['outcome'] == 'unsupported'
    assert tmp_path.is_dir()


@pytest.mark.parametrize('contents', [b'bad-size', b'baad'])
def test_size_and_same_size_content_mutants_are_rejected(tmp_path, monkeypatch, contents):
    receipt = stub_proof(monkeypatch)
    path = tmp_path / 'candidate.kmb'
    path.write_bytes(contents)
    with pytest.raises(ReceiptMismatch, match='complete candidate'):
        replay(path, receipt)
    assert path.read_bytes() == contents


def test_regular_candidate_content_is_still_verified(tmp_path, monkeypatch):
    receipt = stub_proof(monkeypatch)
    path = tmp_path / 'candidate.kmb'
    path.write_bytes(b'good')
    assert replay(path, receipt) == receipt
