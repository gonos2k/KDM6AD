"""Authenticate and replay the saved fixed-M0 cost decomposition."""
from __future__ import annotations

import hashlib
import importlib
import json
import math
from pathlib import Path
import re
import subprocess
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
DIRECT = REPO / 'harness/evidence/native_qi_postmicro_direct_m0_2026-10-30'
HOST = REPO / 'harness/evidence/native_qi_postmicro_boundary_2026-10-30'
BASELINE = REPO / 'harness/evidence/native_full_physics_observation_2026-10-25'
FILES = {
    'README.md', 'analysis.json', 'semantic_analysis.json',
    'review_summary.json', 'replay.py',
    'data/original_vs_qnc_guard_checkpoint.json',
    'data/compare_original_checkpoint.py.txt',
    'data/east_cost_moment_witness.json',
    'data/export_east_cost_witness.py.txt',
}
SOURCES = {
    'harness/analyze_qi_m0_cost_decomposition.py',
    'harness/analyze_qi_m0_direct_semantics.py',
    'harness/native_replay_compare.py',
    'harness/native_qnc_residual_reason_producer.py',
}
UPSTREAM = {
    'harness/evidence/native_qi_postmicro_direct_m0_2026-10-30/manifest.json',
    'harness/evidence/native_qi_postmicro_boundary_2026-10-30/manifest.json',
    'harness/evidence/native_full_physics_observation_2026-10-25/manifest.json',
}
HEX = re.compile(r'[0-9A-F]{8}\Z')


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root: Path, pins: dict[str, str]) -> None:
    if not isinstance(pins, dict) or not pins:
        raise ValueError('empty cost-decomposition pin inventory')
    for relative, digest in pins.items():
        item = Path(relative)
        if item.is_absolute() or '..' in item.parts:
            raise ValueError('unsafe cost-decomposition path')
        path = root / item
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('cost-decomposition pin escapes root')
        if sha(path) != digest:
            raise ValueError(f'cost-decomposition pinned file changed: {relative}')


def _check_checkpoint_witness(cost: dict) -> None:
    baseline = json.loads((BASELINE / 'manifest.json').read_text())
    host = json.loads((HOST / 'execution_summary.json').read_text())
    receipt = json.loads((PACKET / 'data/original_vs_qnc_guard_checkpoint.json').read_text())
    witness = json.loads((PACKET / 'data/east_cost_moment_witness.json').read_text())
    original = baseline['analysis']['checkpoint_sha256']
    qnc = host['cases']['control']['parent_checkpoint_sha256']
    pilot = host['cases']['control']['candidate_checkpoint_sha256']
    if (receipt.get('schema') != 'kdm6.original_vs_qnc_guard_control_checkpoint.v1' or
            receipt.get('original_checkpoint_sha256') != original or
            receipt.get('qnc_guard_checkpoint_sha256') != qnc or
            receipt.get('comparison_source_sha256') != sha(
                REPO / 'harness/native_replay_compare.py') or
            receipt.get('variable_count') != 652 or
            receipt.get('numeric_elements_compared') != 322426586 or
            receipt.get('changed_variables') != {'QNCLOUD': 15, 'RE_CLOUD': 1} or
            receipt.get('east_profiles_bitwise_equal_before_boundary_pilot') is not True or
            receipt.get('model_calls') != {'host': 0, 'KDM6': 0, 'RTTOV': 0, 'optimizer': 0}):
        raise ValueError('original-to-QNC checkpoint witness differs')
    changed = receipt['changed_rows']
    if set(changed) != {'QNCLOUD', 'RE_CLOUD'} or any(
            len(changed[name]) != receipt['changed_variables'][name] for name in changed):
        raise ValueError('checkpoint witness changed-row inventory differs')
    east = [(234, j) for j in (*range(3, 12), 52)]
    if (receipt['east_pilot_control_cost_profiles_ij_1based'] != [list(x) for x in east] or
            any((r['ijk_1based'][0], r['ijk_1based'][1]) in east
                for rows in changed.values() for r in rows)):
        raise ValueError('east checkpoint identity witness differs')
    if (witness.get('schema') != 'kdm6.qi_m0_east_cost_moment_witness.v1' or
            witness.get('checkpoint_sha256') !=
            {'original_control': original, 'qnc_guard_control': qnc,
             'pilot_control': pilot} or
            witness.get('profile_count') != 11 or
            witness.get('east_profile_count') != 10 or
            witness.get('model_calls') != {'host': 0, 'KDM6': 0, 'RTTOV': 0,
                                          'optimizer': 0}):
        raise ValueError('east moment witness lineage differs')
    profiles = witness['profiles']
    if [row['native_ij_1based'] for row in profiles] != [
            *[list(x) for x in east], [221, 63]]:
        raise ValueError('east moment witness coordinate inventory differs')
    for row in profiles:
        i, j = row['native_ij_1based']
        if row['flat_index_zero_based'] != (j - 1) * 234 + i - 1:
            raise ValueError('east moment witness flat coordinate differs')
        counts = {name: 0 for name in ('QCLOUD', 'QNCLOUD', 'QICE', 'QNICE')}
        for item in row['changed_moment_words']:
            values = item['words']
            if (item['field'] not in counts or
                    not 1 <= item['k_1based'] <= 39 or
                    set(values) != {'original_control', 'qnc_guard_control',
                                    'pilot_control'} or
                    not all(HEX.fullmatch(v) for v in values.values()) or
                    len(set(values.values())) == 1):
                raise ValueError('east moment word record differs')
            if values['qnc_guard_control'] != values['pilot_control']:
                counts[item['field']] += 1
            if i == 234 and values['original_control'] != values['qnc_guard_control']:
                raise ValueError('east moment changed before boundary pilot')
        if counts != row['changed_layers_from_qnc_guard_by_field']:
            raise ValueError('east moment layer counts differ')
        if i == 234 and (counts['QICE'] < 1 or counts['QNICE'] < 1 or
                         counts['QCLOUD'] or counts['QNCLOUD']):
            raise ValueError('east cost moment attribution differs')
        if i == 221 and j == 63 and (counts['QICE'] or counts['QNICE']):
            raise ValueError('QNC target changed under boundary pilot')
    old = (PACKET / 'data/compare_original_checkpoint.py.txt').read_bytes()
    new = (PACKET / 'data/export_east_cost_witness.py.txt').read_bytes()
    if (b'ORIGINAL_SHA' not in old or b'QNC_GUARD_SHA' not in old or
            b'PINS' not in new or b'PROFILES' not in new):
        raise ValueError('private producer snapshot differs')


def build_analysis() -> dict:
    parent = importlib.import_module(
        'harness.evidence.native_qi_postmicro_direct_m0_2026-10-30.packet_replay')
    parent.main()
    command = [sys.executable, '-m', 'harness.analyze_qi_m0_cost_decomposition',
               '--top', '20']
    cost_raw = subprocess.run(command, cwd=REPO, check=True, capture_output=True).stdout
    if cost_raw != (PACKET / 'analysis.json').read_bytes():
        raise ValueError('cost decomposition differs from published bytes')
    semantics_raw = subprocess.run(
        [sys.executable, '-m', 'harness.analyze_qi_m0_direct_semantics'],
        cwd=REPO, check=True, capture_output=True,
    ).stdout
    if semantics_raw != (PACKET / 'semantic_analysis.json').read_bytes():
        raise ValueError('direct receipt semantics differ from published bytes')
    cost = json.loads(cost_raw)
    semantics = json.loads(semantics_raw)
    if (semantics['status'] != 'PASSED' or semantics['receipts_verified'] != 258 or
            semantics['support_cells'] != 377342 or semantics['model_calls'] != 0 or
            semantics['cases']['control']['cost'] != cost['costs']['control'] or
            semantics['cases']['alpha025']['cost'] != cost['costs']['alpha025']):
        raise ValueError('direct semantics/cost join differs')
    control = cost['comparisons']['control_minus_baseline']
    alpha = cost['comparisons']['alpha025_minus_baseline']
    paired = cost['comparisons']['alpha025_minus_control']
    expected_control = {(234, j) for j in (*range(3, 12), 52)} | {(221, 63)}
    listed_control = control['top_changed_profiles_by_abs_cost_delta']
    if (len(listed_control) != 11 or
            {(row['i'], row['j']) for row in listed_control} != expected_control):
        raise ValueError('Control cost profiles do not join the moment witnesses')
    if (control['changed_profiles'] != 11 or
            control['geometry']['east']['changed_profiles'] != 10 or
            control['geometry']['interior']['changed_profiles'] != 1 or
            control['profilewise_gross']['positive_count'] != 11 or
            control['profilewise_gross']['negative_count'] != 0 or
            alpha['profilewise_gross']['positive_count'] != 14804 or
            alpha['profilewise_gross']['negative_count'] != 33453 or
            alpha['strict_abs_bt_thresholds_K']['0.01']['cells'] != 5075 or
            alpha['strict_abs_bt_thresholds_K']['0.1']['cells'] != 966 or
            alpha['strict_abs_bt_thresholds_K']['1.0']['cells'] != 127 or
            not alpha['channel_cost_delta']['10'] > 0 or
            any(alpha['channel_cost_delta'][str(c)] >= 0 for c in range(11, 17)) or
            any(paired['channel_cost_delta'][str(c)] >= 0 for c in range(10, 17))):
        raise ValueError('reviewed cost decomposition inventory differs')
    for row in (control, alpha, paired):
        if (abs(row['roundoff_gap_regrouped_minus_aggregate']) > 2e-15 or
                abs(row['geometry_sum_minus_regrouped']) > 2e-15 or
                abs(row['channel_sum_minus_regrouped']) > 2e-15 or
                sum(part['supported_profiles'] for part in row['geometry'].values()) != 53906 or
                sum(part['supported_cells'] for part in row['geometry'].values()) != 377342):
            raise ValueError('decomposition does not reconcile with fixed M0')
    east = control['geometry']['east']['cost_delta']
    total = control['regrouped_cell_delta']
    share = east / total
    if not math.isclose(share, 0.9883565126914911, rel_tol=0, abs_tol=2e-15):
        raise ValueError('east cost share differs')
    _check_checkpoint_witness(cost)
    return {
        'schema': 'kdm6.qi_m0_cost_decomposition_review.v1',
        'model_calls': {'host': 0, 'KDM6': 0, 'RTTOV': 0, 'optimizer': 0},
        'costs': cost['costs'],
        'pilot_control_minus_original_east_share': share,
        'pilot_control_changed_profiles': 11,
        'pilot_control_east_profiles': 10,
        'pilot_alpha_profile_loss_increase_count_vs_original': 14804,
        'pilot_alpha_profile_loss_decrease_count_vs_original': 33453,
        'direct_receipts_semantically_verified': 258,
        'checkpoint_witness_east_state_equal_before_boundary_pilot': True,
        'scope': 'saved direct observation arrays and private-checkpoint producer receipts; no new model calls or physical/derivative acceptance',
    }


def main() -> int:
    manifest = json.loads((PACKET / 'manifest.json').read_text())
    if (manifest.get('schema') != 'kdm6.qi_m0_cost_decomposition_manifest.v1' or
            set(manifest.get('packet_files_sha256', {})) != FILES or
            set(manifest.get('external_source_pins', {})) != SOURCES or
            set(manifest.get('upstream_manifest_pins', {})) != UPSTREAM or
            manifest.get('analysis_sha256') != sha(PACKET / 'analysis.json') or
            manifest.get('semantic_analysis_sha256') != sha(
                PACKET / 'semantic_analysis.json') or
            manifest.get('review_summary_sha256') != sha(
                PACKET / 'review_summary.json') or
            manifest.get('offline_model_calls') !=
            {'host': 0, 'KDM6': 0, 'RTTOV': 0, 'optimizer': 0}):
        raise ValueError('cost-decomposition manifest inventory differs')
    verify(PACKET, manifest['packet_files_sha256'])
    verify(REPO, manifest['external_source_pins'])
    verify(REPO, manifest['upstream_manifest_pins'])
    result = build_analysis()
    encoded = (json.dumps(result, indent=2, sort_keys=True,
                          allow_nan=False) + '\n').encode()
    if encoded != (PACKET / 'review_summary.json').read_bytes():
        raise ValueError('review summary differs from published bytes')
    print(json.dumps({'status': 'REPLAY_PASSED',
                      'analysis_sha256': sha(PACKET / 'analysis.json'),
                      'semantic_sha256': sha(PACKET / 'semantic_analysis.json'),
                      'east_share': result['pilot_control_minus_original_east_share'],
                      'model_calls': 0}, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
