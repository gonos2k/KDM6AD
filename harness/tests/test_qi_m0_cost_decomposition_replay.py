"""Trust-boundary checks for the saved M0 cost decomposition packet."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


REPLAY = importlib.import_module(
    'harness.evidence.native_qi_m0_cost_decomposition_2026-10-31.replay'
)


def test_official_replay_checks_parent_and_semantics() -> None:
    run = subprocess.run(
        [sys.executable, '-m',
         'harness.evidence.native_qi_m0_cost_decomposition_2026-10-31.replay'],
        cwd=REPLAY.REPO, check=True, capture_output=True, text=True,
    )
    last = json.loads(run.stdout.splitlines()[-1])
    assert last['status'] == 'REPLAY_PASSED'
    assert last['model_calls'] == 0
    assert last['east_share'] == 0.9883565126914912


def test_east_witness_cannot_invent_pre_pilot_qnc_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = tmp_path / 'packet'
    shutil.copytree(REPLAY.PACKET, packet)
    monkeypatch.setattr(REPLAY, 'PACKET', packet)
    path = packet / 'data/east_cost_moment_witness.json'
    witness = json.loads(path.read_text())
    row = witness['profiles'][0]['changed_moment_words'][0]
    row['words']['original_control'] = '00000001'
    path.write_text(json.dumps(witness, indent=2, sort_keys=True) + '\n')
    with pytest.raises(ValueError, match='east moment changed before boundary pilot'):
        REPLAY._check_checkpoint_witness(json.loads((packet / 'analysis.json').read_text()))


def test_manifest_missing_required_file_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = tmp_path / 'packet'
    shutil.copytree(REPLAY.PACKET, packet)
    monkeypatch.setattr(REPLAY, 'PACKET', packet)
    path = packet / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['packet_files_sha256'].pop('semantic_analysis.json')
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
    with pytest.raises(ValueError, match='manifest inventory differs'):
        REPLAY.main()


def test_analysis_and_semantics_sources_are_pinned() -> None:
    manifest = json.loads((REPLAY.PACKET / 'manifest.json').read_text())
    for relative in (
        'harness/analyze_qi_m0_cost_decomposition.py',
        'harness/analyze_qi_m0_direct_semantics.py',
        'harness/native_qnc_residual_reason_producer.py',
    ):
        digest = hashlib.sha256((REPLAY.REPO / relative).read_bytes()).hexdigest()
        assert manifest['external_source_pins'][relative] == digest


def test_private_witness_field_reader_change_is_rejected(tmp_path: Path) -> None:
    relative = 'harness/native_qnc_residual_reason_producer.py'
    source = REPLAY.REPO / relative
    copied = tmp_path / relative
    copied.parent.mkdir(parents=True)
    shutil.copy2(source, copied)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    REPLAY.verify(tmp_path, {relative: digest})
    copied.write_bytes(copied.read_bytes() + b'\n# changed reader\n')
    with pytest.raises(ValueError, match='pinned file changed'):
        REPLAY.verify(tmp_path, {relative: digest})
