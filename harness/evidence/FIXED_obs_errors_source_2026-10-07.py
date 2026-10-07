#!/usr/bin/env python3
"""Actual retained C5 fixed-weight plumbing check; not a calibrated R/bias study."""
from __future__ import annotations
import argparse, hashlib, json, math, os, sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'oracle'))
from kdm6.da_fulldomain import make_fulldomain_obs_eval
from kdm6.da_driver import OsseObsConfig
from kdm6.da_window import WindowConfig,collect_window_trajectory,run_da_window
from kdm6.state import State,Forcing
from kdm6.obs.model_profile_builder import RttovProfileConfig
from kdm6.obs.rttov_input_builder import RttovInputConfig
from kdm6.obs.rttov_case_writer import make_live_run_k
from kdm6.rttov_bridge import freeze_dry_air_density
F64=dict(dtype=torch.float64)
PROFILE=ROOT/'harness/evidence/C5_supported_profile_2026-10-03.npz'
FIELDS=ROOT/'harness/evidence/NATIVE_KMA_analysis_fields_2026-10-05.npz'
PREP=Path('/private/tmp/KDM6AD-c5-native39-sea-supported-retry1-20261003/evidence/selected_profile_preparation_receipt_20261003.json')
FIXTURE=Path('/private/tmp/KDM6AD-c5-dom32-fixture-20261003')
# Predeclared nonuniform engineering assumptions, unrelated to fitting residuals.
SIGMA=(1.,1.,1.5,2.,.75,1.25,2.5,1.75,3.)
BIAS=(0.,0.,.05,-.1,.15,-.05,.2,-.15,.1)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 a.output.mkdir(parents=True)
 for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OMP_THREAD_LIMIT'):os.environ[key]='1'
 torch.set_num_threads(1)
 if sha(PROFILE)!='7915ef9bc9fab4983ab47776c1a3345384c21f09bddc2a6d540d36c4755194d4' or sha(FIELDS)!='fc414c8e394f60f094530ed4a493345dbaa13604517189d92a8f8de430e978da':raise ValueError('retained C5 inputs changed')
 with np.load(PROFILE,allow_pickle=False) as z:p={k:z[k].copy() for k in z.files}
 with np.load(FIELDS,allow_pickle=False) as z:
  y=torch.as_tensor(z['y_bt'],**F64);gate=torch.as_tensor(z['mask'],**F64)
  background=np.stack([z['xb_'+f][0] for f in State._fields])
 if not np.array_equal(background,p['native_state_bottom_up']):raise ValueError('background/input linkage differs')
 fixture_hashes={str(k.relative_to(FIXTURE)):sha(k) for k in sorted(FIXTURE.rglob('*')) if k.is_file()}
 expected=json.loads((ROOT/'harness/evidence/C5_nc_bt_dom32_result_2026-10-03.json').read_text())['fixture_source_hashes']
 if fixture_hashes!=expected:raise ValueError('RTTOV fixture changed')
 prep=json.loads(PREP.read_text());ob=prep['observation'];sf=prep['surface']
 geometry=dict(zenangle=ob['view_zenith_deg'],azangle=ob['view_azimuth_deg_clockwise_from_north'],sunzenangle=ob['solar_zenith_deg'],sunazangle=ob['solar_azimuth_deg'],latitude=ob['pixel_latitude_deg'],longitude=ob['pixel_longitude_deg'],elevation=sf['same_c2_frame_surface']['HGT']/1000.)
 surface=dict(skin=dict(sf['RTTOV_skin']),near_surface=dict(sf['RTTOV_near_surface']))
 x=State(*(torch.as_tensor(v[None,:],**F64) for v in p['native_state_bottom_up']))
 fc=Forcing(*(torch.as_tensor(v[None,:],**F64) for v in p['native_forcing_bottom_up']))
 land=torch.tensor([2.],**F64);cfg=WindowConfig(dt=20.,xland=land,ncmin_land=10.,ncmin_sea=10.,normalized_dry=True)
 slot=collect_window_trajectory(x,[fc],cfg,{1})[1]
 pl=torch.as_tensor(p['extended_p_center_hPa'],**F64);ph=torch.as_tensor(p['extended_p_half_hPa'],**F64)
 tr=torch.as_tensor(p['extended_temperature_K'],**F64);qr=torch.as_tensor(p['extended_q_ppmv_moist'],**F64)
 clear=OsseObsConfig(run_k=make_live_run_k(a.output/'clear',fixture_case_dir=FIXTURE,ami_kma_bt=True),profile_cfg=RttovProfileConfig(2,'mixing_ratio_kgkg_dry',rttov_layer_pressure=pl,rttov_level_pressure=ph),input_cfg=RttovInputConfig('C5-fixed-errors',tuple(range(8,17)),geometry=geometry,surface=surface),obs_sigma=1.,t_ref=tr,q_ref=qr,t_blend_octaves=0.,q_blend_octaves=0.)
 rc=dict(t_ref=tr.numpy(),q_ref=qr.numpy(),p_lay=pl.numpy(),p_half=ph.numpy(),channels=tuple(range(8,17)),coef_id='C5-fixed-errors',geometry=geometry,surface=surface,ncmin_land=10.,ncmin_sea=10.,oracle_root=str(ROOT/'oracle'),rho_d=freeze_dry_air_density(x,fc).numpy(),dry_number=True,ami_kma_bt=True,fixture_case_dir=str(FIXTURE),t_blend_octaves=0.,q_blend_octaves=0.)
 source_hashes={str(k.relative_to(ROOT)):sha(k) for k in sorted((ROOT/'oracle/kdm6').rglob('*.py'))}
 results={};arrays={};direction=.01*x.qv;h=1e-4
 for policy,extra in [('legacy',{}),('fixed',dict(obs_sigma=torch.tensor(SIGMA,**F64),obs_bias=torch.tensor([BIAS],**F64)))]:
  evaluate=make_fulldomain_obs_eval(x,fc,y,torch.zeros_like(y),land,torch.tensor([0]),torch.empty(0,dtype=torch.int64),clear,rc,str(a.output/policy),n_workers=1,pool=None,obs_time=1,huber_delta=1.,x_slot_bg=slot,channel_gate=gate,**extra)
  cases={}
  for label,offset in [('base',0.),('plus',h),('minus',-h)]:
   initial=x._replace(qv=x.qv+offset*direction);seen=[]
   def callback(t,s):
    value=evaluate(t,s)
    if value is None:return None
    seen.append(value);return value.adj if label=='base' else None
   win=run_da_window(initial,[fc],callback,cfg);v=seen[0]
   cases[label]=dict(cost=v.j,signature=v.signature,n_valid=v.n_valid)
   arrays[policy+'_'+label+'_state']=np.stack([f.numpy() for f in win.state_final])
   if label=='base':cases[label]['vjp']=float((win.adj_x0.qv*direction).sum());arrays[policy+'_qv_adjoint']=win.adj_x0.qv.numpy()
  ad=cases['base']['vjp'];fd=(cases['plus']['cost']-cases['minus']['cost'])/(2*h);relative=abs(ad-fd)/max(abs(ad),abs(fd),1e-30)
  if relative>1e-5 or len({v['signature'] for v in cases.values()})!=1 or any(v['n_valid']!=7 for v in cases.values()):raise RuntimeError('cost FD or frozen support failed')
  results[policy]=dict(cases=cases,vjp=ad,fd=fd,relative=relative)
 if source_hashes!={str(k.relative_to(ROOT)):sha(k) for k in sorted((ROOT/'oracle/kdm6').rglob('*.py'))}:raise ValueError('source changed during execution')
 np.savez(a.output/'arrays.npz',**arrays,sigma_K=np.array(SIGMA),bias_K=np.array(BIAS),mask=gate.numpy(),target_K=y.numpy(),direction=direction.numpy())
 result=dict(experiment='actual retained C5 fixed-error forward/cost/VJP check',results=results,sigma_K=SIGMA,bias_K=BIAS,bias_definition='added_to_observation',error_source='predeclared synthetic engineering assumptions',source_hashes=source_hashes,input_hashes={str(k):sha(k) for k in (PROFILE,FIELDS,PREP)},fixture_source_hashes=fixture_hashes,source_sha256=sha(__file__),array_sha256=sha(a.output/'arrays.npz'),science_scope='nominal C5 timing/geometry/product compatibility unresolved; no calibrated R/bias, analysis or forecast approval',independent_case=False,accepted_observation_cost=False)
 (a.output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print(json.dumps(results,indent=2))
if __name__=='__main__':main()
