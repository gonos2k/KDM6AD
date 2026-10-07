#!/usr/bin/env python3
"""One retained C5 comparison of initial NC controls; not estimated B/R."""
from __future__ import annotations
import argparse,hashlib,json,os,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'oracle'))
from kdm6.state import State,Forcing
from kdm6.obs.obs_ingest import ColumnObs
from kdm6.da_fulldomain import run_fulldomain_analysis
PROFILE=ROOT/'harness/evidence/C5_supported_profile_2026-10-03.npz'
FIELDS=ROOT/'harness/evidence/NATIVE_KMA_analysis_fields_2026-10-05.npz'
PREP=Path('/private/tmp/KDM6AD-c5-native39-sea-supported-retry1-20261003/evidence/selected_profile_preparation_receipt_20261003.json')
FIXTURE=Path('/private/tmp/KDM6AD-c5-dom32-fixture-20261003')
SIGMA=(1.,1.,1.5,2.,.75,1.25,2.5,1.75,3.);BIAS=(0.,0.,.05,-.1,.15,-.05,.2,-.15,.1)
F64=dict(dtype=torch.float64)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 if a.output.exists():raise FileExistsError(a.output)
 a.output.mkdir(parents=True)
 for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OMP_THREAD_LIMIT'):os.environ[key]='1'
 torch.set_num_threads(1)
 if sha(PROFILE)!='7915ef9bc9fab4983ab47776c1a3345384c21f09bddc2a6d540d36c4755194d4' or sha(FIELDS)!='fc414c8e394f60f094530ed4a493345dbaa13604517189d92a8f8de430e978da':raise ValueError('retained inputs changed')
 with np.load(PROFILE,allow_pickle=False) as z:profile={k:z[k].copy() for k in z.files}
 with np.load(FIELDS,allow_pickle=False) as z:y=torch.as_tensor(z['y_bt'],**F64);gate=torch.as_tensor(z['mask'],**F64)
 x=State(*(torch.as_tensor(v[None,:],**F64) for v in profile['native_state_bottom_up']))
 fc=Forcing(*(torch.as_tensor(v[None,:],**F64) for v in profile['native_forcing_bottom_up']))
 from types import SimpleNamespace
 frame=SimpleNamespace(state=x,forcing=fc,xland=torch.tensor([2.],**F64),meta=dict(nx=1,ny=1,valid_time_utc='2025-07-19_00:00:20'))
 co=ColumnObs(y,torch.zeros_like(y),1,0,0,torch.tensor([0]),'202507190000',torch.tensor([BIAS],**F64),gate)
 prep=json.loads(PREP.read_text());ob=prep['observation'];sf=prep['surface']
 geo=dict(zenangle=ob['view_zenith_deg'],azangle=ob['view_azimuth_deg_clockwise_from_north'],sunzenangle=ob['solar_zenith_deg'],sunazangle=ob['solar_azimuth_deg'],latitude=ob['pixel_latitude_deg'],longitude=ob['pixel_longitude_deg'],elevation=sf['same_c2_frame_surface']['HGT']/1000.)
 surface=dict(skin=dict(sf['RTTOV_skin']),near_surface=dict(sf['RTTOV_near_surface']))
 grids=dict(p_lay=profile['extended_p_center_hPa'],p_half=profile['extended_p_half_hPa'],t_ref=profile['extended_temperature_K'],q_ref=profile['extended_q_ppmv_moist'],cloud_fixture_case_dir=str(FIXTURE),clear_fixture_case_dir=str(FIXTURE))
 fixture_hashes={str(p.relative_to(FIXTURE)):sha(p) for p in sorted(FIXTURE.rglob('*')) if p.is_file()}
 expected=json.loads((ROOT/'harness/evidence/C5_nc_bt_dom32_result_2026-10-03.json').read_text())['fixture_source_hashes']
 if fixture_hashes!=expected:raise ValueError('RTTOV fixture changed')
 sources={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'oracle/kdm6').rglob('*.py'))}
 cases={}
 for label,nc_sigma in [('NC_initial_fixed',0.),('NC_initial_enabled',.15)]:
  folder=a.output/label
  report=run_fulldomain_analysis(frame,co,grids,str(folder),boundary=0,n_workers=1,max_iter=1,
    channels=tuple(range(8,17)),geometry=geo,surface=surface,obs_time=1,dt=20.,
    time_tolerance_s=40.,ncmin_land=10.,ncmin_sea=10.,qv_levels=39,huber_delta=1.,
    normalized_dry=True,observation_coordinate='kma_v3_0',fixed_obs_errors=True,
    obs_sigma=torch.tensor(SIGMA,**F64),obs_error_source='predeclared synthetic engineering assumptions',
    background_sigma_overrides={'nc':nc_sigma},background_error_source='predeclared initial NC control comparison',
    save_fields=str(a.output/(label+'.npz')))
  with np.load(a.output/(label+'.npz'),allow_pickle=False) as z:
   init_nc_change=float(np.linalg.norm(z['xa_nc']-z['xb_nc']))
   slot_nc_change=float(np.linalg.norm(z['xslot_a_nc']-z['xslot_b_nc']))
  if nc_sigma==0. and init_nc_change!=0.:raise RuntimeError('fixed initial NC moved')
  if (report['background_control_counts']['nc']>0)!=(nc_sigma>0.):raise RuntimeError('control metadata differs')
  cases[label]=dict(report=report,initial_nc_increment_norm=init_nc_change,slot_nc_increment_norm=slot_nc_change,fields_sha256=sha(a.output/(label+'.npz')))
 if sources!={str(p.relative_to(ROOT)):sha(p) for p in sorted((ROOT/'oracle/kdm6').rglob('*.py'))}:raise ValueError('source changed during experiment')
 result=dict(cases=cases,source_hashes=sources,source_sha256=sha(__file__),input_hashes={str(p):sha(p) for p in (PROFILE,FIELDS,PREP)},fixture_hashes=fixture_hashes,sigma_K=SIGMA,bias_K=BIAS,scope='one-column nominal C5 two one-iteration trials; state NC control only, warm theta priors unchanged; not convergence/NC truth/calibrated B/R/forecast evidence',independent_case=False,prior_is_calibrated=False,accepted_observation_cost=False)
 (a.output/'result.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
 for k,v in cases.items():print(k,v['report']['jb_final']+v['report']['jobs_final']+v['report']['jtheta_final'],v['initial_nc_increment_norm'],v['slot_nc_increment_norm'])
if __name__=='__main__':main()
