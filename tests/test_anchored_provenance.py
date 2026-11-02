"""The engine and harness have the same basename but distinct provenance roles."""
from __future__ import annotations

import hashlib
from pathlib import Path

from benchmarks import anchored_kraus as campaign
from symq.labs import anchored_kraus as engine


def test_provenance_does_not_overwrite_same_basename_sources():
    report = campaign.campaign(programs=1)
    assert report['passed']
    assert report['sources'] == {
        'harness_sha256': hashlib.sha256(Path(campaign.__file__).read_bytes()).hexdigest(),
        'engine_sha256': hashlib.sha256(Path(engine.__file__).read_bytes()).hexdigest(),
    }
    assert report['sources']['engine_sha256'] != report['sources']['harness_sha256']
