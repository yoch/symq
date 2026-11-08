"""Publication is exclusive and never cleans a concurrent writer's output."""
import os

import pytest
from test_kmb_reset_cache import fixture, pins

from symq.errors import ResourceLimitExceeded
from symq.labs import kmb_reset_cache as api


@pytest.mark.parametrize('failure', ['timeout', 'invalid'])
def test_failed_emission_preserves_a_concurrent_destination(tmp_path, monkeypatch, failure):
    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'
    original_emit = api._emit

    def interrupted(*args, **kwargs):
        original_emit(*args, **kwargs)
        foreign = tmp_path / 'foreign-output'
        foreign.write_bytes(b'unrelated concurrent output')
        os.replace(foreign, output)
        if failure == 'timeout':
            raise ResourceLimitExceeded('seconds', 1, 2)
        raise ValueError('failed after another writer populated the destination')

    monkeypatch.setattr(api, '_emit', interrupted)
    if failure == 'timeout':
        result = api.prove_kmb_reset_cache(source, request, output_path=output, **pins(request))
        assert result['outcome'] == 'inconclusive'
    else:
        with pytest.raises(ValueError, match='another writer'):
            api.prove_kmb_reset_cache(source, request, output_path=output, **pins(request))
    assert output.read_bytes() == b'unrelated concurrent output'
    assert set(tmp_path.iterdir()) == {source, output}


def test_collision_at_publication_preserves_the_concurrent_file(tmp_path, monkeypatch):
    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'
    original_link = os.link

    def collision(before, after):
        output.write_bytes(b'created just before publication')
        original_link(before, after)

    monkeypatch.setattr(api.os, 'link', collision)
    with pytest.raises(FileExistsError):
        api.prove_kmb_reset_cache(source, request, output_path=output, **pins(request))
    assert output.read_bytes() == b'created just before publication'
    assert set(tmp_path.iterdir()) == {source, output}


def test_session_exit_timeout_never_exposes_a_candidate(tmp_path, monkeypatch):
    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'
    visible_at_exit = []
    original_session = api.VerificationSession

    class ExpiringSession(original_session):
        def __exit__(self, exc_type, exc, traceback):
            super().__exit__(exc_type, exc, traceback)
            if exc_type is None:
                visible_at_exit.append(output.exists())
                raise ResourceLimitExceeded('seconds', 1, 2)

    monkeypatch.setattr(api, 'VerificationSession', ExpiringSession)
    result = api.prove_kmb_reset_cache(source, request, output_path=output, **pins(request))
    assert result['outcome'] == 'inconclusive'
    assert visible_at_exit == [False]
    assert not output.exists()
    assert set(tmp_path.iterdir()) == {source}


def test_publication_failure_cleans_only_private_staging(tmp_path, monkeypatch):
    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'

    def unsupported_link(_before, _after):
        raise OSError('filesystem does not support exclusive linking')

    monkeypatch.setattr(api.os, 'link', unsupported_link)
    with pytest.raises(OSError, match='exclusive linking'):
        api.prove_kmb_reset_cache(source, request, output_path=output, **pins(request))
    assert set(tmp_path.iterdir()) == {source}


def test_successful_publication_occurs_after_session_exit(tmp_path, monkeypatch):
    source, request = fixture(tmp_path)
    output = tmp_path / 'candidate.kmb'
    finished = []
    original_session, original_link = api.VerificationSession, os.link

    class TrackingSession(original_session):
        def __exit__(self, exc_type, exc, traceback):
            super().__exit__(exc_type, exc, traceback)
            if exc_type is None:
                finished.append(True)

    def publish(before, after):
        assert finished == [True]
        assert not output.exists()
        original_link(before, after)

    monkeypatch.setattr(api, 'VerificationSession', TrackingSession)
    monkeypatch.setattr(api.os, 'link', publish)
    proof = api.prove_kmb_reset_cache(source, request, output_path=output, **pins(request))
    assert proof['outcome'] == 'equivalent_channel_extension'
    assert set(tmp_path.iterdir()) == {source, output}
