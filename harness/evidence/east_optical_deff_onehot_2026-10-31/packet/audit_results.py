#!/usr/bin/env python3
"""Independently reparse archived direct output, serialized inputs and reused K."""
import json, sys
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent
sys.path.insert(0,str(R.parent/'east_optical_derivative_20261031'))
import runner as old_runner
import importlib.util
spec=importlib.util.spec_from_file_location('deff_experiment_runner',R/'runner.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
sys.path.insert(0,str(runner.old.SOURCE))
from oracle.kdm6.obs.rttov_runner import parse_rttov_radiance
from oracle.kdm6.obs._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks
from oracle.kdm6.obs.ami_bt_coordinate import read_ami_filters,read_kma_calibration,transform_rttov_to_kma
from oracle.kdm6.obs.rttov_case_writer import _resolve_coef_path
pins=json.loads((R/'prepared/pins.json').read_text());runner.verify(pins)
summary=json.loads((R/'results/summary.json').read_text());values={};checks={}
for key,expected in pins['cases'].items():
 case=R/'results'/key; receipt=json.loads((case/'receipt.json').read_text())
 if runner.old.inputs(case)!=expected or receipt['input_hashes']!=expected or receipt['post_input_hashes']!=expected:raise ValueError('input hashes '+key)
 direct=case/'out/direct'; files={str(p.relative_to(direct)):runner.sha(p) for p in direct.rglob('*') if p.is_file()}
 if files!=receipt['raw_direct_hashes'] or set(files)!={'radiance.txt','transmission.txt','emissivity_out.txt','diffuse_reflectance_out.txt'} or list((case/'out/k').rglob('*')) or receipt['raw_k_inventory']!=[]:raise ValueError('output inventory '+key)
 if runner.sha(case/'values.npz')!=receipt['value_sha256']:raise ValueError('value hash '+key)
 rad=direct/'radiance.txt'; parsed=parse_rttov_radiance(rad,nchannels=7)
 if parsed['nprofiles']!=10 or np.any(np.asarray(parsed['rad_quality'])!=0):raise ValueError('quality '+key)
 total=np.asarray(parse_rttov_ascii_blocks(rad)['RADIANCE%TOTAL']).reshape(10,7)
 bt,_,_=transform_rttov_to_kma(parsed['bt'],total,{},runner.old.CHANNELS,read_ami_filters(_resolve_coef_path(case)),read_kma_calibration())
 with np.load(case/'values.npz') as v:
  if not np.array_equal(bt,v['bt']):raise ValueError('BT mismatch '+key)
 values[key]=bt; checks[key]={'inputs_pre_post_match':True,'raw_hashes_match':True,'k_empty':True,'quality_zero':True,'bt_match':True}
results={}
for c in ('GG','PP'):
 with np.load(runner.OLD/'results'/f'{c}_K/values.npz') as d: kd=d['deff7'].copy()
 results[c]={}
 for h in runner.HS:
  a=runner.key(c,h,'plus'); b=runner.key(c,h,'minus'); va=[]
  for i in range(1,11):
   p=Path('in/profiles')/f'{i:03d}'/'atm/hydro_deff.txt'
   x=np.loadtxt(R/'results'/a/p); y=np.loadtxt(R/'results'/b/p);base=np.loadtxt(runner.pf.ORIG/c/p)
   delta=(x-y)/(2*h); mask=np.ones(x.shape,dtype=bool);mask[runner.LAYER,6]=False
   if np.any(x[mask]!=base[mask]) or np.any(y[mask]!=base[mask]) or not (20<x[runner.LAYER,6]<120 and 20<y[runner.LAYER,6]<120):raise ValueError('onehot or bound')
   va.append(delta[runner.LAYER,6])
  pred=kd[:,:,runner.LAYER]*np.asarray(va)[:,None];fd=(values[a]-values[b])/(2*h);err=fd-pred
  recorded=summary['results'][c][f'{h:g}']
  if not np.array_equal(fd,np.asarray(recorded['fd'])) or not np.array_equal(pred,np.asarray(recorded['k_v'])):raise ValueError('summary mismatch')
  results[c][f'{h:g}']={'nonzero_bt_differences':int(np.count_nonzero(values[a]-values[b])),'nonzero_kv':int(np.count_nonzero(pred)),'max_abs_error_K':float(np.max(np.abs(err))),'relative_l2_error':float(np.linalg.norm(err)/np.linalg.norm(pred))}
 if any(e['rank']!=4 for e in pins['checks'][c]):raise ValueError('rank')
runner.verify(pins)
out={'status':'AUDIT_COMPLETE','cases':checks,'results':results,'scope':'serialized RTTOV optical diameter sensitivity only; no host attribution or convergence verdict','source_and_prepared_pins_match':True,'rank4_all_profiles':True,'fixed_content_fraction_and_no_20um_or_clamp_crossing':True}
with (R/'results/independent_audit.json').open('x') as f:json.dump(out,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
print(json.dumps({'status':'AUDIT_COMPLETE','sha256':runner.sha(R/'results/independent_audit.json'),'results':results}))
