"""Replay the public QI/NI post-microphysics boundary diagnostic packet."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys

import numpy as np


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
PARENT = REPO / 'harness/evidence/native_qi_outflow_terms_2026-10-30'
SUPPORT = REPO / 'harness/evidence/native_qnc_host_backoff_2026-10-27/support_masks.npz'
SUPPORT_SHA = 'c4154b4b735fcbfb5509b1f23ee53f4cfe17b46ccf0c6930f63aa244f2a0f9a9'
PACKET_FILES = {
    'README.md', 'SOURCE_RESOLUTION.md', 'analysis.json', 'sample_analysis.json',
    'execution_summary.json', 'replay.py', 'data/alpha025/rk_writer_delta.json',
} | {
    f'data/{case}/{name}'
    for case in ('control', 'alpha025')
    for name in ('pilot_off.tsv', 'pilot_on.tsv', 'qi_donor_pilot_on.tsv',
                 'support_analysis.json', 'checkpoint_comparison.json',
                 'invalid_profiles.json', 'target_checkpoint_words.json')
}
EXTERNAL_FILES = {
    'harness/analyze_qi_postmicro_boundary_pilot.py',
    'harness/native_qi_postmicro_boundary_pilot_overlay.py',
    'harness/analyze_qi_donor_transient.py',
    'harness/native_qnc_residual_reason_producer.py',
    'harness/native_replay_compare.py',
}
UPSTREAM_FILES = {
    'harness/evidence/native_qi_outflow_terms_2026-10-30/manifest.json',
    'harness/evidence/native_qnc_host_backoff_2026-10-27/manifest.json',
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_files(root: Path, pins: dict[str, str]) -> None:
    if not isinstance(pins, dict) or not pins:
        raise ValueError('empty QI boundary source/data inventory')
    for relative, digest in pins.items():
        item = Path(relative)
        if item.is_absolute() or '..' in item.parts:
            raise ValueError('unsafe QI boundary inventory path')
        path = root / item
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            raise ValueError('QI boundary inventory path escapes root')
        if sha(path) != digest:
            raise ValueError(f'QI boundary pinned file changed: {relative}')


def _verify_rk_delta(delta: dict, expected_new: str) -> None:
    if (delta.get('schema') != 'kdm6.qi_postmicro_rk_writer_single_delta.v1' or
            delta.get('old_relative_path') !=
            'harness/evidence/native_qnc_live_guard_2026-10-30/data/alpha025/rk_writer.tsv'):
        raise ValueError('RK writer delta source differs')
    old = REPO / delta['old_relative_path']
    if sha(old) != delta['old_sha256']:
        raise ValueError('old RK writer differs')
    rows = old.read_bytes().splitlines(keepends=True)
    number = delta['line_number_1based']
    if (len(rows) != delta['line_count'] or number != 53001 or
            rows[number - 1].decode().rstrip('\r\n') != delta['old_line'] or
            delta['old_line'] != 'VAL\t3\t0\tPOST_FINISH\t1\t33\t168\tQI\tf32\t00000002' or
            delta['new_line'] != 'VAL\t3\t0\tPOST_FINISH\t1\t33\t168\tQI\tf32\t00000000'):
        raise ValueError('RK writer delta record differs')
    old_row = rows[number - 1]
    newline = b'\r\n' if old_row.endswith(b'\r\n') else b'\n'
    rows[number - 1] = delta['new_line'].encode() + newline
    if hashlib.sha256(b''.join(rows)).hexdigest() != expected_new or delta['new_sha256'] != expected_new:
        raise ValueError('RK writer delta does not reconstruct trace hash')


def _case_analysis(case: str, execution: dict, parent: dict, m0: np.ndarray) -> dict:
    item = execution['cases'][case]
    runs = item['runs']
    off = runs['pilot_off_trace_on']
    on = runs['pilot_on_trace_on']
    untraced = runs['pilot_on_trace_off']
    prior = parent['runs'][case]['on']
    if (item['parent_checkpoint_sha256'] != prior['checkpoint_sha256'] or
            off['checkpoint_sha256'] != prior['checkpoint_sha256'] or
            item['candidate_checkpoint_sha256'] != on['checkpoint_sha256'] or
            on['checkpoint_sha256'] != untraced['checkpoint_sha256'] or
            len({off['applied_ack_sha256'], on['applied_ack_sha256'],
                 untraced['applied_ack_sha256'], prior['applied_ack_sha256']}) != 1 or
            any(row['host_steps_completed'] != 1 for row in runs.values()) or
            untraced['trace_sha256']):
        raise ValueError(f'QI boundary host lineage or trace pair differs: {case}')
    base_trace = prior['trace_sha256']
    for name in ('qi_face', 'qi_outflow', 'qnc_candidate_faces'):
        if (off['trace_sha256'].get(name) != base_trace[name] or
                on['trace_sha256'].get(name) != base_trace[name]):
            raise ValueError(f'upstream QI/QNC trace changed: {case}/{name}')
    if off['trace_sha256'].get('qi_donor') != base_trace['qi_donor']:
        raise ValueError('pilot-off donor trace changed')
    for mode, row in (('off', off), ('on', on)):
        data = PACKET / 'data' / case / f'pilot_{mode}.tsv'
        if row['trace_sha256'].get('qi_post_bdy') != sha(data):
            raise ValueError('post-boundary trace/receipt differs')
    if on['trace_sha256'].get('qi_donor') != sha(
            PACKET / 'data' / case / 'qi_donor_pilot_on.tsv'):
        raise ValueError('pilot-on donor trace differs')
    if case == 'alpha025':
        delta_path = PACKET / 'data/alpha025/rk_writer_delta.json'
        if item['rk_writer_delta_sha256'] != sha(delta_path):
            raise ValueError('alpha RK writer delta pin differs')
        delta = json.loads(delta_path.read_text())
        if delta['old_sha256'] != base_trace['rk_writer']:
            raise ValueError('alpha RK writer parent hash differs')
        _verify_rk_delta(delta, on['trace_sha256']['rk_writer'])
    elif on['trace_sha256'].get('rk_writer') != base_trace['rk_writer']:
        raise ValueError('control RK writer changed')
    if off['trace_sha256'].get('rk_writer') != base_trace['rk_writer']:
        raise ValueError('pilot-off RK writer changed')

    data_dir = PACKET / 'data' / case
    for field, name in (('support_analysis_sha256', 'support_analysis.json'),
                        ('checkpoint_comparison_sha256', 'checkpoint_comparison.json'),
                        ('invalid_profiles_sha256', 'invalid_profiles.json'),
                        ('target_checkpoint_words_sha256', 'target_checkpoint_words.json')):
        if item[field] != sha(data_dir / name):
            raise ValueError(f'{case} public receipt hash differs: {name}')
    support = json.loads((data_dir / 'support_analysis.json').read_text())
    compare = json.loads((data_dir / 'checkpoint_comparison.json').read_text())
    invalid = json.loads((data_dir / 'invalid_profiles.json').read_text())
    witness = json.loads((data_dir / 'target_checkpoint_words.json').read_text())
    candidate = item['candidate_checkpoint_sha256']
    if (support.get('checkpoint_sha256') != candidate or
            support.get('M0_profiles') != 53906 or
            support.get('M0_channel_cells') != 377342 or
            support.get('lost_profiles') != 0 or support.get('lost_channel_cells') != 0 or
            compare.get('base_sha256') != item['parent_checkpoint_sha256'] or
            compare.get('candidate_sha256') != candidate or
            compare.get('full_variable_count') != 652 or
            compare.get('full_numeric_elements') != 322426586 or
            compare.get('full_fields_finite_and_complete') is not True or
            set(compare.get('changed_variables', {})) != {'QICE', 'QNICE'} or
            compare.get('new_hard_invalid_flat_indices') != [] or
            invalid.get('checkpoint_sha256') != candidate or
            invalid.get('support_sha256') != SUPPORT_SHA or
            invalid.get('total_columns') != 65988 or
            invalid.get('m0_profile_count') != 53906 or
            invalid.get('m0_channel_cells') != 377342 or
            witness.get('schema') != 'kdm6.native_qi_postmicro_target_checkpoint_words.v1' or
            witness.get('coord_order') != 'i,j,k' or
            witness.get('base_checkpoint_sha256') != item['parent_checkpoint_sha256'] or
            witness.get('candidate_checkpoint_sha256') != candidate or
            witness.get('fields') != {'QI': 'QICE', 'NI': 'QNICE'}):
        raise ValueError(f'{case} fixed support or full checkpoint receipt differs')
    from harness.analyze_qi_postmicro_boundary_pilot import read_trace

    sampled_off = read_trace(data_dir / 'pilot_off.tsv', 0)['values']
    sampled_on = read_trace(data_dir / 'pilot_on.tsv', 1)['values']
    expected_coords = {f'{i},168,{k}' for i in (1, 2) for k in range(30, 34)}
    if set(witness['before']) != expected_coords or set(witness['after']) != expected_coords:
        raise ValueError(f'{case} checkpoint witness coordinate inventory differs')
    for i in (1, 2):
        for k in range(30, 34):
            key = f'{i},168,{k}'
            if set(witness['before'][key]) != {'QI', 'NI'} or set(witness['after'][key]) != {'QI', 'NI'}:
                raise ValueError(f'{case} checkpoint witness moment inventory differs')
            for field in ('QI', 'NI'):
                if (witness['before'][key][field] != sampled_off[('AFTER', i, k, field)] or
                        witness['before'][key][field] != sampled_on[('BEFORE', i, k, field)] or
                        witness['after'][key][field] != sampled_on[('AFTER', i, k, field)]):
                    raise ValueError(f'{case} checkpoint words differ from boundary trace')
    indices = invalid['hard_invalid_flat_indices_zero_based']
    if (not isinstance(indices, list) or indices != sorted(set(indices)) or
            any(type(index) is not int or index < 0 or index >= 65988 for index in indices) or
            len(indices) != invalid['hard_invalid_profile_count'] or
            invalid['m0_lost_flat_indices_zero_based'] != [] or
            invalid['m0_lost_channel_cells'] != 0 or
            any(m0[index].any() for index in indices) or
            compare['hard_invalid_profiles_candidate'] != len(indices) or
            len(compare['new_hard_invalid_flat_indices']) != 0):
        raise ValueError(f'{case} invalid-profile list differs from original M0')
    changes = {}
    for name in ('QICE', 'QNICE'):
        row = compare['moment_changes'][name]
        sides = row['changed_by_side_with_corner_overlap']
        if (row['changed_elements'] <= 0 or
                row['changed_boundary_elements'] != row['changed_elements'] or
                row['changed_interior_elements'] != 0 or
                sides['west'] + sides['east'] + sides['south'] + sides['north'] -
                sides['corner_overlap'] != row['changed_elements'] or
                compare['changed_variables'][name]['mismatch_count'] != row['changed_elements']):
            raise ValueError(f'{case} boundary-only field change inventory differs')
        changes[name] = {'elements': row['changed_elements'],
                         'sides_with_corner_overlap': sides,
                         'raw_delta_sum': row['raw_delta_sum']}
    for name in ('QCLOUD', 'QNCLOUD'):
        if compare['moment_changes'][name]['changed_elements'] != 0:
            raise ValueError('unrelated cloud moment changed')
    return {
        'checkpoint_sha256': candidate,
        'parent_checkpoint_sha256': item['parent_checkpoint_sha256'],
        'trace_off_on_checkpoint_and_ACK_equal': True,
        'checkpoint_bound_target_donor_words_joined': True,
        'M0_hard_moment_lost_profiles': 0,
        'M0_hard_moment_lost_channel_cells': 0,
        'full_domain_hard_invalid_profiles': len(indices),
        'full_domain_new_hard_invalid_vs_parent': len(compare['new_hard_invalid_flat_indices']),
        'changed_checkpoint_variables': changes,
    }


def build_analysis() -> dict:
    if sha(SUPPORT) != SUPPORT_SHA:
        raise ValueError('original support mask source changed')
    with np.load(SUPPORT, allow_pickle=False) as archive:
        m0 = np.asarray(archive['m0_mask'], dtype=np.bool_)
    if m0.shape != (65988, 7) or int(m0.sum()) != 377342:
        raise ValueError('original M0 inventory differs')
    execution = json.loads((PACKET / 'execution_summary.json').read_text())
    parent = json.loads((PARENT / 'execution_summary.json').read_text())
    if (execution.get('schema') != 'kdm6.native_qi_postmicro_execution_summary.v1' or
            execution.get('host_steps_completed') != 6 or
            execution.get('RTTOV_calls') != 0 or execution.get('optimizer_calls') != 0 or
            execution.get('parent_manifest_sha256') != sha(PARENT / 'manifest.json') or
            execution.get('parent_analysis_sha256') != sha(PARENT / 'analysis.json') or
            execution.get('parent_execution_summary_sha256') != sha(PARENT / 'execution_summary.json') or
            execution.get('base_executable_sha256') != parent['executable_sha256'] or
            execution.get('dso_sha256') != parent['dso_sha256'] or
            execution.get('changed_archive_members') != ['solve_em.o'] or
            execution.get('overlay_sha256') != sha(
                REPO / 'harness/native_qi_postmicro_boundary_pilot_overlay.py')):
        raise ValueError('QI boundary execution lineage differs')
    from harness.analyze_qi_postmicro_boundary_pilot import analyze

    paths = {(case, mode): PACKET / 'data' / case / f'pilot_{mode}.tsv'
             for case in ('control', 'alpha025') for mode in ('off', 'on')}
    donors = {case: PACKET / 'data' / case / 'qi_donor_pilot_on.tsv'
              for case in ('control', 'alpha025')}
    sample = analyze(paths, donors)
    sample_bytes = (json.dumps(sample, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    if sample_bytes != (PACKET / 'sample_analysis.json').read_bytes():
        raise ValueError('sampled boundary analysis differs from published bytes')
    cases = {case: _case_analysis(case, execution, parent, m0)
             for case in ('control', 'alpha025')}
    return {
        'schema': 'kdm6.native_qi_postmicro_boundary_host.v1',
        'host_steps_completed': 6,
        'offline_model_calls': {'host': 0, 'KDM6': 0, 'RTTOV': 0, 'optimizer': 0},
        'original_M0_profiles': 53906,
        'original_M0_channel_cells': 377342,
        'alpha_k33_target_QI_before_after': sample['alpha025_k33_target_qi'],
        'cases': cases,
        'whole_M0_RTTOV_cost_defined_in_this_packet': False,
        'candidate_is_diagnostic_not_accepted': True,
    }


def _verify_manifest(manifest: dict) -> None:
    if manifest.get('schema') != 'kdm6.native_qi_postmicro_boundary_manifest.v1':
        raise ValueError('QI boundary manifest schema differs')
    if (set(manifest.get('packet_files_sha256', {})) != PACKET_FILES or
            set(manifest.get('external_source_pins', {})) != EXTERNAL_FILES or
            set(manifest.get('upstream_manifest_pins', {})) != UPSTREAM_FILES or
            manifest.get('analysis_sha256') != sha(PACKET / 'analysis.json') or
            manifest.get('support_masks_sha256') != SUPPORT_SHA or
            manifest.get('offline_model_calls') !=
            {'host': 0, 'KDM6': 0, 'RTTOV': 0, 'optimizer': 0}):
        raise ValueError('QI boundary manifest inventory or summary differs')
    _verify_files(PACKET, manifest['packet_files_sha256'])
    _verify_files(REPO, manifest['external_source_pins'])
    _verify_files(REPO, manifest['upstream_manifest_pins'])


def main() -> int:
    manifest = json.loads((PACKET / 'manifest.json').read_text())
    _verify_manifest(manifest)
    parent = importlib.import_module('harness.evidence.native_qi_outflow_terms_2026-10-30.replay')
    parent.main()
    result = build_analysis()
    payload = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n').encode()
    if payload != (PACKET / 'analysis.json').read_bytes():
        raise ValueError('QI boundary analysis differs from published bytes')
    print('REPLAY_PASSED')
    print('analysis_sha256:')
    print(hashlib.sha256(payload).hexdigest())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
