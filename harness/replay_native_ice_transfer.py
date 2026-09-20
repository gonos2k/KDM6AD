#!/usr/bin/env python3
"""Run existing ice substeps on captured native operands; no operational fix."""
import json
import math
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'oracle'))
from replay_native_number import f32, EXPECTED_FIELDS

EVIDENCE = Path(__file__).parent/'evidence/native_ice_transfer_2026-09-20.json'
FIELDS = {'native_k','qi','ni','work1','workn','rho','dz','dt','mstep','fall_qi','fall_ni'}


def validate(data):
    if not __debug__: raise RuntimeError('assertions must remain enabled')
    assert data['schema']=='native-ice-transfer-v1'
    for field in ('physical_number_basis_resolved','operational_fix_applied','accepted_observation_cost'):
        assert data[field] is False
    assert [c['step'] for c in data['cases']]==[1,2]
    for c in data['cases']:
        assert (c['loop'],c['substep'],c['mstep'],c['dt'])==(1,1,1,20.)
        assert [r['native_k'] for r in c['rows']]==list(range(39,0,-1))
        for r in c['rows']:
            assert set(r)==FIELDS
            assert all(math.isfinite(v) for v in r.values())
            assert r['rho']>0 and r['dz']>0
            assert min(r['qi'],r['ni'],r['work1'],r['workn'],r['fall_qi'],r['fall_ni'])>=0
            assert (r['dt'],r['mstep'])==(c['dt'],c['mstep'])
            for k in FIELDS-{'work1','workn','native_k'}: assert f32(r[k])==r[k]
    p=data['provenance']
    assert p['prior_capture_scalars_exact'] is True
    assert p['history_sha256']==p['prior_history_sha256']
    assert p['experiment']['experiment_valid'] is True


def native_number(c):
    """Independent mixed-precision replay at actual REAL(4) store boundaries."""
    post=[];offered=[];departure=[];arrival=[];prev_flux=0.
    for k,r in enumerate(c['rows']):
        flux=f32(r['ni']*r['workn']/c['mstep']) # REAL(8) product, REAL(4) store
        offer=f32(flux*c['dt']);out=min(offer,r['ni'])
        inc=0. if k==0 else min(f32(f32(f32(prev_flux*c['rows'][k-1]['dz'])/r['dz'])*c['dt']),post[-1])
        value=max(f32(r['ni']-offer),0.) if k==0 else max(f32(f32(r['ni']-out)+inc),0.)
        post.append(value);offered.append(offer);departure.append(out);arrival.append(inc);prev_flux=flux
    return dict(post=post,offer=offered,departure=departure,arrival=arrival)


def check_native(c,prior):
    rows={tuple(r[:8]):dict(zip(sorted(EXPECTED_FIELDS[r[0]]),r[8:])) for r in prior['packed_records']}
    result=native_number(c)
    for j,r in enumerate(c['rows']):
        k=r['native_k'];tag='TOP' if k==39 else 'SED'
        key=(c['step'],153,144,1,1,k,'ice')
        before=rows[(tag+'_BEFORE',)+key];after=rows[(tag+'_AFTER',)+key]
        assert r['ni']==before['number'] and result['post'][j]==after['number']
        assert result['offer'][j]==before['offer']
        if k!=39:
            assert result['departure'][j]==before['departure'] and result['arrival'][j]==before['incoming']
    return result


def tensors(c,dtype):
    import torch
    return {k:torch.tensor([[r[k] for r in c['rows']]],dtype=dtype) for k in FIELDS-{'native_k','dt','mstep'}}


def call_kernel(x,c,conservative,qi=None,ni=None):
    from kdm6.sedimentation import IceSubstepState,ice_substep_advection_torch,default_substep_advection_params
    from kdm6.sed_conservative import conservative_ice_substep_advection_torch
    fn=conservative_ice_substep_advection_torch if conservative else ice_substep_advection_torch
    return fn(IceSubstepState(x['qi'] if qi is None else qi,x['ni'] if ni is None else ni),
              x['fall_qi'],x['fall_ni'],x['work1'],x['workn'],x['dz'],x['rho'],
              mstep=c['mstep'],n_current=c['substep'],dtcld=c['dt'],params=default_substep_advection_params())


def budget(x,c,o):
    def value(v):return float(v.detach().sum())
    number_pre=value(x['ni']*x['dz']);mass_pre=value(x['qi']*x['rho']*x['dz'])
    number_post=value(o.state.ni*x['dz']);mass_post=value(o.state.qi*x['rho']*x['dz'])
    number_bottom=value((o.fall_ni[:,-1]-x['fall_ni'][:,-1])*c['dt']*x['dz'][:,-1])
    mass_bottom=value((o.fall_qi[:,-1]-x['fall_qi'][:,-1])*c['dt']*x['dz'][:,-1])
    return dict(number_pre=number_pre,number_post=number_post,number_bottom=number_bottom,
                number_residual=number_post+number_bottom-number_pre,
                mass_pre=mass_pre,mass_post=mass_post,mass_bottom=mass_bottom,
                mass_residual=mass_post+mass_bottom-mass_pre,
                nonnegative=bool((o.state.ni>=0).all() and (o.state.qi>=0).all()))


def derivative_budget(x,c):
    """Fixed metrics/work; homogeneous state direction stays on the captured caps."""
    import torch
    def inventory(q,n):
        o=call_kernel(x,c,True,q,n)
        return torch.stack(((o.state.qi*x['rho']*x['dz']).sum()+((o.fall_qi[:,-1]-x['fall_qi'][:,-1])*c['dt']*x['dz'][:,-1]).sum(),
                            (o.state.ni*x['dz']).sum()+((o.fall_ni[:,-1]-x['fall_ni'][:,-1])*c['dt']*x['dz'][:,-1]).sum()))
    q,n=x['qi'],x['ni'];v=(q*.01,n*.01)
    y,jvp=torch.autograd.functional.jvp(inventory,(q,n),v)
    expected=torch.stack(((v[0]*x['rho']*x['dz']).sum(),(v[1]*x['dz']).sum()))
    seed=torch.tensor([.75,-.25],dtype=q.dtype)
    _,vjp=torch.autograd.functional.vjp(inventory,(q,n),seed)
    dual=(vjp[0]*v[0]).sum()+(vjp[1]*v[1]).sum()
    eps=1e-4;fd=(inventory(q+eps*v[0],n+eps*v[1])-inventory(q-eps*v[0],n-eps*v[1]))/(2*eps)
    return dict(jvp=jvp.tolist(),expected=expected.tolist(),fd=fd.tolist(),dual_error=float(dual-(seed*jvp).sum()),
                jvp_relative=((jvp-expected).abs()/expected.abs().clamp_min(1e-300)).tolist(),
                fd_relative=((fd-jvp).abs()/jvp.abs().clamp_min(1e-300)).tolist())


def replay(data,prior):
    import torch
    validate(data);torch.set_num_threads(1)
    results=[]
    for c in data['cases']:
        native=check_native(c,prior)
        x=tensors(c,torch.float64)
        legacy=call_kernel(x,c,False);cons=call_kernel(x,c,True)
        b=budget(x,c,cons)
        assert b['nonnegative']
        for name in ('number','mass'):
            scale=b[name+'_pre']+abs(b[name+'_post'])+abs(b[name+'_bottom'])
            assert abs(b[name+'_residual'])<=32*math.ulp(scale)
        results.append(dict(step=c['step'],native_number_exact=True,legacy=budget(x,c,legacy),conservative=b,
                            ni_legacy=legacy.state.ni.tolist()[0],ni_conservative=cons.state.ni.tolist()[0],
                            qi_legacy=legacy.state.qi.tolist()[0],qi_conservative=cons.state.qi.tolist()[0],
                            derivative=None if c['step']==1 else derivative_budget(x,c)))
    return dict(scope='existing_substep_promoted_float64_not_host_integration',torch_version=torch.__version__,
                physical_number_basis_resolved=False,operational_fix_applied=False,accepted_observation_cost=False,cases=results)


def cpp_compare(executable,data):
    """Optional actual C++ kernel execution; no subprocess is used by normal CI."""
    import subprocess
    import torch
    old=json.loads((EVIDENCE.parent/'native_number_2026-09-20.json').read_text())
    qv={(r[1],r[6]):r[8+sorted(EXPECTED_FIELDS[r[0]]).index('qv')] for r in old['packed_records'] if r[0] in ('TOP_BEFORE','SED_BEFORE') and r[7]=='ice'}
    results=[]
    for c in data['cases']:
        fields=('qi','ni','work1','workn','rho','dz','fall_qi','fall_ni')
        payload=f"39 {c['dt']} {c['mstep']} {c['substep']}\n"+'\n'.join(' '.join(repr(r[k]) for k in fields) for r in c['rows'])+'\n'
        proc=subprocess.run([str(executable)],input=payload,text=True,capture_output=True,check=True)
        groups={};current=None
        for line in proc.stdout.splitlines():
            if line.startswith('RUN '):
                current=line[4:];assert current not in groups;groups[current]={}
            else:
                words=line.split();assert current is not None and words[0] not in groups[current]
                groups[current][words[0]]=[float.fromhex(v) for v in words[1:]]
        assert set(groups)=={'legacy f32','conservative f32','legacy f64','conservative f64'}
        for g in groups.values():
            assert set(g)=={'qi','ni','fall_qi','fall_ni'}
            assert all(len(v)==39 and all(math.isfinite(a) for a in v) for v in g.values())
        assert groups['legacy f32']['ni']==native_number(c)['post'], 'C++ native number mismatch'
        x=tensors(c,torch.float64)
        for name,conservative in [('legacy',False),('conservative',True)]:
            o=call_kernel(x,c,conservative)
            for field,v in [('qi',o.state.qi),('ni',o.state.ni),('fall_qi',o.fall_qi),('fall_ni',o.fall_ni)]:
                assert groups[name+' f64'][field]==v.tolist()[0], ('C++/Python exact promoted comparison',field)
        y=groups['conservative f32'];rows=c['rows']
        inv=math.fsum(y['ni'][k]*rows[k]['dz'] for k in range(39))
        pre=math.fsum(r['ni']*r['dz'] for r in rows)
        bottom=(y['fall_ni'][-1]-rows[-1]['fall_ni'])*c['dt']*rows[-1]['dz']
        from replay_native_number import sedimentation_ledger
        native=native_number(c); ledger_rows=[]
        for k,r in enumerate(rows):
            outgoing=native['departure'][k]
            incoming=0. if k==0 else f32(f32(native['departure'][k-1]*rows[k-1]['dz'])/r['dz'])
            assert y['ni'][k]==f32(f32(r['ni']-outgoing)+incoming)
            ledger_rows.append(dict(step=c['step'],loop=1,species='ice',substep=1,k=r['native_k'],
                                    pre=r['ni'],post=y['ni'][k],out=outgoing,**{'in':incoming},
                                    rho=r['rho'],qv=qv[(c['step'],r['native_k'])],dz=r['dz'],offer=native['offer'][k]))
        volume=next(r for r in sedimentation_ledger(ledger_rows) if r['measure']=='volume_number')
        # Only the existing conservative number measure (dz) is reported here.
        results.append(dict(step=c['step'],mixed_legacy_number_exact=True,promoted_vectors_exact=True,
                            mixed_conservative_number_residual=inv+bottom-pre,
                            mixed_conservative_volume_ledger=volume,outputs=groups))
    return results


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cpp',type=Path,help='separately built native_ice_driver executable')
    args=parser.parse_args()
    data=json.loads(EVIDENCE.read_text())
    prior=json.loads((EVIDENCE.parent/'native_number_2026-09-20.json').read_text())
    result=replay(data,prior)
    if args.cpp:result['cpp']=cpp_compare(args.cpp,data)
    print(json.dumps(result,indent=2))
