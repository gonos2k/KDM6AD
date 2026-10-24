"""Invalid restricted invocations cannot write into parent or unrelated runs."""
import json

import pytest

from harness import run_native_satellite_case as runner


@pytest.mark.parametrize("preflight,owned,stale,computed", [
    (True, True, False, True), (False, False, False, True),
    (False, True, False, True), (False, True, True, True),
    (False, True, False, False),
])
def test_failure_receipt_requires_owned_run_and_actual_execution(tmp_path, monkeypatch,
                                                               preflight, owned, stale, computed):
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "CASE_MANIFEST.json").write_text('{"run_id":"parent"}')
    candidate = tmp_path / "candidate.json"
    candidate.write_text('{"selected_alpha":1.0}')
    root = tmp_path / "restricted" if owned else parent
    if owned:
        root.mkdir()
        (root / "CASE_MANIFEST.json").write_text(json.dumps({
            "run_id": "stale-other-source" if stale else "restricted",
            "experiment_type": "restricted_block_confirmation_v1",
            "candidate_json_sha256": runner.sha(candidate),
            "parent_case_manifest_sha256": runner.sha(parent / "CASE_MANIFEST.json"),
        }))
    before = {str(p): p.read_bytes() for p in parent.rglob('*') if p.is_file()}

    def refuse(_):
        if computed:
            runner._EXPECTED_FAILURE_RUN_ID = "restricted"
        raise ValueError("invalid invocation before models")

    monkeypatch.setattr(runner, "main", refuse)
    args = ["--stage", "restricted-confirmation", "--parent-run", str(parent),
            "--candidate-json", str(candidate), "--output-root", str(root)]
    if preflight:
        args.append("--preflight-only")
    runner._EXPECTED_FAILURE_RUN_ID = "stale-from-prior-invocation"
    with pytest.raises(ValueError, match="invalid invocation"):
        runner.guarded_main(args)
    assert {str(p): p.read_bytes() for p in parent.rglob('*') if p.is_file()} == before
    assert len(list((root / 'failures').glob('*.json'))) == int(
        owned and not preflight and not stale and computed)
