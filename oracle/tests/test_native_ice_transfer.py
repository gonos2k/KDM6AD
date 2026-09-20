"""Existing conservative kernel on native operands and independent transfer cases."""
import json
import math
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'harness'))
from replay_native_ice_transfer import EVIDENCE, replay, call_kernel


def test_actual_native_operands_and_differentiated_inventory():
    d=json.loads(EVIDENCE.read_text())
    p=json.loads((EVIDENCE.parent/'native_number_2026-09-20.json').read_text())
    r=replay(d,p);c=r['cases'][1]
    assert c['legacy']['number_residual'] < -4e8
    assert c['conservative']['number_residual']==0
    assert c['ni_legacy'][16]==0
    assert c['ni_conservative'][16]==pytest.approx(436252.71875*726.5537109375/d['cases'][1]['rows'][16]['dz'],rel=2e-15)
    assert max(c['derivative']['jvp_relative']) < 1e-14
    assert max(c['derivative']['fd_relative']) < 1e-6
    assert abs(c['derivative']['dual_error']) < 1e-8
    assert not r['operational_fix_applied'] and not r['physical_number_basis_resolved']


def state(n,dz,w,fall=None):
    t=lambda a:torch.tensor([a],dtype=torch.float64)
    z=torch.zeros((1,len(n)),dtype=torch.float64)
    return dict(qi=z,ni=t(n),work1=z,workn=t(w),rho=torch.ones_like(z),dz=t(dz),
                fall_qi=z,fall_ni=z if fall is None else t(fall))


def test_empty_donor_unequal_layers_and_stored_fall_not_reinjected():
    x=state([0,8,2],[1,2,4],[1,1,0],[100,200,300])
    o=call_kernel(x,dict(mstep=1,substep=1,dt=1.),True)
    assert torch.equal(o.state.ni,torch.tensor([[0.,0.,6.]],dtype=torch.float64))
    assert torch.equal(o.fall_ni-x['fall_ni'],torch.tensor([[0.,8.,0.]],dtype=torch.float64))
    assert float((o.state.ni*x['dz']).sum())==24.


def test_three_substeps_carry_state_and_actual_bottom_export():
    x=state([8,0,0],[2,3,4],[3,3,3]);initial=16.
    for n in range(1,4):
        o=call_kernel(x,dict(mstep=3,substep=n,dt=1.),True)
        x=dict(x,qi=o.state.qi,ni=o.state.ni,fall_qi=o.fall_qi,fall_ni=o.fall_ni)
        inventory=float((x['ni']*x['dz']).sum()+x['fall_ni'][0,-1]*x['dz'][0,-1])
        assert abs(inventory-initial)<=8*math.ulp(initial)
        assert bool((x['ni']>=0).all())
    assert float(x['ni'].sum())==0 and float(x['fall_ni'][0,-1]*x['dz'][0,-1])==16.
