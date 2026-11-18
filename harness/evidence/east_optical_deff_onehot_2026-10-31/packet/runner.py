#!/usr/bin/env python3
"""One-hot serialized optical experiment: prepare/verify without RTTOV; execute only after review."""
import argparse, json, shutil, sys
from pathlib import Path
import numpy as np
R=Path(__file__).resolve().parent
OLD=R.parent/'east_optical_derivative_20261031'
sys.path.insert(0,str(OLD))
import runner as old
import preflight as pf
HS=(1e-4,2e-4,4e-4,8e-4); LAYER=39
PREP=R/'prepared'
ONE=R.parent/'east_optical_onehot_20261031'
def sha(p): return pf.sha(Path(p))
def write(p,x):
 with p.open('x') as f: json.dump(x,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
def verify(pins):
 old.verify_sources(pins['old_pins'])
 for p,h in pins['extra'].items():
  if sha(p)!=h: raise ValueError('changed pinned file '+p)
 for key,expected in pins['cases'].items():
  case=PREP/key
  if old.inputs(case)!=expected: raise ValueError('changed prepared case '+key)
  old.check_case(case,False)
  if any(any((case/'out'/x).iterdir()) for x in ('direct','k')): raise ValueError('prepared output not empty '+key)
def key(c,h,s): return f'{c}_{HS.index(h)}_{s}'
def prepare():
 oldpins=json.loads((OLD/'prepared/pins.json').read_text());old.verify_sources(oldpins)
 report=json.loads((OLD/'preflight.json').read_text()); audit=json.loads((OLD/'results/independent_audit.json').read_text())
 if audit['status']!='AUDIT_COMPLETE' or not audit['baseline_both_bit_equal'] or not audit['quality_all_zero']:raise ValueError('old audit')
 extra={}
 paths=[ONE/'prepared/pins.json', ONE/'runner.py', ONE/'results/summary.json', OLD/'prepared/pins.json',OLD/'preflight.json',OLD/'results/independent_audit.json',OLD/'runner.py',OLD/'preflight.py',Path(__file__)]
 for c in ('GG','PP'):
  kr=OLD/'results'/f'{c}_K';receipt=json.loads((kr/'receipt.json').read_text())
  if old.inputs(kr)!=oldpins['cases'][f'{c}_K'] or receipt['input_hashes']!=oldpins['cases'][f'{c}_K'] or receipt['value_sha256']!=sha(kr/'values.npz'):raise ValueError('K receipt')
  bc=json.loads((OLD/'results'/f'{c}_baseline_compatibility.json').read_text())
  if not bc['compatible']:raise ValueError('baseline compatibility')
  paths.extend([kr/'receipt.json',kr/'values.npz',OLD/'results'/f'{c}_baseline_compatibility.json'])
 for p in paths: extra[str(p)]=sha(p)
 PREP.mkdir(exist_ok=False); cases={};checks={}
 for c in ('GG','PP'):
  base=pf.ORIG/c; old.check_case(base,False)
  with np.load(OLD/'results'/f'{c}_K/values.npz') as data:
   kh=data['deff7'].copy(); baseline=data['direct_bt'].copy();kbt=data['bt'].copy()
  with np.load(old.BASE_RESULTS/c/'result.npz') as data: direct=data['bt'].copy();quality=data['quality'].copy()
  if kh.ndim!=3 or kh.shape[:2]!=(10,7) or not np.isfinite(kh).all() or np.any(quality!=0) or not np.array_equal(baseline.view('uint64'),direct.view('uint64')) or not np.array_equal(kbt.view('uint64'),direct.view('uint64')):raise ValueError('baseline or K')
  checks[c]=[]
  for i in range(1,11):
   atm=base/'in/profiles'/f'{i:03d}'/'atm'; H=pf.parse(pf.rows(atm/'hydro.txt'));D=pf.parse(pf.rows(atm/'hydro_deff.txt'));F=pf.parse(pf.rows(atm/'hydro_frac.txt'))[1:];n=len(H)
   if len(D)!=n or len(F)!=n or kh.shape[2]!=n: raise ValueError('shape')
   v=H[LAYER][6];diam=D[LAYER][6];frac=F[LAYER][0]
   if not (v>0 and frac>0 and 10<diam<120 and diam!=20): raise ValueError('layer constraint')
   # Two-component (hydro, diameter) directions, normalized columnwise for rank.
   one=np.zeros(2*n);one[n+LAYER]=diam
   content_one=np.zeros(2*n);content_one[LAYER]=v
   vectors=[one,content_one]
   for mode in ('hydro','deff','mixed'):
    vec=np.zeros(2*n)
    for e in report['cases'][c]['checks']:
     if e['profile']==i and e['field']==mode and e['h']==old.HS[1]:
      l=e['layer_zero_based'];vec[l]=(e['content_plus']-e['content_minus'])/(2*old.HS[1]);vec[n+l]=(e['deff_plus']-e['deff_minus'])/(2*old.HS[1])
    vectors.append(vec)
   norms=np.linalg.norm(vectors,axis=1)
   if np.any(norms==0): raise ValueError('zero old direction')
   rank=int(np.linalg.matrix_rank(np.stack(vectors,axis=1)/norms))
   pred=kh[i-1,:,LAYER]*diam
   if rank!=4 or np.any(pred==0) or not np.isfinite(pred).all():raise ValueError('rank or K prediction')
   checks[c].append({'profile':i,'layer_zero_based':LAYER,'content':v,'diameter_um':diam,'fraction':frac,'rank':rank,'predicted_k_v':pred.tolist(),'serialized':{}})
  for h in HS:
   for s,sgn in (('plus',1),('minus',-1)):
    k=key(c,h,s);dest=PREP/k;shutil.copytree(base,dest)
    for i,entry in enumerate(checks[c],1):
     p=dest/'in/profiles'/f'{i:03d}'/'atm/hydro_deff.txt';rows=pf.rows(p); before=[x[:] for x in rows]; val=entry['diameter_um']*(1+sgn*h); rows[LAYER][6]=f'{val:.16E}';p.write_text(''.join(' '.join(r)+'\n' for r in rows));actual=pf.parse(pf.rows(p));basevals=pf.parse(before)
     if not 10<actual[LAYER][6]<120 or actual[LAYER][6]==entry['diameter_um'] or (actual[LAYER][6]-20)*(entry['diameter_um']-20)<=0:raise ValueError('serialization')
     for l in range(len(rows)):
      for j in range(len(rows[l])):
       if (l,j)!=(LAYER,6) and rows[l][j]!=before[l][j]:raise ValueError('unexpected input change')
     entry['serialized'][f'{h:g}_{s}']=rows[LAYER][6]
    old.check_case(dest,False);cases[k]=old.inputs(dest)
 pins={'old_pins':oldpins,'extra':extra,'cases':cases,'checks':checks,'calls':{'direct':16,'K':0},'scope':'serialized fixed-branch HYDRO_DEFF slot 7 at zero-based layer 39; content and fraction fixed'}
 write(PREP/'pins.json',pins)
 print(json.dumps({'status':'PREFLIGHT_PASSED','manifest_sha256':sha(PREP/'pins.json'),'runner_sha256':sha(__file__),'cases':len(cases),'direct_calls':0,'K_calls':0,'predictions_nonzero':140}))
def execute(pins):
 sys.path.insert(0,str(old.SOURCE))
 from harness.native_observation_batch import _case_direct_radiance
 output=R/'results';output.mkdir(exist_ok=False);write(output/'attempt.json',{'manifest_sha256':sha(PREP/'pins.json'),'runner_sha256':sha(__file__),'planned_calls':pins['calls']})
 vals={}
 for k,expected in pins['cases'].items():
  verify(pins);case=output/k;shutil.copytree(PREP/k,case);before=old.inputs(case)
  if before!=expected:raise ValueError('copied input mismatch')
  old.check_case(case,False)
  if any(any((case/'out'/x).iterdir()) for x in ('direct','k')): raise ValueError('copied output not empty '+k)
  try:
   bt,q,_=_case_direct_radiance(case/'out',10,channels=old.CHANNELS,timeout=600,kma_bt=True)
   bt=np.asarray(bt)
   if bt.shape!=(10,7) or not np.isfinite(bt).all() or np.any(np.asarray(q)!=0):raise ValueError('quality')
  finally:
   if old.inputs(case)!=before:raise ValueError('consumed inputs changed')
   verify(pins)
  direct=case/'out/direct'; kdir=case/'out/k'
  direct_files={str(p.relative_to(direct)):sha(p) for p in direct.rglob('*') if p.is_file()}
  expected_files={'radiance.txt','transmission.txt','emissivity_out.txt','diffuse_reflectance_out.txt'}
  if set(direct_files)!=expected_files or any(kdir.rglob('*')): raise ValueError('unexpected raw output inventory '+k)
  with (case/'values.npz').open('xb') as f:np.savez_compressed(f,bt=bt)
  write(case/'receipt.json',{'input_hashes':before,'post_input_hashes':old.inputs(case),'raw_direct_hashes':direct_files,'raw_k_inventory':[],'value_sha256':sha(case/'values.npz'),'mode':'direct','do_k':False});vals[k]=bt
 summary={}
 for c in ('GG','PP'):
  with np.load(OLD/'results'/f'{c}_K/values.npz') as d: kh=d['deff7'].copy()
  summary[c]={}
  for h in HS:
   plus=vals[key(c,h,'plus')];minus=vals[key(c,h,'minus')];v=np.array([(float(e['serialized'][f'{h:g}_plus'])-float(e['serialized'][f'{h:g}_minus']))/(2*h) for e in pins['checks'][c]])
   pred=kh[:,:,LAYER]*v[:,None];fd=(plus-minus)/(2*h);err=fd-pred
   summary[c][f'{h:g}']={'fd':fd.tolist(),'k_v':pred.tolist(),'max_abs_error':float(np.max(abs(err))),'relative_l2_error':float(np.linalg.norm(err)/np.linalg.norm(pred)),'nonzero_bt_differences':int(np.count_nonzero(plus-minus))}
 write(output/'summary.json',{'results':summary,'calls':pins['calls'],'scope':pins['scope'],'note':'no convergence or pass verdict'})
 print(json.dumps({'status':'COMPLETE','summary_sha256':sha(output/'summary.json')}))
def main():
 p=argparse.ArgumentParser();g=p.add_mutually_exclusive_group(required=True);g.add_argument('--preflight',action='store_true');g.add_argument('--verify-only',action='store_true');g.add_argument('--execute',action='store_true');p.add_argument('--expected-runner');p.add_argument('--expected-manifest');a=p.parse_args()
 if a.preflight:prepare();return
 if not a.expected_runner or not a.expected_manifest or sha(__file__)!=a.expected_runner or sha(PREP/'pins.json')!=a.expected_manifest:raise ValueError('locked hashes required')
 pins=json.loads((PREP/'pins.json').read_text());verify(pins)
 if a.verify_only:print(json.dumps({'status':'LOCKED_VERIFIED','direct_calls':0,'K_calls':0}));return
 execute(pins)
if __name__=='__main__':main()
