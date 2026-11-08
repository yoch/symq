"""Missing optional dependency and closed request tests run without NumPy."""
import sys

import pytest

from symq.hashing import canonical_sha256
from symq.labs.kmb_resource_frontier import assess_kmb_resources


def test_missing_numpy_never_reuses_a_claim_or_infers_zero(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "numpy", None)
    request = {"kind": "symq_kmb_resource_frontier", "schema_version": 1,
               "source_file_sha256": "0" * 64, "cut_op": 0, "lease_stop_op": 0,
               "wires": [0], "initial_constants": []}
    report = assess_kmb_resources(tmp_path / "source.kmb", request,
                                  expected_source_sha256="0" * 64,
                                  expected_request_sha256=canonical_sha256(request))
    assert report["status"] == "unsupported"
    assert report["facts"] == report["available_zero_wires"] == []
    assert not report["candidate_authorized"]
    request["schema_version"] = True
    with pytest.raises(ValueError, match="schema"):
        assess_kmb_resources(tmp_path / "source.kmb", request,
                              expected_source_sha256="0" * 64,
                              expected_request_sha256=canonical_sha256(request))
