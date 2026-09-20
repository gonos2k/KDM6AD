#!/usr/bin/env python3
"""Arithmetic replay of selected native captures, not a physical unit approval."""
import math
import struct
from collections import defaultdict


def f32(value):
    return struct.unpack('f', struct.pack('f', value))[0]


def sedimentation_ledger(rows):
    """Pair actual cell updates with three explicitly conditional measures.

    Interior out/in are recorded post-cap operands. Top removal is derived
    from the recorded offer and pre-state because the source has no stored
    min-departure variable. State rounding is retained separately.
    """
    if not __debug__:
        raise RuntimeError('assertions must remain enabled')
    groups = defaultdict(dict)
    for r in rows:
        key = (r['step'],r['loop'],r['species'],r['substep'])
        k = r['k']
        assert k not in groups[key]
        assert 1 <= k <= 39
        for field in ('pre','post','out','in','rho','qv','dz','offer'):
            assert math.isfinite(r[field]), field
        assert r['rho'] > 0 and r['dz'] > 0 and r['qv'] >= 0
        assert min(r['pre'],r['post'],r['out'],r['in'],r['offer']) >= 0
        if k == 39:
            assert r['in'] == 0
            assert r['out'] == min(r['pre'],r['offer'])
            expected = max(f32(r['pre']-r['offer']),0.)
        else:
            expected = max(f32(f32(r['pre']-r['out'])+r['in']),0.)
        assert r['post'] == expected, (key,k,'state update')
        groups[key][k] = r
    assert groups
    results = []
    for key, cells in sorted(groups.items()):
        assert set(cells) == set(range(1,40)), 'incomplete vertical ledger'
        for measure in ('volume_number','source_moist_mass_number','dry_mass_number'):
            def weight(r):
                if measure == 'volume_number': return r['dz']
                if measure == 'source_moist_mass_number': return r['rho']*r['dz']
                return r['rho']/(1+r['qv'])*r['dz']
            w = {k:weight(r) for k,r in cells.items()}
            state_terms = [w[k]*(r['post']-r['pre']) for k,r in cells.items()]
            rounding_terms = [w[k]*((r['post']-r['pre'])+r['out']-r['in']) for k,r in cells.items()]
            departures = [w[k+1]*cells[k+1]['out'] for k in range(1,39)]
            arrivals = [w[k]*cells[k]['in'] for k in range(1,39)]
            mismatch = math.fsum(a-d for a,d in zip(arrivals,departures))
            surface = w[1]*cells[1]['out']
            state = math.fsum(state_terms)
            rounding = math.fsum(rounding_terms)
            residual = state-(mismatch-surface+rounding)
            scale = math.fsum(map(abs,state_terms))+math.fsum(departures)+math.fsum(arrivals)+surface+math.fsum(map(abs,rounding_terms))
            assert abs(residual) <= 32*math.ulp(scale)
            denominator = math.fsum(departures)
            results.append(dict(step=key[0],loop=key[1],species=key[2],substep=key[3],
                                measure=measure,state_delta=state,interface_mismatch=mismatch,
                                surface_exit=surface,state_rounding=rounding,closure=residual,
                                departure=denominator,arrival=math.fsum(arrivals),
                                relative_mismatch=None if denominator == 0 else mismatch/denominator))
    return results


def parse_records(lines):
    """Read lossless scalar capture records without silently merging duplicates."""
    records = {}
    for line in lines:
        parts = line.split()
        assert len(parts) == 11 and parts[0] == 'KDM6BC', 'bad capture row'
        tag = parts[1]
        step, lat, col, loop, substep, k = map(int,parts[2:8])
        assert (lat,col) == (153,144), 'unexpected host column'
        assert 1 <= k <= 39 and step > 0 and loop >= 0 and substep >= 0
        key = (tag,step,lat,col,loop,substep,k,parts[8])
        field, value = parts[9], float(parts[10])
        assert math.isfinite(value) and f32(value) == value
        record = records.setdefault(key,{})
        assert field not in record, 'duplicate scalar record'
        record[field] = value
    assert records, 'empty capture'
    return records


def _mul(*values):
    value = values[0]
    for x in values[1:]: value = f32(value*x)
    return value


def producer(a):
    """The two source-ordered binary32 producer expressions, before/after min."""
    nc,nr,sc,sr = (a[k] for k in ('nc','nr','rslopec3','rslope3_r'))
    big = a['avedia_r'] >= a['di100']
    ratio = f32(a['g4pmr']/a['g1pmr']) if big else f32(a['g7pmr']/a['g1pmr'])
    if big:
        raw_n = _mul(a['ncrk1'],nc,nr,f32(_mul(sc,a['g3pmc'])+_mul(sr,ratio)))
        raw_q = _mul(f32(a['cmc']/a['den']),a['ncrk1'],nc,nr,sc,
                     f32(_mul(sc,a['g6pmc'])+_mul(sr,a['g3pmc'],ratio)))
    else:
        raw_n = _mul(a['ncrk2'],nc,nr,f32(_mul(sc,sc,a['g6pmc'])+_mul(sr,sr)),ratio)
        raw_q = _mul(f32(a['cmc']/a['den']),a['ncrk2'],nc,nr,sc,
                     f32(_mul(sc,sc,a['g9pmc'])+_mul(sr,sr,a['g3pmc'],ratio)))
    if a['qr'] < a['lenconcr']: return 0.,0.
    return min(raw_q,f32(a['qc']/a['dt'])),min(raw_n,f32(nc/a['dt']))


HOST_FIELDS = {'qc','nc','qr','nr','den','p','delz','qv'}
PRODUCER_FIELDS = {'qc','nc','qr','nr','den','qv','rslopec3','rslope3_r',
                  'avedia_r','dt','lenconcr','di100','ncrk1','ncrk2','cmc',
                  'g3pmc','g6pmc','g9pmc','g1pmr','g4pmr','g7pmr'}
BUDGET_FIELDS = {'nc','qc','nr','qr','dt','cold','den','qv','delz','p',
                 'nraut','nccol','nracw','niacw','naacw','pracw'}
TOP_FIELDS = {'number','offer','rho','operator_rho','qv','dz','mstep','dt'}
SED_FIELDS = TOP_FIELDS | {'departure','incoming','upper_number','upper_rho','upper_dz'}
EXPECTED_FIELDS = {**{t:HOST_FIELDS for t in ('HOST_ENTRY','LOCAL_ENTRY','LOCAL_RETURN','HOST_RETURN')},
                   'PRODUCER_INPUT':PRODUCER_FIELDS,'PRODUCER_OUTPUT':{'pracw','nracw'},
                   **{t:BUDGET_FIELDS for t in ('LIMIT_INPUT','NC_BEFORE_COLD','NC_BEFORE_WARM','NC_AFTER_COLD','NC_AFTER_WARM')},
                   'TOP_BEFORE':TOP_FIELDS,'TOP_AFTER':TOP_FIELDS,
                   'SED_BEFORE':SED_FIELDS,'SED_AFTER':SED_FIELDS}


def replay_capture(lines):
    records = parse_records(lines)
    for key,fields in records.items():
        assert key[0] in EXPECTED_FIELDS
        assert set(fields) == EXPECTED_FIELDS[key[0]], ('missing capture fields',key)
    def paired(key,tag):
        return records[(tag,)+key[1:]]
    host_count = budget_count = producer_count = 0
    sed = []
    for key,r in records.items():
        tag,step,lat,col,loop,n,k,species = key
        if tag == 'HOST_ENTRY':
            assert r == paired(key,'LOCAL_ENTRY')
            assert paired(key,'LOCAL_RETURN') == paired(key,'HOST_RETURN')
            host_count += 1
        elif tag == 'PRODUCER_INPUT':
            qrate,nrate = producer(r)
            out = paired(key,'PRODUCER_OUTPUT')
            for name,expected in (('pracw',qrate),('nracw',nrate)):
                assert out[name] == expected, ('producer',key,name,out[name],expected)
            producer_count += 1
        elif tag in ('NC_BEFORE_COLD','NC_BEFORE_WARM'):
            assert r['cold'] == (tag == 'NC_BEFORE_COLD')
            post = paired(key,tag.replace('BEFORE','AFTER'))
            rate = -r['nraut']
            for name in ['nccol','nracw']+(['niacw'] if r['cold'] else [])+['naacw','naacw']:
                rate = f32(rate-r[name])
            expected = max(f32(r['nc']+f32(rate*r['dt'])),0.)
            assert post['nc'] == expected, ('nc budget',key,post['nc'],expected)
            budget_count += 1
        elif tag in ('TOP_BEFORE','SED_BEFORE'):
            post = paired(key,tag.replace('BEFORE','AFTER'))
            assert r['operator_rho'] == r['rho']
            if tag == 'SED_BEFORE':
                upper_tag = 'TOP_AFTER' if k == 38 else 'SED_AFTER'
                upper = records[(upper_tag,step,lat,col,loop,n,k+1,species)]
                assert r['upper_number'] == upper['number'], 'upper updated state'
                assert r['upper_rho'] == upper['rho'] and r['upper_dz'] == upper['dz']
                assert r['departure'] == min(r['offer'],r['number'])
                assert r['incoming'] <= r['upper_number'], 'upper storage cap'
            for field in set(r)-{'number'}: assert post[field] == r[field], ('changed operand',key,field)
            sed.append(dict(step=step,loop=loop,species=species,substep=n,k=k,
                            pre=r['number'],post=post['number'],
                            out=min(r['number'],r['offer']) if tag=='TOP_BEFORE' else r['departure'],
                            **{'in':0. if tag=='TOP_BEFORE' else r['incoming']},
                            rho=r['rho'],qv=r['qv'],dz=r['dz'],offer=r['offer']))
    assert host_count == 78, 'two host calls, all 39 layers required'
    assert producer_count == budget_count == 78
    for step in (1,2):
        for k in range(1,40):
            base = (step,153,144,1,0,k,'cloud')
            for tag in ('PRODUCER_INPUT','PRODUCER_OUTPUT','LIMIT_INPUT'):
                assert (tag,)+base in records
            arms = [arm for arm in ('COLD','WARM') if ('NC_BEFORE_'+arm,)+base in records]
            assert len(arms) == 1
            assert ('NC_AFTER_'+arms[0],)+base in records
    for step in (1,2):
        for tag in ('HOST_ENTRY','LOCAL_ENTRY','LOCAL_RETURN','HOST_RETURN'):
            assert {key[6] for key in records if key[0]==tag and key[1]==step} == set(range(1,40))
    expected_keys = set()
    for step in (1,2):
        for k in range(1,40):
            for tag in ('HOST_ENTRY','LOCAL_ENTRY','LOCAL_RETURN','HOST_RETURN'):
                expected_keys.add((tag,step,153,144,0,0,k,'cloud'))
            for tag in ('PRODUCER_INPUT','PRODUCER_OUTPUT','LIMIT_INPUT'):
                expected_keys.add((tag,step,153,144,1,0,k,'cloud'))
            for arm in ('COLD','WARM'):
                before = ('NC_BEFORE_'+arm,step,153,144,1,0,k,'cloud')
                if before in records:
                    expected_keys.add(before)
                    expected_keys.add(('NC_AFTER_'+arm,)+before[1:])
        for species in ('rain','ice'):
            top_key = ('TOP_BEFORE',step,153,144,1,1,39,species)
            count = records[top_key]['mstep']
            assert count >= 1 and count == int(count)
            for substep in range(1,int(count)+1):
                for k in range(1,40):
                    for side in ('BEFORE','AFTER'):
                        key = (('TOP_' if k==39 else 'SED_')+side,step,153,144,1,substep,k,species)
                        assert records[key]['mstep'] == count
                        expected_keys.add(key)
    assert set(records) == expected_keys, 'unexpected or incomplete capture identities'
    ledgers = sedimentation_ledger(sed)
    assert any(r['departure'] > 0 and r['arrival'] > 0 for r in ledgers), 'nonzero transfer required'
    return dict(scope='native_capture_arithmetic_only',host_rows=host_count,
                producer_rows=producer_count,nc_update_rows=budget_count,
                sedimentation_rows=len(sed),ledgers=ledgers,
                physical_number_basis_resolved=False,accepted_observation_cost=False)


def replay(data):
    if not __debug__: raise RuntimeError('assertions must remain enabled')
    assert data['schema'] == 'native-number-v1'
    assert data['physical_number_basis_resolved'] is False
    assert data['accepted_observation_cost'] is False
    assert data['scope'] == dict(column=35711,host_i=144,host_j=153,levels=39,
                                scheme=37,dt_seconds=20,duration_seconds=40)
    assert len(data['noninterference']['comparisons']) == 3
    for frame,c in enumerate(data['noninterference']['comparisons']):
        assert c['frame'] == frame and c['returncode'] == 0
        assert '254 common, 254 BITWISE-MATCH, 0 DIFFER, 0 unsupported/skipped' in c['stdout']
    lines = []
    for row in data['packed_records']:
        tag = row[0]
        assert tag in EXPECTED_FIELDS
        fields = sorted(EXPECTED_FIELDS[tag])
        assert len(row) == 8+len(fields)
        prefix = ' '.join(map(str,row[:8]))
        for field,value in zip(fields,row[8:]):
            lines.append(f'KDM6BC {prefix} {field} {value!r}')
    return replay_capture(lines)


if __name__ == '__main__':
    import argparse
    import json
    from pathlib import Path
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence',nargs='?',type=Path,
                        default=Path(__file__).parent/'evidence/native_number_2026-09-20.json')
    print(json.dumps(replay(json.loads(parser.parse_args().evidence.read_text())),indent=2))
