"""Synthetic, blocked condition bridge; no producer or execution evidence is accepted."""
import copy
import importlib.util
import json
from pathlib import Path

_GATE = Path(__file__).resolve().parent.parent / 'native_host_preflight_2026-11-12' / 'fd_gate.py'
_spec = importlib.util.spec_from_file_location('condition_bridge_fd_gate', _GATE)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

MASKS = ('entry_nc_floor', 'entry_nccn_bounds', 'snap1_per_cell_gate',
         'snap2_per_cell_gate', 'lambda_active', 'lambda_bounds', 'dsd_ncmin',
         'dsd_ncmax', 'cleanup_qc', 'temperature_floor', 'water_es_cap',
         'satadj_paths', 'safe_pow_floor', 'ncact_preclamp', 'nccn_cap_clamp',
         'main_transport_gate', 'ice_transport_gate', 'warm_cold_gate',
         'progb_density_gate')
IDENTITY = ('runtime_call', 'one_step_call', 'outer_loop', 'family', 'substep_n',
            'scope', 'b_zero', 'k_zero', 'native_level_bottom_first', 'stage',
            'field', 'event_ordinal')
SCHEMA = 'kdm6.synthetic_conditions.v2'
PREFIX = '__synthetic_v2__:'


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def normalize(sidecar, call_id):
    """Validate an artificial complete universe, not a real source coverage claim.

    Each synthetic schedule entry requires all 19 IDs at each declared substep;
    an inactive family has one n=0 row per ID, explicitly justified by its gate.
    This deliberately artificial universe is not a proposed physical selector.
    """
    need(type(sidecar) is dict and set(sidecar) == {'schema', 'status', 'call_id', 'schedule', 'records'}, 'sidecar fields')
    need(sidecar['schema'] == SCHEMA and sidecar['status'] == 'SYNTHETIC_ONLY', 'synthetic schema/status required')
    need(type(call_id) is str and call_id and sidecar['call_id'] == call_id, 'wrong call')
    schedule = sidecar['schedule']
    need(type(schedule) is list and schedule, 'schedule required')
    schedules = {}
    for s in schedule:
        need(type(s) is dict and set(s) == {'outer_loop', 'family', 'active', 'substeps'}, 'schedule fields')
        loop, family, active, count = (s[k] for k in ('outer_loop', 'family', 'active', 'substeps'))
        need(type(loop) is int and loop > 0 and family in ('main', 'ice') and type(active) is bool and type(count) is int and ((active and count > 0) or (not active and count == 0)), 'schedule value')
        key = (loop, family)
        need(key not in schedules, 'duplicate schedule')
        schedules[key] = (active, count)
    loops = {k[0] for k in schedules}
    need(loops == set(range(1, max(loops) + 1)), 'schedule loops')
    need(all((loop, family) in schedules for loop in loops for family in ('main', 'ice')), 'schedule families')
    expected = {(loop, family, n, mask) for (loop, family), (active, count) in schedules.items()
                for n in (range(1, count + 1) if active else (0,)) for mask in MASKS}
    records = sidecar['records']
    need(type(records) is list, 'records')
    seen, result = set(), {}
    for r in records:
        need(type(r) is dict and set(r) == set(IDENTITY) | {'mask_id', 'availability', 'value', 'reason', 'call_id'}, 'record fields')
        need(r['call_id'] == call_id, 'wrong record call')
        need(all(type(r[k]) is int for k in ('runtime_call', 'one_step_call', 'outer_loop', 'substep_n', 'b_zero', 'k_zero', 'native_level_bottom_first', 'event_ordinal')), 'identity types')
        need(r['runtime_call'] == 0 and r['one_step_call'] == 0 and r['scope'] == 'column' and r['b_zero'] == 0 and r['k_zero'] == -1 and r['native_level_bottom_first'] == -1 and r['stage'] == 'synthetic' and r['field'] == r['mask_id'] and r['event_ordinal'] == 0, 'synthetic identity')
        key = (r['outer_loop'], r['family'], r['substep_n'], r['mask_id'])
        need(key in expected and key not in seen, 'unknown or duplicate record')
        seen.add(key)
        active = schedules[(key[0], key[1])][0]
        if active:
            need(r['availability'] == 'present' and type(r['value']) is bool and r['reason'] is None, 'active condition')
        else:
            need(r['availability'] == 'inactive' and r['value'] is None and r['reason'] == 'family_gate_false', 'inactive reason')
        identity = tuple(r[k] for k in IDENTITY) + (r['mask_id'],)
        result[identity] = (r['availability'], r['value'], r['reason'])
    need(seen == expected, 'missing records')
    return schedules, result


def evaluate(gate_input, bindings, sidecars):
    """Feed supplemental comparisons through the real gate, synthetic use only.

    bindings maps center and step/role to distinct sidecar call IDs. Each sidecar
    proves only an internally consistent artificial inventory. No receipt is
    validated and no source hook or execution completeness is implied.
    """
    need(type(bindings) is dict and set(bindings) == {'center', 'samples'}, 'bindings')
    samples = gate_input['samples']
    steps = gate_input['plan']['steps']
    need(type(samples) is list and type(steps) is list, 'step inventory')
    sample_ids = [s['id'] for s in samples]
    step_ids = [s['id'] for s in steps]
    need(len(set(sample_ids)) == len(sample_ids) and len(set(step_ids)) == len(step_ids)
         and set(sample_ids) == set(step_ids), 'step identity')
    need(type(bindings['samples']) is dict and set(bindings['samples']) == set(sample_ids), 'sample bindings')
    plans = {s['id']: s for s in steps}
    bound_inputs = {}
    def bind(cid, words):
        need(type(cid) is str and cid and type(words) is list, 'call binding')
        planned = tuple(words)
        need(cid not in bound_inputs or bound_inputs[cid] == planned, 'call ID bound to different planned inputs')
        bound_inputs[cid] = planned
    bind(bindings['center'], gate_input['plan']['center_input_words'])
    slots = [(gate_input['center'], bindings['center'])]
    for sample in samples:
        roles = {'lower', 'upper'} | ({'plus2'} if 'plus2' in sample else set())
        b = bindings['samples'][sample['id']]
        need(type(b) is dict and set(b) == roles, 'role bindings')
        plan = plans[sample['id']]
        need(('plus2_input_words' in plan) == ('plus2' in roles), 'plus2 binding')
        for role in roles:
            bind(b[role], plan[role + '_input_words'])
        slots.extend((sample[role], b[role]) for role in sorted(roles))
    ids = [cid for _, cid in slots]
    need(all(type(x) is str and x for x in ids) and type(sidecars) is dict and set(sidecars) == set(ids), 'sidecar inventory')
    parsed = {cid: normalize(sidecars[cid], cid) for cid in set(ids)}
    # Compare full canonical semantic values. The explicit marker for a missing
    # identity is only formed after each call's own schedule has been validated.
    keys = set().union(*(set(records) for _, records in parsed.values()))
    signatures = {}
    for cid, (sched, records) in parsed.items():
        signatures[cid] = json.dumps({'schedule': sorted((l, f, a, n) for (l, f), (a, n) in sched.items()),
                                     'conditions': [(list(k), records.get(k, ('absent_due_to_schedule', None, None))) for k in sorted(keys)]}, separators=(',', ':'))
    values = sorted(set(signatures.values()))
    data = copy.deepcopy(gate_input)
    copy_slots = [(data['center'], bindings['center'])]
    for sample in data['samples']:
        b = bindings['samples'][sample['id']]
        copy_slots.extend((sample[role], b[role]) for role in sorted(b))
    for obs, cid in copy_slots:
        need(not any(k.startswith(PREFIX) for k in obs['masks']), 'reserved mask namespace')
        for i, signature in enumerate(values):
            obs['masks'][PREFIX + str(i)] = signatures[cid] == signature
    result = gate.evaluate(data, allow_synthetic=True)
    result.update({'condition_bridge_schema': SCHEMA, 'condition_status': 'SYNTHETIC_ONLY',
                   'status': 'DRAFT_BLOCKED', 'gate_eligibility': 'NOT_ELIGIBLE',
                   'scope': 'Synthetic artificial conditions only; no source coverage, receipt, execution, scientific or physical certification.'})
    return result
