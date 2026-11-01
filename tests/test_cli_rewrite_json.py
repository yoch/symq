"""P2 CLI JSON contract: early timeouts and invalid inputs never break machine parsers."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from symq.__main__ import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "rewrite"


def _request(tmp_path: Path) -> Path:
    for file in ("source.qasm", "replacement.json", "request.json"):
        shutil.copyfile(EXAMPLE / file, tmp_path / file)
    return tmp_path / "request.json"


def _run(capsys, argv: list[str]) -> tuple[int, dict, str]:
    code = main(argv)
    out = capsys.readouterr()
    return code, json.loads(out.out), out.err


def test_missing_input_is_typed_json_even_before_a_checker_runs(tmp_path, capsys):
    code, out, err = _run(capsys, ["rewrite", str(tmp_path / "missing.json")])
    assert code == 3 and not err
    assert out["kind"] == "symq_rewrite_cli_result"
    assert out["schema_version"] == 1
    assert out["application"] == "not_applied"
    assert out["result"]["outcome"] == "invalid"
    assert out["error_type"] == "FileNotFoundError"
    assert "missing.json" in out["result"]["reason"]


def test_early_timeout_never_outputs_a_flat_or_empty_status(tmp_path, capsys):
    request = _request(tmp_path)
    code, out, err = _run(capsys, [
        "rewrite", str(request), "--timeout", "1e-12",
        "--report", str(tmp_path / "never.json"),
    ])
    assert code == 2 and not err
    assert out["application"] == "not_applied"
    assert out["result"]["outcome"] == "inconclusive"
    assert out["error_type"] == "ResourceLimitExceeded"
    assert not (tmp_path / "never.json").exists()


@pytest.mark.sat
def test_full_success_then_early_replay_timeout_have_same_parseable_envelope(tmp_path, capsys):
    request = _request(tmp_path)
    path = tmp_path / "result.json"
    code, ok, err = _run(capsys, ["rewrite", str(request), "--report", str(path)])
    assert code == 0 and not err
    assert ok["kind"] == "symq_rewrite_cli_result"
    assert ok["result"]["outcome"] == "equivalent"
    assert ok["application"] == "applied"

    code, late, err = _run(capsys, ["replay", str(path), "--timeout", "1e-12"])
    assert code == 2 and not err
    assert late["kind"] == ok["kind"]
    assert late["result"]["outcome"] == "inconclusive"
    assert late["application"] == "not_applied"


@pytest.mark.sat
def test_malformed_replay_json_gives_typed_invalid_status(tmp_path, capsys):
    report = tmp_path / "report.json"
    report.write_text("[]")
    code, result, err = _run(capsys, ["replay", str(report)])
    assert code == 3 and not err
    assert result["kind"] == "symq_rewrite_cli_result"
    assert result["result"]["outcome"] == "invalid"


def test_isolated_worker_timeout_has_same_nested_result(tmp_path, capsys, monkeypatch):
    from symq.experimental import execution

    request = _request(tmp_path)
    def worker(*_args, **_kwargs):
        return SimpleNamespace(status="inconclusive",
                               reason="hard wall deadline", value=None)

    monkeypatch.setattr(execution, "run_isolated", worker)
    code, result, err = _run(capsys, ["rewrite", str(request), "--isolate"])
    assert code == 2 and not err
    assert result["application"] == "not_applied"
    assert result["result"] == {"outcome": "inconclusive", "reason": "hard wall deadline"}


def test_native_missing_error_names_absent_binary_not_circular_import():
    from symq.backends import NATIVE_IMPORT_ERROR, has_native

    if has_native():
        pytest.skip("native binary installed: missing binary case is tested by the pure CI job")
    assert NATIVE_IMPORT_ERROR is not None
    assert "symq.backends._zdd" in NATIVE_IMPORT_ERROR
    assert "not installed" in NATIVE_IMPORT_ERROR
    assert "partially initialized" not in NATIVE_IMPORT_ERROR
    assert "circular import" not in NATIVE_IMPORT_ERROR
