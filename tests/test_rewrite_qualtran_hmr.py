"""The Qualtran coherent-rewrite runner: checker and independent oracle agree, costs priced."""
from __future__ import annotations

from benchmarks.rewrite_qualtran_hmr import run


def test_qualtran_measurement_based_uncompute_is_proved_and_priced():
    result = run()
    rows = {row["id"]: row for row in result["cases"]}
    for degree, coherences, wrong in ((1, 16, 6), (2, 256, 96)):
        good, bad = rows[f"m{degree}-full-none"], rows[f"m{degree}-full-missing_correction"]
        assert good["outcome"] == good["replayed_outcome"] == "equivalent"
        assert good["application"] == "applied"
        assert good["independent_oracle"] == {"coherences_checked": coherences,
                                              "differing": 0, "diagonal_differs": False}
        assert bad["outcome"] == "not_proved" and bad["application"] == "not_proved"
        assert bad["independent_oracle"]["differing"] == wrong
        assert not bad["independent_oracle"]["diagonal_differs"]
    # Toffolis are priced 12 under the declared proxy: both valid rewrites are cheaper.
    assert rows["m1-full-none"]["cost"]["weighted_delta"] == -10
    assert rows["m2-full-none"]["cost"]["weighted_delta"] == -40
    assert not result["receipt"]["symq_location"].startswith("/")  # no absolute path
