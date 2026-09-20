"""Native-ledger arithmetic checks; synthetic rows are not model evidence."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from replay_native_number import sedimentation_ledger


def synthetic_rows():
    rows = [dict(step=1,loop=1,species=1,substep=1,k=k,pre=0.,post=0.,
                 out=0.,**{'in':0.},rho=1.,qv=0.,dz=1.,offer=0.) for k in range(1,40)]
    rows[1].update(pre=8.,post=4.,out=4.,offer=4.,rho=2.)
    rows[0].update(pre=2.,post=5.,out=1.,offer=1.,rho=.5,**{'in':4.})
    return rows


def test_measures_are_distinct_and_surface_is_separate():
    result = {r['measure']:r for r in sedimentation_ledger(synthetic_rows())}
    v = result['volume_number']
    assert (v['departure'],v['arrival'],v['surface_exit'],v['state_delta']) == (4.,4.,1.,-1.)
    m = result['source_moist_mass_number']
    assert (m['departure'],m['arrival'],m['surface_exit'],m['state_delta']) == (8.,2.,.5,-6.5)
    assert m['interface_mismatch'] == -6. and m['closure'] == 0.
    # Closing a signed ledger is not proof of physical transfer conservation.
    assert m['relative_mismatch'] != 0


@pytest.mark.parametrize('fault',['missing','duplicate','post','incoming'])
def test_incomplete_or_inconsistent_updates_rejected(fault):
    rows = synthetic_rows()
    if fault == 'missing': rows.pop()
    elif fault == 'duplicate': rows.append(dict(rows[0]))
    elif fault == 'post': rows[0]['post'] += 1.
    else: rows[0]['in'] += 1.
    with pytest.raises(AssertionError): sedimentation_ledger(rows)


def test_top_offer_is_not_endpoint_difference():
    rows = synthetic_rows()
    rows[-1].update(pre=1.,post=0.,offer=2.,out=1.)
    result = sedimentation_ledger(rows)
    assert all(r['closure'] == 0 for r in result)


def test_scalar_records_are_lossless_and_unique():
    from replay_native_number import parse_records
    row = 'KDM6BC HOST_ENTRY 1 153 144 0 0 12 host nc 1.29151680000000000E+009'
    assert next(iter(parse_records([row]).values()))['nc'] == 1291516800.
    with pytest.raises(AssertionError): parse_records([row,row])
    with pytest.raises(AssertionError): parse_records([row.replace('153 144','152 143')])
    with pytest.raises(AssertionError): parse_records([row.replace('1.29151680000000000E+009','nan')])


def measured():
    import json
    return json.loads((Path(__file__).resolve().parents[1]/'evidence/native_number_2026-09-20.json').read_text())


def test_actual_native_capture():
    from replay_native_number import replay
    r = replay(measured())
    assert (r['host_rows'],r['producer_rows'],r['nc_update_rows'],r['sedimentation_rows']) == (78,78,78,156)
    ice = next(x for x in r['ledgers'] if x['step']==2 and x['species']=='ice' and x['measure']=='volume_number')
    assert ice['departure'] > 4e8 and 0 < ice['arrival'] < 500
    assert ice['relative_mismatch'] < -.99999 and ice['closure'] == 0
    assert not r['physical_number_basis_resolved'] and not r['accepted_observation_cost']


@pytest.mark.parametrize('fault',['row','field','upper','post','approval','bitwise'])
def test_actual_evidence_faults(fault):
    from replay_native_number import replay, EXPECTED_FIELDS
    d = measured()
    if fault == 'row': d['packed_records'].pop()
    elif fault == 'approval': d['physical_number_basis_resolved'] = True
    elif fault == 'bitwise': d['noninterference']['comparisons'][1]['stdout'] = 'PASS'
    else:
        tag = 'SED_BEFORE' if fault=='upper' else 'NC_AFTER_WARM'
        row = next(r for r in d['packed_records'] if r[0]==tag and r[1]==2)
        if fault == 'field': row.pop()
        else:
            field = 'upper_number' if fault=='upper' else 'nc'
            row[8+sorted(EXPECTED_FIELDS[tag]).index(field)] = -1.
    with pytest.raises((AssertionError,KeyError)): replay(d)


def test_optimized_python_refuses_replay():
    import subprocess
    result = subprocess.run([sys.executable,'-O',str(Path(__file__).resolve().parents[1]/'replay_native_number.py')],capture_output=True,text=True)
    assert result.returncode != 0 and 'assertions must remain enabled' in result.stderr
