"""Three source-proposed scalar selectors; no execution or science authority."""

SCHEMA = 'kdm6.synthetic33.selector_proposal.v1'
SOURCE_SNAPSHOT_SHA256 = '033558eb6f771beb76d6ba8ebbc1aa126c4abafd4eb6d53dcabd3361cb8a1038'
STATUS = 'SPEC_ONLY'
ELIGIBILITY = 'NOT_ELIGIBLE'
CENTERS = ('baseline', 'warm_vertical', 'ice_vertical')
DIRECTIONS = ('nc', 'th')
# B=1,K=39: packed bottom-first index 23 maps to capture top index 15 and level 24.
LAYER = {'scope': 'layer', 'b_zero': 0, 'k_zero': 15, 'native_level_bottom_first': 24, 'B': 1, 'K': 39}
SELECTORS = {
    'nc_snap1.nc_before': {'stage': 'nc_snap1', 'field': 'nc_before', 'family': 'microphysics',
                           'outer_loop': 0, 'one_step_call': 1, 'substep_n': 0, 'event_ordinal': 0},
    'a5_satadj.qc_final': {'stage': 'a5_satadj', 'field': 'qc_final', 'family': 'microphysics',
                           'outer_loop': 0, 'one_step_call': 1, 'substep_n': 0, 'event_ordinal': 0},
    'a7_main_selected.qr_state': {'stage': 'a7_main_selected', 'field': 'qr_state', 'family': 'sedimentation_main',
                                   'outer_loop': 0, 'one_step_call': 0, 'substep_n': 1, 'event_ordinal': 0},
}
BUDGET = {'forwards': 33, 'graph_primal': 9, 'intermediate_jvp': 18, 'intermediate_vjp': 9,
          'wall_seconds': 900, 'peak_rss_kib': 4 * 1024 * 1024}
# These thresholds are proposals, not a finding that any selected scalar is active.
GATES = {'absolute_tolerance': 1e-8, 'relative_tolerance': 1e-5, 'minimum_fd_signal': 1e-8,
         'require_finite': True, 'require_nonzero_direction': True, 'require_connected_derivative': True,
         'require_identical_full_dynamic_identity': True, 'require_branch_and_schedule_evidence': True,
         'incomplete_branch_coverage': 'INCONCLUSIVE', 'units': 'UNRESOLVED'}


def proposed_manifest():
    """Return a fresh manifest for review; no call to the model is authorized."""
    return {'schema': SCHEMA, 'status': STATUS, 'eligibility': ELIGIBILITY,
            'source_snapshot_sha256': SOURCE_SNAPSHOT_SHA256, 'centers': list(CENTERS),
            'directions': list(DIRECTIONS), 'layer': dict(LAYER),
            'selectors': {name: dict(spec) for name, spec in SELECTORS.items()},
            'budget': dict(BUDGET), 'gates': dict(GATES),
            'handle_contract': 'All graph primal/JVP/VJP queries precede same-thread handle close and sidecar clear.',
            'scope': 'Predeclared synthetic proposal only; missing selectors, branch changes, inactive signals, limits, or incomplete coverage are INCONCLUSIVE.'}


def resolve(records, selector, call):
    """Find exactly one full v1 scalar identity or return INCONCLUSIVE.

    This checks metadata consistency only; it does not authenticate records, read
    graph values, prove coverage, or assert that the record exists in a fixture.
    """
    if selector not in SELECTORS or type(records) is not list or type(call) is not dict:
        raise ValueError('selector, records or call')
    if set(call) != {'input_id', 'mode', 'runtime_call'} or type(call['input_id']) is not str or not call['input_id'] or call['mode'] not in ('capture_on_value', 'center_joint_graph') or type(call['runtime_call']) is not int or call['runtime_call'] < 1:
        raise ValueError('call identity')
    expected = {**SELECTORS[selector], **LAYER, **call, 'record_kind': 'value'}
    matches = [index for index, row in enumerate(records) if type(row) is dict and
               all(type(row.get(key)) is type(value) and row[key] == value for key, value in expected.items())]
    if len(matches) != 1:
        return {'status': 'INCONCLUSIVE', 'reason': 'missing or ambiguous full selector', 'match_count': len(matches),
                'eligibility': ELIGIBILITY}
    return {'status': STATUS, 'eligibility': ELIGIBILITY, 'record_index': matches[0],
            'identity': expected, 'scope': 'Untrusted metadata only; graph handle lifetime and derivative validity not established.'}
