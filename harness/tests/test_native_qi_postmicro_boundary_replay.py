"""Mutation checks for the public QI boundary pilot's trust boundaries."""
from __future__ import annotations

import hashlib
import importlib
import json
import copy
from pathlib import Path
import shutil

import numpy as np
import pytest


REPLAY = importlib.import_module('harness.evidence.native_qi_postmicro_boundary_2026-10-30.replay')


def _copy_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    copied = tmp_path / 'packet'
    shutil.copytree(REPLAY.PACKET, copied)
    monkeypatch.setattr(REPLAY, 'PACKET', copied)
    return copied


def _save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def test_published_pilot_is_full_m0_but_boundary_wide() -> None:
    result = REPLAY.build_analysis()
    assert result['alpha_k33_target_QI_before_after']['after'] == '00000000'
    assert result['cases']['control']['M0_hard_moment_lost_profiles'] == 0
    assert result['cases']['alpha025']['M0_hard_moment_lost_channel_cells'] == 0
    assert result['cases']['alpha025']['changed_checkpoint_variables']['QICE']['elements'] == 12183
    assert result['cases']['alpha025']['checkpoint_bound_target_donor_words_joined'] is True
    assert result['candidate_is_diagnostic_not_accepted'] is True


def test_invalid_profile_inside_original_m0_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _copy_packet(tmp_path, monkeypatch)
    with np.load(REPLAY.SUPPORT, allow_pickle=False) as archive:
        assert archive['m0_mask'][39078].any()
    path = packet / 'data/alpha025/invalid_profiles.json'
    invalid = json.loads(path.read_text())
    invalid['hard_invalid_flat_indices_zero_based'] = sorted(
        [*invalid['hard_invalid_flat_indices_zero_based'], 39078]
    )
    invalid['hard_invalid_profile_count'] += 1
    _save_json(path, invalid)
    execution_path = packet / 'execution_summary.json'
    execution = json.loads(execution_path.read_text())
    execution['cases']['alpha025']['invalid_profiles_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    _save_json(execution_path, execution)
    with pytest.raises(ValueError, match='invalid-profile list'):
        REPLAY.build_analysis()


def test_wrong_finish_writer_delta_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _copy_packet(tmp_path, monkeypatch)
    path = packet / 'data/alpha025/rk_writer_delta.json'
    delta = json.loads(path.read_text())
    delta['new_line'] = delta['new_line'].replace('QI\tf32\t00000000', 'QI\tf32\t00000001')
    _save_json(path, delta)
    execution_path = packet / 'execution_summary.json'
    execution = json.loads(execution_path.read_text())
    execution['cases']['alpha025']['rk_writer_delta_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    _save_json(execution_path, execution)
    with pytest.raises(ValueError, match='RK writer delta'):
        REPLAY.build_analysis()


def test_checkpoint_target_word_must_join_boundary_trace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    packet = _copy_packet(tmp_path, monkeypatch)
    path = packet / 'data/alpha025/target_checkpoint_words.json'
    witness = json.loads(path.read_text())
    witness['after']['1,168,33']['QI'] = '00000002'
    _save_json(path, witness)
    execution_path = packet / 'execution_summary.json'
    execution = json.loads(execution_path.read_text())
    execution['cases']['alpha025']['target_checkpoint_words_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    _save_json(execution_path, execution)
    with pytest.raises(ValueError, match='checkpoint words differ'):
        REPLAY.build_analysis()


def test_manifest_summary_and_inventory_mutations_are_rejected() -> None:
    original = json.loads((REPLAY.PACKET / 'manifest.json').read_text())
    variants = []
    changed = copy.deepcopy(original)
    changed['offline_model_calls']['RTTOV'] = 1
    variants.append(changed)
    changed = copy.deepcopy(original)
    changed['analysis_sha256'] = '0' * 64
    variants.append(changed)
    changed = copy.deepcopy(original)
    changed['support_masks_sha256'] = '0' * 64
    variants.append(changed)
    changed = copy.deepcopy(original)
    changed['packet_files_sha256'].pop('data/alpha025/target_checkpoint_words.json')
    variants.append(changed)
    for manifest in variants:
        with pytest.raises(ValueError, match='manifest inventory or summary'):
            REPLAY._verify_manifest(manifest)
