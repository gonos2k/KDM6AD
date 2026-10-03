"""One Python KDM step to shared-entry optics and actual RTTOV; qv direction."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import torch

p = argparse.ArgumentParser()
p.add_argument('--repo', required=True, type=Path)
p.add_argument('--profile', required=True, type=Path)
p.add_argument('--fixture', required=True, type=Path)
p.add_argument('--output', required=True, type=Path)
a = p.parse_args()
sys.path.insert(0, str(a.repo / 'oracle'))
from kdm6.state import State, Forcing
from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6.sed_conservative import CONSERVATIVE_SED_FNS
from kdm6.obs.model_profile_builder import RttovProfileConfig, RttovProfileTensors, model_to_rttov_tensors
from kdm6.obs.rttov_input_builder import RttovInputConfig, pack_rttov_input
from kdm6.obs.rttov_case_writer import make_live_run_k

if a.output.exists():
    raise FileExistsError(a.output)
a.output.mkdir(parents=True)
with np.load(a.profile) as f:
    saved = {k: f[k].copy() for k in f.files}
s = State(*(torch.tensor(x, dtype=torch.float64)[None,:] for x in saved['native_state_bottom_up']))
f = Forcing(*(torch.tensor(x, dtype=torch.float64)[None,:] for x in saved['native_forcing_bottom_up']))
assert s.nc.numel() == 39
bg = int(saved['above_model_top_background_mask'].sum())
assert np.array_equal(saved['above_model_top_background_mask'],np.arange(bg+39)<bg)
assert np.array_equal(saved['native_mask'],np.arange(bg+39)>=bg)
for key,value in saved.items():
    assert np.isfinite(value).all(),key
cfg = RttovProfileConfig(2, 'mixing_ratio_kgkg_dry', cloud=True, dry_number=True)
fc=Forcing(*(v[0].flip(0) for v in f))
xland = torch.tensor([float(saved['native_xland'])], dtype=torch.float64)

def cloud(qv):
    entry=s._replace(qv=qv)
    result=_kdm6_pure(entry,f,make_parameters(),dt=20.,xland=xland,
        ncmin_land=10.,ncmin_sea=10.,dry_number=True,
        normalize_ice_handoff=True,sed_substep_fns=CONSERVATIVE_SED_FNS)
    prof=model_to_rttov_tensors(State(*(v[0].flip(0) for v in result)),fc,cfg,
        xland=xland,ncmin_land=10.,ncmin_sea=10.,entry_qv=qv[0].flip(0))
    return prof.t_lay,prof.q_lay,prof.clw,prof.ciw,prof.deff_liq,prof.deff_ice,prof.cfrac

keys = ('T', 'Q', 'HYDRO6', 'HYDRO7', 'HYDRO_DEFF6', 'HYDRO_DEFF7')
source_keys = ('extended_temperature_K','extended_q_ppmv_moist','extended_hydro6_g_m3', 'extended_hydro7_g_m3',
               'extended_hydro_deff6_um', 'extended_hydro_deff7_um')
fixed = {k: saved[v][None, :] for k, v in (
    ('T', 'extended_temperature_K'), ('Q', 'extended_q_ppmv_moist'),
    ('P', 'extended_p_center_hPa'), ('P_HALF', 'extended_p_half_hPa'),
    ('CFRAC', 'extended_cfrac'))}
for key,value in fixed.items():
    assert value.shape==(1,bg+39+(key=='P_HALF')),key
fixture_hashes = {str(p.relative_to(a.fixture)):hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(a.fixture.rglob('*')) if p.is_file()}
input_cfg = RttovInputConfig('installed-AMI-coefficient-pinned-in-fixture', tuple(range(8,17)))

# Detach is the existing external value-only serialization boundary; derivatives
# re-enter through the explicitly contracted RTTOV K fields below.
def external(label, values):
    prof = dict(fixed)
    prof['CFRAC']=np.concatenate((saved['extended_cfrac'][:bg],values[-1].detach().numpy()))[None,:]
    for k, sk, v in zip(keys, source_keys, values):
        prof[k] = np.concatenate((saved[sk][:bg], v.detach().numpy()))[None, :]
    tensor = lambda key: torch.tensor(prof[key],dtype=torch.float64)
    packet = pack_rttov_input(RttovProfileTensors(
        tensor('T'),tensor('Q'),tensor('P'),tensor('P_HALF'),
        tensor('HYDRO6'),tensor('HYDRO7'),tensor('HYDRO_DEFF6'),tensor('HYDRO_DEFF7'),tensor('CFRAC')),input_cfg)
    result = make_live_run_k(a.output / label, fixture_case_dir=a.fixture)(packet)
    np.savez_compressed(a.output / (label + '.npz'), **prof,
                        BT=np.asarray(result[0]), QUALITY=np.asarray(result[2]),
                        **{'K_' + k: np.asarray(result[1][k]) for k in keys})
    return result

v = .01 * s.qv
base, tangent = torch.func.jvp(cloud, (s.qv,), (v,))
bt, kval, quality = external('base', base)
# No numerical pass or accepted cost is inferred from an empty quality support.
if not np.any(np.asarray(quality) == 0):
    (a.output / 'result.json').write_text(json.dumps({
        'status': 'EMPTY_RADIANCE_SUPPORT', 'accepted_observation_cost': False,
        'return_quality': np.asarray(quality).tolist()}, indent=2) + '\n')
    raise SystemExit(1)
h = 1e-4
bp, _, qp = external('plus', cloud(s.qv+h*v))
bm, _, qm = external('minus', cloud(s.qv-h*v))
jv = sum(np.asarray(kval[k])[0, :, bg:] @ t.detach().numpy()
         for k, t in zip(keys, tangent))
fd = (np.asarray(bp)[0]-np.asarray(bm)[0])/(2*h)
rel = float(np.max(np.abs(jv-fd))/max(np.max(np.abs(jv)),np.max(np.abs(fd)),1e-30))
seed = torch.linspace(-.7,.8,9,dtype=torch.float64)
_, pullback = torch.func.vjp(cloud,s.qv)
weights = tuple(torch.tensor(np.asarray(kval[k])[0,:,bg:],dtype=torch.float64).T @ seed for k in keys)
adj, = pullback(weights+(torch.zeros_like(base[-1]),))
lhs = float(torch.tensor(jv) @ seed)
rhs = float((v * adj).sum())
same_quality = bool(np.array_equal(quality,qp) and np.array_equal(quality,qm))
dual_rel = abs(lhs-rhs)/max(abs(lhs),abs(rhs),1e-30)
nonzero = bool(np.any(jv != 0))
supported_nonzero = bool(np.any(jv[np.asarray(quality)[0]==0] != 0))
passed = rel<=1e-5 and same_quality and dual_rel<=1e-12 and nonzero and supported_nonzero
result = {'status': 'NUMERICAL_PASS' if passed else 'NUMERICAL_CHECK_FAILED',
          'h': h, 'qv_direction': '0.01*qv_entry; one 20 s Python KDM step, shared-entry density; forcing held fixed',
          'jvp_bt_K': jv.tolist(), 'fd_bt_K': fd.tolist(), 'max_norm_relative_error': rel,
          'duality_lhs': lhs, 'duality_rhs': rhs, 'duality_difference': lhs-rhs,
          'duality_relative_error': dual_rel, 'nonzero_qv_bt_sensitivity': nonzero,
          'nonzero_radiance_supported_qv_bt_sensitivity': supported_nonzero,
          'base_quality': np.asarray(quality).tolist(), 'plus_quality': np.asarray(qp).tolist(),
          'minus_quality': np.asarray(qm).tolist(), 'quality_unchanged': same_quality,
          'accepted_observation_cost': False, 'physical_number_basis_resolved': False,
          'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'profile_sha256': hashlib.sha256(a.profile.read_bytes()).hexdigest(),
          'fixture_source_hashes': fixture_hashes}
(a.output / 'result.json').write_text(json.dumps(result,indent=2)+'\n')
np.savez_compressed(a.output/'derivatives.npz',direction=v.numpy(),adjoint=adj.detach().numpy(),JVP=jv,FD=fd)
print(json.dumps(result,indent=2))
raise SystemExit(0 if result['status']=='NUMERICAL_PASS' else 1)
