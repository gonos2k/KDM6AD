"""Conditional C5 local derivatives from PR511's inferred call operands.

The packet does not capture C5 inputs. Coordinator source rebuilds pre2 from
working, whose temperature is unchanged before C5. The T0-supcol roundtrip
is checked against step-entry T, but is corroboration, not direct capture.
Matching saved limited rates does not establish the limiter's derivative. The
state composition assumes C5 passes the limiter unchanged under perturbation.
"""
import json
import math

import torch

from oracle.kdm6 import fconst as fc
from oracle.kdm6.cold import default_ice_aggregation_params, ice_aggregation_torch
from oracle.kdm6.thermo import default_thermo_params

from .replay import Replay, bits


class C5Replay:
    def __init__(self, k):
        r = Replay(k)
        v = r.v
        self.v = v
        self.qi = v['c4_in', 'state.qi']
        self.ni = v['c3_in', 'state.ni']
        if (bits(self.qi) != bits(v['state_in', 'working.qi'])
                or bits(self.ni) != bits(v['state_in', 'working.ni'])):
            raise ValueError('C5 and state-update working operands differ')
        self.den = v['c3_in', 'forcing.dend']
        self.supcol = v['c3_in', 'pre.supcol']
        self.t = v['step_entry', 'state.t']
        self.dt = r.dt
        self.saved = [v['limited', 'scaled.cold.' + name] for name in ('psaut', 'nsaut')]
        self.params = default_ice_aggregation_params()
        if bits(default_thermo_params().t0c - self.supcol) != bits(self.t):
            raise ValueError('inferred temperature roundtrip mismatch')

    def __call__(self, qi):
        def t(x):
            return torch.tensor(x, dtype=torch.float64)
        return torch.stack(ice_aggregation_torch(qi, t(self.ni), t(self.t), t(self.den),
                            t(self.supcol), params=self.params, dtcld=self.dt))

    def state(self, qi):
        """Frozen-other-rate state update, assuming the limiter is locally identity."""
        v = self.v
        psaut, nsaut = self(qi)

        def rate(name):
            return torch.tensor(v['limited', 'scaled.cold.' + name], dtype=torch.float64)

        qi_inner = (psaut + rate('praci') + rate('psaci') + rate('pgaci')
                    - rate('pinud') - rate('pidep') - rate('piacw') - rate('pmulcs')
                    - rate('pmulcg') - rate('pmulrs') - rate('pmulrg'))
        ni_inner = (-rate('nraci') - rate('nsaci') - rate('ngaci') - rate('niacr')
                    + rate('ninud') + rate('nmulcs') + rate('nmulcg') + rate('nmulrs')
                    + rate('nmulrg') - nsaut)
        cold = float(self.supcol >= 0)
        ice_complete = bool(v['c4_out', 'depsub.ice_complete_sublim'])
        qi_out = torch.clamp(qi + cold * (-qi_inner) * self.dt, min=0)
        ni_out = torch.clamp(torch.tensor(self.ni * (not ice_complete), dtype=torch.float64)
                             + cold * ni_inner * self.dt, min=0)
        return torch.stack((qi_out, ni_out))

    def branches(self, qi):
        p = self.params
        qi0 = ((0.4632 * 10 ** (-6 + 0.0413 * self.supcol)) if self.t > p.t_split
               else (0.2316 * 10 ** (-4 - 0.0519 * self.supcol))) * self.den
        alpha = 0.005 * math.exp(-0.025 * self.supcol)
        raw = alpha * (qi - qi0)
        pos = max(raw, 0.0)
        capped = min(pos, qi / self.dt)
        d = fc._f32(p.di125)
        mass = fc._f32(fc._f32(fc._f32(fc._f32(fc.PI) * fc._f32(p.deni))
                              * fc._f32(fc._f32(d * d) * d)) / fc._f32(6.0))
        nsraw = capped * self.den / mass
        return {'active': self.supcol > 0 and qi > 0 and self.ni > 0,
                'warm_arm': self.t > p.t_split, 'qi0': qi0,
                'ps_arm': 'zero' if raw < 0 else ('raw' if pos < qi / self.dt else 'cap'),
                'ns_arm': 'raw' if nsraw < self.ni / self.dt else 'cap',
                'margins': {'supcol': self.supcol, 'qi': qi, 'ni': self.ni,
                            't_split': self.t - p.t_split, 'qi_minus_qi0': qi - qi0,
                            'ps_raw_zero': raw, 'ps_pos_minus_cap': pos - qi / self.dt,
                            'ns_raw_minus_cap': nsraw - self.ni / self.dt},
                'alpha': alpha, 'mass': mass}

    def baseline(self):
        out = self(torch.tensor(self.qi, dtype=torch.float64))
        if any(bits(a) != bits(b) for a, b in zip(out, self.saved)):
            raise ValueError('C5 output differs from saved limited rate bits')
        state = self.state(torch.tensor(self.qi, dtype=torch.float64))
        expected = [self.v['state_out', 'new_state.' + name] for name in ('qi', 'ni')]
        if any(bits(a) != bits(b) for a, b in zip(state, expected)):
            raise ValueError('conditional state baseline bits mismatch')
        return out

    def derivative(self, h):
        x = torch.tensor(self.qi, dtype=torch.float64)
        direction = torch.tensor(self.qi, dtype=torch.float64)
        y, j = torch.autograd.functional.jvp(self, x, direction)
        v = torch.stack([torch.autograd.functional.vjp(self, x, torch.eye(2, dtype=torch.float64)[i])[1]
                         * direction for i in range(2)])
        plus, minus = float(self.qi * (1 + h)), float(self.qi * (1 - h))
        branches = [self.branches(z) for z in (minus, self.qi, plus)]
        def signature(b):
            return (b['active'], b['warm_arm'], b['ps_arm'], b['ns_arm'])
        if not branches[1]['active']:
            raise ValueError('conditional state analytic requires active cold branch')
        if any(signature(b) != signature(branches[1]) for b in branches):
            raise ValueError('C5 branch changed under perturbation')
        fd = (self(torch.tensor(plus, dtype=torch.float64))
              - self(torch.tensor(minus, dtype=torch.float64))) / ((plus - minus) / self.qi)
        b = branches[1]
        if not b['active'] or b['ps_arm'] == 'zero':
            ps = 0.0
        elif b['ps_arm'] == 'raw':
            ps = b['alpha'] * self.qi
        else:
            ps = self.qi / self.dt
        ns = ps * self.den / b['mass'] if b['active'] and b['ns_arm'] == 'raw' else 0.0
        state_value, state_jvp = torch.autograd.functional.jvp(self.state, x, direction)
        state_vjp = torch.stack([
            torch.autograd.functional.vjp(self.state, x, torch.eye(2, dtype=torch.float64)[i])[1]
            * direction for i in range(2)])
        state_fd = (self.state(torch.tensor(plus, dtype=torch.float64))
                    - self.state(torch.tensor(minus, dtype=torch.float64))) / (
                        (plus - minus) / self.qi)
        state_endpoints = [self.state(torch.tensor(z, dtype=torch.float64)).tolist()
                           for z in (minus, self.qi, plus)]
        if any(value <= 0 for endpoint in state_endpoints for value in endpoint):
            raise ValueError('state clamp branch is not strictly positive')
        state_result = {'value': state_value.tolist(), 'jvp': state_jvp.tolist(),
                        'vjp': state_vjp.tolist(), 'fd': state_fd.tolist(),
                        'analytic': [self.qi - self.dt * ps, -self.dt * ns],
                        'clamp_margins_minus_baseline_plus': state_endpoints,
                        'limiter_identity': 'assumed under perturbation'}
        return {'state': state_result, 'value': y.tolist(), 'jvp': j.tolist(), 'vjp': v.tolist(), 'fd': fd.tolist(),
                'analytic': [ps, ns], 'branches_minus_baseline_plus': branches}


def report():
    result = {}
    for k in (21, 23):
        replay = C5Replay(k)
        replay.baseline()
        result[k] = {str(h): replay.derivative(h) for h in (1e-3, 1e-4, 1e-5)}
    return result


if __name__ == '__main__':
    print(json.dumps(report(), indent=2))
