#!/usr/bin/env python3
"""Pinned serialized-cloud directional FD experiment; preflight makes no RTTOV calls."""
import argparse, hashlib, json, os, re, shutil, sys
from pathlib import Path
import numpy as np
import preflight as pf
R=Path(__file__).resolve().parent
BASE_RESULTS=R.parent/'east_optical_2x2_20261031/results_v3'
PREP=R/'prepared'
SOURCE=pf.SOURCE
HS=pf.HS
CHANNELS=list(range(10,17))
JS=pf.JS

def sha(p): return pf.sha(Path(p))
def write(p,x):
 with p.open('x') as f: json.dump(x,f,indent=2,sort_keys=True,allow_nan=False); f.write('\n')
def inputs(case):
 files=[p for p in (case/'in').rglob('*') if p.is_file()]+[case/'out'/n for n in ('run.sh','env.sh','rttov_test.txt')]
 return {str(p.relative_to(case)):sha(p) for p in sorted(files)}
def runtime():
 import torch,netCDF4
 return {'python_version':sys.version,'python_executable_sha256':sha(sys.executable),'numpy_version':np.__version__,'torch_version':str(torch.__version__),'torch_extension_sha256':sha(torch._C.__file__),'netcdf4_version':netCDF4.__version__,'netcdf4_extension_sha256':sha(netCDF4._netCDF4.__file__)}
def verify_sources(pins):
 if Path('/Users/yhlee/AD-RTTOV/external/rttov14/current').resolve() != Path('/Users/yhlee/AD-RTTOV/external/rttov14/src').resolve(): raise ValueError('RTTOV current symlink retargeted')
 if runtime()!=pins['runtime']: raise ValueError('runtime mismatch')
 for p,digest in pins['sources'].items():
  if sha(p)!=digest: raise ValueError('source or asset changed: '+p)
 for c,expected in pins['baseline_cases'].items():
  if pf.tree(pf.ORIG/c)!=expected: raise ValueError('preserved baseline changed: '+c)

def name(c,mode,h=None,sign=None):
 return c+'_K' if mode=='K' else f'{c}_{mode}_{HS.index(h)}_{sign}'
def check_case(case,k):
 if not all((case/'out'/n).is_dir() for n in ('direct','k')): raise ValueError('missing output directories')
 if pf.rows(case/'in/channels.txt') != [list(map(str,CHANNELS))]*10 or pf.rows(case/'in/lprofiles.txt') != [[str(i)]*7 for i in range(1,11)]: raise ValueError('channel/profile mapping')
 if len(list((case/'in/profiles').iterdir()))!=10 or len(list((case/'in').rglob('*.txt')))!=193: raise ValueError('case input inventory')
 s=(case/'out/rttov_test.txt').read_text()
 def one(key,value):
  matches=re.findall(r'(?mi)^\s*defn%'+re.escape(key)+r'\s*=\s*([^!\n]+)',s)
  if len(matches)!=1 or matches[0].strip().rstrip(',').upper()!=value: raise ValueError('namelist '+key)
 for a,b in [('nprofiles','10'),('nchannels','70'),('do_direct','.TRUE.'),('do_k','.TRUE.' if k else '.FALSE.'),('opts%config%adk_bt','.TRUE.')]:one(a,b)

def main():
 ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--preflight-only',action='store_true');g.add_argument('--execute',action='store_true');ap.add_argument('--expected-runner');ap.add_argument('--expected-manifest');a=ap.parse_args()
 prior=json.loads((pf.ORIG/'pins.json').read_text()); report=json.loads((R/'preflight.json').read_text())
 if a.preflight_only:
  if sha(R/'preflight.py')!=report['runner_sha256'] or sha(pf.ORIG/'pins.json')!=report['case_manifest_sha256']: raise ValueError('preflight pin mismatch')
  # Pin all observation/harness source files covered by historical source manifest,
  # executable, both RT tables, KMA calibration and the interpreter extensions.
  sources={}
  for p,d in prior['source_pins'].items():
   if p.startswith(str(SOURCE)+'/') or any(q in p for q in ('/rttov14/src/bin/rttov_test.exe','/rttov14/src/rtcoef_rttov14/')):
    if not Path(p).is_file() or sha(p)!=d: raise ValueError('historical source mismatch '+p)
    sources[p]=d
  for c in ('GG','PP'):
   receipt=json.loads((BASE_RESULTS/c/'result.json').read_text())
   if receipt['manifest_sha256']!=report['case_manifest_sha256'] or receipt['result_sha256']!=sha(BASE_RESULTS/c/'result.npz') or receipt['direct_calls']!=1 or receipt['K_calls']!=0 or receipt['coordinate']['bt_coordinate']!='kma_v3_0':raise ValueError('baseline result receipt mismatch '+c)
   for p in (BASE_RESULTS/c/'result.json',BASE_RESULTS/c/'result.npz'):sources[str(p)]=sha(p)
  for p in (R/'preflight.py',R/'preflight.json',pf.ORIG/'pins.json',Path(__file__).resolve()):sources[str(p)]=sha(p)
  rt=runtime()
  if rt!=prior['runtime']: raise ValueError('historical Python runtime mismatch')
  pins={'sources':sources,'runtime':rt,'baseline_cases':{c:prior['cases'][c] for c in ('GG','PP')},'cases':{},'threshold_margins':{},'calls':{'subprocesses':50,'direct_mode_paths':50,'K_mode_paths':2,'direct_only_fd_subprocesses':48,'combined_baseline_K_subprocesses':2},'scope':'serialized optical input derivative; cloud fraction held fixed; not QNICE or host boundary derivative'}
  verify_sources(pins)
  PREP.mkdir(exist_ok=False)
  for c in ('GG','PP'):
   check_case(pf.ORIG/c,False)
   variants=[('K',None,None)]+[(mode,h,sign) for mode in ('hydro','deff','mixed') for h in HS for sign in ('plus','minus')]
   for mode,h,sign in variants:
    key=name(c,mode,h,sign); dest=PREP/key; shutil.copytree(pf.ORIG/c,dest)
    if mode=='K':
     n=dest/'out/rttov_test.txt';s=n.read_text();s,count=re.subn(r'(?mi)^(\s*defn%do_k\s*=\s*)\.FALSE\.',r'\g<1>.TRUE.',s)
     if count!=1: raise ValueError('K namelist replacement')
     n.write_text(s)
    else:
     chosen=[r for r in report['cases'][c]['checks'] if r['field']==mode and r['h']==h]
     if len(chosen)!=42: raise ValueError('preflight perturbation count')
     for i in range(1,11):
      selected=[x for x in chosen if x['profile']==i]
      for kind,field in (('hydro','content'),('hydro_deff','deff')):
       p=dest/'in/profiles'/f'{i:03d}'/'atm'/f'{kind}.txt'; rows=pf.rows(p)
       if (kind=='hydro' and mode in ('hydro','mixed')) or (kind=='hydro_deff' and mode in ('deff','mixed')):
        for entry in selected:rows[entry['layer_zero_based']][6]=f"{entry[field+'_'+sign]:.16E}"
        p.write_text(''.join(' '.join(row)+'\n' for row in rows))
       vals=pf.parse(pf.rows(p))
       for entry in selected:
        target=entry[field+'_'+sign] if ((kind=='hydro' and mode in ('hydro','mixed')) or (kind=='hydro_deff' and mode in ('deff','mixed'))) else entry[field+'_base']
        if vals[entry['layer_zero_based']][6]!=target:raise ValueError('serialized value mismatch')
    check_case(dest,mode=='K'); pins['cases'][key]=inputs(dest)
    margins=[]
    for i in range(1,11):
     atm=dest/'in/profiles'/f'{i:03d}'/'atm'
     hrows=pf.parse(pf.rows(atm/'hydro.txt'))
     margins.extend(abs(row[5]+row[6]-1e-6) for row in hrows)
    pins['threshold_margins'][key]=min(margins)
  write(PREP/'pins.json',pins)
  print(json.dumps({'status':'PREFLIGHT_PASSED','manifest_sha256':sha(PREP/'pins.json'),'runner_sha256':sha(__file__),'prepared_cases':len(pins['cases']),'direct_calls':0,'K_calls':0,'planned_subprocesses':50,'planned_direct_mode_paths':50,'planned_K_mode_paths':2}))
  return
 if not a.expected_runner or not a.expected_manifest or sha(__file__)!=a.expected_runner or sha(PREP/'pins.json')!=a.expected_manifest: raise ValueError('locked hashes required')
 pins=json.loads((PREP/'pins.json').read_text());verify_sources(pins)
 for key,expected in pins['cases'].items():
  if inputs(PREP/key)!=expected: raise ValueError('prepared input mismatch '+key)
  check_case(PREP/key,key.endswith('_K'))
 sys.path.insert(0,str(SOURCE))
 from oracle.kdm6.obs.rttov_runner import run_rttov_k,parse_rttov_radiance
 from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path,add_cloud_k_slots
 from oracle.kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks
 from oracle.kdm6.obs.ami_bt_coordinate import read_ami_filters,read_kma_calibration,transform_rttov_to_kma
 from harness.native_observation_batch import _case_direct_radiance
 output=R/'results';output.mkdir(exist_ok=False)
 write(output/'attempt.json',{'manifest_sha256':a.expected_manifest,'runner_sha256':a.expected_runner,'planned_calls':pins['calls']})
 def call(key,k=False):
  verify_sources(pins)
  if inputs(PREP/key)!=pins['cases'][key]:raise ValueError('prepared changed '+key)
  case=output/key;shutil.copytree(PREP/key,case);before=inputs(case)
  if before!=pins['cases'][key]:raise ValueError('copy mismatch '+key)
  check_case(case,k)
  try:
   if k:
    raw=run_rttov_k(case/'out',nchannels=7,expected_nprofiles=10,timeout=600)
    if np.any(np.asarray(raw.rad_quality)!=0):raise ValueError('bad K quality')
    nlay=len(raw.k['T'][0][0]);add_cloud_k_slots(raw.k,nlay=nlay)
    total=np.asarray(parse_rttov_ascii_blocks(case/'out/k/radiance.txt')['RADIANCE%TOTAL'],dtype=float).reshape(10,7)
    filters=read_ami_filters(_resolve_coef_path(case)); calibration=read_kma_calibration()
    bt,kout,ratio=transform_rttov_to_kma(raw.bt,total,raw.k,CHANNELS,filters,calibration)
    direct=parse_rttov_radiance(case/'out/direct/radiance.txt',nchannels=7)
    if direct['nprofiles']!=10 or np.any(np.asarray(direct['rad_quality'])!=0):raise ValueError('bad K-case direct quality/count')
    direct_total=np.asarray(parse_rttov_ascii_blocks(case/'out/direct/radiance.txt')['RADIANCE%TOTAL'],dtype=float).reshape(10,7)
    direct_bt,_,_=transform_rttov_to_kma(direct['bt'],direct_total,{},CHANNELS,filters,calibration)
    ans=(bt,np.asarray(kout['HYDRO7']),np.asarray(kout['HYDRO_DEFF7']),ratio,total,direct_bt)
   else:
    bt,quality,_=_case_direct_radiance(case/'out',10,channels=CHANNELS,timeout=600,kma_bt=True)
    if np.any(np.asarray(quality)!=0):raise ValueError('bad direct quality')
    ans=np.asarray(bt)
  finally:
   if inputs(case)!=before:raise ValueError('consumed inputs changed '+key)
   verify_sources(pins)
  if not all(np.isfinite(x).all() for x in (ans if k else [ans])): raise ValueError('nonfinite result')
  with (case/'values.npz').open('xb') as f:
   if k:np.savez_compressed(f,bt=ans[0],hydro7=ans[1],deff7=ans[2],ratio=ans[3],total=ans[4],direct_bt=ans[5])
   else:np.savez_compressed(f,bt=ans)
  write(case/'receipt.json',{'input_hashes':before,'value_sha256':sha(case/'values.npz'),'mode':'K' if k else 'direct','do_k':k})
  return ans
 summary={}
 for c in ('GG','PP'):
  bt,kh,kd,ratio,total,direct_bt=call(name(c,'K'),True); nlay=kh.shape[-1]
  with np.load(BASE_RESULTS/c/'result.npz') as f:
   baseline=np.asarray(f['bt']);quality=np.asarray(f['quality'])
  if baseline.shape!=(10,7) or not np.isfinite(baseline).all() or np.any(quality!=0):raise ValueError('invalid preserved baseline '+c)
  compatible=bool(np.array_equal(direct_bt.view(np.uint64),baseline.view(np.uint64)) and np.array_equal(bt.view(np.uint64),direct_bt.view(np.uint64)))
  baseline_check={'preserved_vs_K_case_direct_bit_equal':bool(np.array_equal(direct_bt.view(np.uint64),baseline.view(np.uint64))), 'preserved_vs_K_case_direct_max_abs_K':float(np.max(np.abs(direct_bt-baseline))), 'K_case_direct_vs_K_radiance_bit_equal':bool(np.array_equal(bt.view(np.uint64),direct_bt.view(np.uint64))), 'K_case_direct_vs_K_radiance_max_abs_K':float(np.max(np.abs(bt-direct_bt))), 'compatible':compatible,'criterion':'bitwise KMA BT equality','preserved_result_sha256':sha(BASE_RESULTS/c/'result.npz')}
  write(output/f'{c}_baseline_compatibility.json',baseline_check)
  if not compatible:
   write(output/'inconclusive.json',{'status':'INCONCLUSIVE','reason':'combined K-case direct or K BT differs from preserved direct KMA BT','corner':c,'baseline_check':baseline_check,'no_fd_interpretation':True})
   print(json.dumps({'status':'INCONCLUSIVE','corner':c,'baseline_check':baseline_check}));return
  comparisons={}
  for mode in ('hydro','deff','mixed'):
   for h in HS:
    plus=call(name(c,mode,h,'plus'));minus=call(name(c,mode,h,'minus'))
    vh=np.zeros((10,nlay));vd=np.zeros((10,nlay))
    for row in report['cases'][c]['checks']:
     if row['field']==mode and row['h']==h:
      i=row['profile']-1;k=row['layer_zero_based']
      vh[i,k]=(row['content_plus']-row['content_minus'])/(2*h)
      vd[i,k]=(row['deff_plus']-row['deff_minus'])/(2*h)
    jvp=np.einsum('pcl,pl->pc',kh,vh)+np.einsum('pcl,pl->pc',kd,vd)
    fd=(plus-minus)/(2*h); residual=fd-jvp
    cot=np.where(np.arange(70).reshape(10,7)%2==0,1.,-1.)/70
    lhs=float(np.sum(cot*jvp));rhs=float(np.sum(vh*np.einsum('pc,pcl->pl',cot,kh))+np.sum(vd*np.einsum('pc,pcl->pl',cot,kd)))
    comparisons[f'{mode}_{h:g}']={'fd':fd.tolist(),'jvp':jvp.tolist(),'max_abs_error':float(np.max(np.abs(residual))),'max_abs_fd':float(np.max(np.abs(fd))),'max_abs_bt_difference':float(np.max(np.abs(plus-minus))),'nonzero_bt_elements':int(np.count_nonzero(plus-minus)),'signal_resolved':bool(np.any(plus!=minus)),'dot_lhs':lhs,'dot_rhs':rhs,'dot_abs_error':abs(lhs-rhs)}
  # Keep adjacent-h differences and error scales for plateau inspection. A
  # nonzero output difference is necessary but does not prove precision or
  # convergence; no zero/zero result is marked as a derivative pass.
  plateau={}
  for mode in ('hydro','deff','mixed'):
   entries=[comparisons[f'{mode}_{h:g}'] for h in HS]
   plateau[mode]=[{'h_large':HS[i],'h_small':HS[i+1],
    'both_signals_resolved':entries[i]['signal_resolved'] and entries[i+1]['signal_resolved'],
    'max_abs_fd_difference':float(np.max(np.abs(np.asarray(entries[i]['fd'])-np.asarray(entries[i+1]['fd'])))),
    'max_abs_fd_scale':max(entries[i]['max_abs_fd'],entries[i+1]['max_abs_fd']),
    'max_abs_k_error_large':entries[i]['max_abs_error'],'max_abs_k_error_small':entries[i+1]['max_abs_error']}
    for i in range(len(HS)-1)]
  summary[c]={'baseline_compatibility':baseline_check,'steps':comparisons,'adjacent_step_diagnostics':plateau}
 write(output/'summary.json',{'comparisons':summary,'note':'fixed-branch serialized optical input directional test; algebraic transpose dot checks K contraction only, not independent VJP; adjacent-step diagnostics are not a plateau verdict','subprocesses':50,'direct_mode_paths':50,'K_mode_paths':2,'direct_only_fd_subprocesses':48,'combined_baseline_K_subprocesses':2})
 print(json.dumps({'status':'COMPLETE','subprocesses':50,'direct_mode_paths':50,'K_mode_paths':2,'summary_sha256':sha(output/'summary.json')}))
if __name__=='__main__':main()
