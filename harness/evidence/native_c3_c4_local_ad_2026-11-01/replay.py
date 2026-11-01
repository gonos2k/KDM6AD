"""Native consumed-operand, frozen-other-rates local C3/C4 AD replay."""
import hashlib
import importlib.util
import json
import math
import struct
from pathlib import Path

import torch

from oracle.kdm6.cold import (default_dep_sub_params, default_ice_nucleation_params,
                              dep_sub_torch, ice_nucleation_torch)

ROOT = Path(__file__).resolve().parents[3]
PR = ROOT / 'harness/evidence/native_c3_c4_dsd_call_2026-11-01'
PIN = 'ef185f41ef0aca0226c980ee0449c7e8ec4809770c98e46a09acfc113c38a224'


def packet():
    pins = json.loads((Path(__file__).parent / 'source_manifest.json').read_text())
    for relative, expected in pins.items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError('source digest mismatch: ' + relative)
    spec = importlib.util.spec_from_file_location('packet_verify', PR / 'verify_packet.py')
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    verify.verify_sources()
    raw = (PR / 'selected_packet.json').read_bytes()
    verify.verify(raw, PIN)
    return json.loads(raw), verify


def bits(v):
    return struct.pack('<d', float(v))


class Replay:
    def __init__(self, k):
        p, verifier = packet()
        rows = [r for r in p['selected_rows'] if int(r['k_zero']) == k - 1]
        self.v = {(r['stage'], r['field']): verifier.number(r) for r in rows}
        self.dt = next(verifier.number(m['rows'][0]) for m in p['capture_metadata']
                       if m['rows'][0]['B'] == '32248')
        self.ni = self.v['c3_in', 'state.ni']
        self.n0 = self.v['c4_in', 'n0i']

    def __call__(self, ni, n0):
        v, dt = self.v, self.dt
        def t(stage, field):
            return torch.tensor(v[stage, field], dtype=torch.float64)
        c3 = ice_nucleation_torch(t('c3_in', 'pre.supcol'), t('c3_in', 'pre.supsat'),
            t('c3_in', 'pre.rh_ice'), t('c3_in', 'prevp'), ni, t('c3_in', 'forcing.dend'),
            params=default_ice_nucleation_params(), dtcld=dt)
        c4_fields = ['state.qi', 'state.qs', 'state.qg']
        args = [t('c4_in', x) for x in c4_fields]
        args += [t('c3_in', x) for x in ['pre.rh_ice', 'pre.supcol', 'pre.supsat', 'prevp']]
        args += [c3.pinud, c3.ifsat, n0]
        args += [t('c4_in', x) for x in ['n0so', 'n0go', 's.n0sfac_field', 'work1_ice',
            'pre.work2', 'pre.precg2', 's.rslope_s', 's.rslope2_s', 's.rslopeb_s',
            's.rslopemu_s', 's.rslope_g', 's.rslope2_g', 's.rslopeb_g', 's.rslopemu_g',
            's.rslope2_i', 's.rslopemu_i']]
        c4 = dep_sub_torch(*args, params=default_dep_sub_params(), dtcld=dt)
        def rate(name):
            return {'pinud': c3.pinud, 'ninud': c3.ninud, 'pidep': c4.pidep}.get(name, t('limited', 'scaled.cold.' + name))
        qi_inner = (rate('psaut') + rate('praci') + rate('psaci') + rate('pgaci')
                    - rate('pinud') - rate('pidep') - rate('piacw') - rate('pmulcs')
                    - rate('pmulcg') - rate('pmulrs') - rate('pmulrg'))
        ni_inner = (-rate('nraci') - rate('nsaci') - rate('ngaci') - rate('niacr')
                    + rate('ninud') + rate('nmulcs') + rate('nmulcg') + rate('nmulrs')
                    + rate('nmulrg') - rate('nsaut'))
        cold = float(v['c3_in', 'pre.supcol'] >= 0)
        qi = torch.clamp(t('state_in', 'working.qi') + cold * (-qi_inner) * dt, min=0)
        ni_out = torch.clamp(ni * (~c4.ice_complete_sublim).to(torch.float64)
                             + cold * ni_inner * dt, min=0)
        return torch.stack((c3.pinud, c3.ninud, c4.pidep, qi, ni_out)), c3, c4

    def signature(self, ni, n0):
        out, c3, c4 = self(ni, n0)
        v = self.v
        sup, sat, rh, prev = [v['c3_in', x] for x in ('pre.supcol', 'pre.supsat', 'pre.rh_ice', 'prevp')]
        p = default_ice_nucleation_params()
        nid = min(max(p.cooper_a * math.exp(p.cooper_b * sup) * p.cooper_unit, 0), p.nid_max)
        # Identify strict winning candidate using source-order baseline constant.
        den = max(v['c3_in', 'forcing.dend'], 1e-9)
        from oracle.kdm6 import fconst as fc
        rn = fc._f32(p.rinud)
        mi = fc._f32(fc._f32(fc._f32(fc._f32(4 / 3) * fc._f32(fc.PI)) * fc._f32(p.deni)) * fc._f32(fc._f32(rn * rn) * rn))
        candidates = [(nid - float(ni)) / self.dt / den * mi, 0.5 * sat / self.dt, sat / self.dt - prev]
        outer = (sup > p.supcol_threshold and sat > 0) or rh > p.rh_ice_threshold
        if outer and nid > float(ni) and candidates.count(min(candidates)) != 1:
            raise ValueError('C3 cap tie in local derivative probe')
        raw = (4 * float(n0) * v['c4_in', 's.rslopemu_i'] * v['c4_in', 's.rslope2_i']
               * (rh - 1) / max(v['c4_in', 'work1_ice'], 1e-9))
        caps = [raw, -v['c4_in', 'state.qi'] / self.dt, 0.5 * sat / self.dt,
                sat / self.dt - prev - float(c3.pinud)] if raw < 0 else [raw, 0.5 * sat / self.dt, sat / self.dt - prev - float(c3.pinud)]
        entered_ice = sup > 0 and v['c4_in', 'state.qi'] > 0 and not bool(c3.ifsat)
        selected_cap = max(caps) if raw < 0 else min(caps)
        if entered_ice and caps.count(selected_cap) != 1:
            raise ValueError('C4 ice cap tie in local derivative probe')
        ice_sat = bool(c3.ifsat) or (entered_ice and abs(prev + float(c3.pinud) + float(c4.pidep)) >= abs(sat / self.dt))
        entered_snow = sup > 0 and v['c4_in', 'state.qs'] > 0 and not ice_sat
        snow_sat = ice_sat or (entered_snow and abs(prev + float(c3.pinud) + float(c4.pidep) + float(c4.psdep)) >= abs(sat / self.dt))
        entered_graupel = sup > 0 and v['c4_in', 'state.qg'] > 0 and not snow_sat
        return (entered_ice, ice_sat, entered_snow, snow_sat, entered_graupel,
                outer,
                nid > float(ni), candidates.index(min(candidates)), raw < 0,
                caps.index(max(caps) if raw < 0 else min(caps)), bool(c3.ifsat),
                bool(c4.ifsat), bool(c4.ice_complete_sublim), float(out[3]) > 0, float(out[4]) > 0)

    def baseline(self):
        out, c3, c4 = self(torch.tensor(self.ni, dtype=torch.float64), torch.tensor(self.n0, dtype=torch.float64))
        for index, stage, field in [(0, 'c3_out', 'icenuc.pinud'), (1, 'c3_out', 'icenuc.ninud'),
                                    (2, 'c4_out', 'depsub.pidep'), (3, 'state_out', 'new_state.qi'),
                                    (4, 'state_out', 'new_state.ni')]:
            if bits(out[index]) != bits(self.v[stage, field]):
                raise ValueError(f'baseline bits mismatch: {stage}/{field}')
        for field in ('psdep', 'pgdep'):
            if bits(getattr(c4, field)) != bits(self.v['c4_out', 'depsub.' + field]):
                raise ValueError('baseline C4 rate mismatch: ' + field)
        for obj, stage, name in [(c3, 'c3_out', 'icenuc'), (c4, 'c4_out', 'depsub')]:
            for field in (('ifsat',) if name == 'icenuc' else ('ifsat', 'ice_complete_sublim')):
                if bool(getattr(obj, field)) != self.v[stage, name + '.' + field]:
                    raise ValueError('baseline branch mismatch')
        return out

    def derivative(self, mode, h):
        base = self.ni if mode == 'ni' else self.n0
        direction = 1.0 if mode == 'ni' else self.n0
        x = torch.tensor(base, dtype=torch.float64, requires_grad=True)
        fixed = torch.tensor(self.n0 if mode == 'ni' else self.ni, dtype=torch.float64)
        def f(z):
            return self(z, fixed)[0] if mode == 'ni' else self(fixed, z)[0]
        y, j = torch.autograd.functional.jvp(f, x, torch.tensor(direction, dtype=torch.float64))
        vjp = torch.stack([torch.autograd.grad(y[i], x, retain_graph=True)[0] * direction for i in range(5)]) if y.requires_grad else torch.stack([torch.autograd.functional.vjp(f, x, torch.eye(5, dtype=torch.float64)[i])[1] * direction for i in range(5)])
        plus, minus = float(base + h * direction), float(base - h * direction)
        a, b = torch.tensor(plus, dtype=torch.float64), torch.tensor(minus, dtype=torch.float64)
        def sig(z):
            return self.signature(z, fixed) if mode == 'ni' else self.signature(fixed, z)
        if sig(a) != sig(torch.tensor(base, dtype=torch.float64)) or sig(b) != sig(torch.tensor(base, dtype=torch.float64)):
            raise ValueError('branch changed under perturbation')
        fd = (f(a) - f(b)) / ((plus - minus) / direction)
        return {'jvp': j.tolist(), 'vjp': vjp.tolist(), 'fd': fd.tolist()}


def report():
    report = {}
    for k in (21, 23):
        r = Replay(k)
        r.baseline()
        report[k] = {'signature': r.signature(torch.tensor(r.ni, dtype=torch.float64), torch.tensor(r.n0, dtype=torch.float64)),
                     'ni': {str(h): r.derivative('ni', h) for h in (0.1, 1., 10.)},
                     'n0i_relative': r.derivative('n0', 1e-4)}
    return report


if __name__ == '__main__':
    print(json.dumps(report(), indent=2))
