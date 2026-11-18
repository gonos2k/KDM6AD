import csv,hashlib,json,os,subprocess,sys,shutil
from pathlib import Path
p=Path(__file__).resolve().parent; root=p.parent; s=json.loads((root/'selected_full.json').read_text()); names=('th','qv'); base={a:int(s['input_words_hex'][a][15],16) for a in names}; runner=Path('/Users/yhlee/KDM6AD-k/host/research_evidence/native_f32_activation_boundary_20261111/runner_build/native_f32_cabi_probe'); research=Path('/Users/yhlee/KDM6AD-k/host/research_evidence/native_f32_activation_boundary_20261111/source/build_f32_capture/libkdm6_c.2.0.0.dylib'); installed=Path('/Users/yhlee/KDM6AD-k/libtorch/install/lib/libkdm6_c.2.0.0.dylib'); limit=1<<20
# At most 1,048,576 adjacent positive float32 words from baseline; no physics overrides.
env={k:v for k,v in os.environ.items() if not k.startswith('KDM6') and not k.startswith('DYLD_')}; env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_THREAD_LIMIT='1',DYLD_LIBRARY_PATH='/opt/homebrew/Caskroom/miniforge/base/lib/python3.9/site-packages/torch/lib',DYLD_PRINT_LIBRARIES='1')
rows=[]; cache={}; result={'schema':'kdm6.host_selected_f32_activation_coupled_boundary.v1','scope':'B=1 value-only perturbation of host-captured column; not a perturbed host tile or f32 AD','max_word_distance':limit,'base_words':{k:f'{v:08x}' for k,v in base.items()},'events':rows,'boundaries':[],'parity':[],'status':'running'}
def f32(w):
 import struct
 return struct.unpack('>f',bytes.fromhex(w))[0]
def call(axis,w,mode='on'):
 tag=f'{axis}_{w:08x}_{mode}'; d=p/tag; d.mkdir(exist_ok=False); e=env.copy(); lib=installed if mode=='installed' else research
 if mode=='on': e.update(KDM6_NATIVE_CAPTURE_DIR=str(d),KDM6_NATIVE_CAPTURE_ALL_K='1',KDM6_NATIVE_CAPTURE_CALL='1',KDM6_NATIVE_CAPTURE_B='0',KDM6_NATIVE_CAPTURE_MAX_ROWS='200000',KDM6_NATIVE_CAPTURE_MAX_BYTES='134217728')
 cmd=[str(runner),'--library',str(lib),'--input',str(p/'input.bin'),'--output',str(d/'out.json'),'--axis',axis+'16','--word',f'{w:08x}']; q=subprocess.run(cmd,env=e,capture_output=True,text=True); (d/'loader.stderr').write_text(q.stderr); assert q.returncode==0,(tag,q.stderr[-1000:]); assert str(lib) in q.stderr,(tag,'wrong loaded DSO'); output=json.loads((d/'out.json').read_text()); trace={}
 if mode=='on':
  f=next(d.glob('native_qnice*.csv')); lines=f.read_text().splitlines(); assert lines[-1].endswith('status=complete')
  for row in csv.DictReader(x for x in lines if not x.startswith('#')):
   if row['stage']=='fd_satadj_inner' and row['k_zero']=='23':
    assert (row['runtime_call'],row['one_step_call'],row['substep'],row['b_zero'])==('1','1','0','0'); assert row['field'] not in trace; trace[row['field']]={'dtype':row['dtype'],'raw_hex':row['raw_hex']}
  assert len(trace)==33
 return {'axis':axis,'word':f'{w:08x}','trace':trace,'state_output_f32_words':output['state_output_f32_words'],'precip_increment_f32_words':output['precip_increment_f32_words'],'rhog_output_f32_words':output['rhog_output_f32_words']}
def probe(a,w):
 if (a,w) not in cache:
  r=call(a,w); cache[a,w]=r; rows.append(r); (p/'progress.json').write_text(json.dumps(result,indent=2)+'\n'); print(a,f'{w:08x}',f32(r['trace']['sw_percent']['raw_hex']),flush=True)
 return cache[a,w]
def pred(r,k):return f32(r['trace']['sw_percent']['raw_hex'])>=.48 if k=='sw' else f32(r['trace']['activation_fraction_min_output']['raw_hex'])>=1
try:
 baseline=probe('th',base['th']); keys=('state_output_f32_words','precip_increment_f32_words','rhog_output_f32_words');
 for mode in ('off','installed'):
  r=call('th',base['th'],mode); assert all(r[k]==baseline[k] for k in keys); result['parity'].append({'axis':'th','word':f"{base['th']:08x}",'mode':mode,'match':True})
 allowed={'activation_fraction_pow_lt_one','activation_fraction_pow_eq_one','activation_fraction_pow_gt_one','ncact_raw_lt_nccn_rate_cap','ncact_raw_eq_nccn_rate_cap','ncact_raw_gt_nccn_rate_cap'}; masks={k:v['raw_hex'] for k,v in baseline['trace'].items() if v['dtype']=='bool' and k not in allowed}
 def check(r):
  changed={k:[v,r['trace'][k]['raw_hex']] for k,v in masks.items() if r['trace'][k]['raw_hex']!=v}
  if changed: raise RuntimeError('unrelated masks changed: '+json.dumps(changed,sort_keys=True))
 for a,sign in [('th',1)]:
  initial=probe(a,base[a]); check(initial)
  for k in ('sw','fraction'):
   initial_pred=pred(initial,k); assert initial_pred, (a,k,'unexpected baseline'); step=1; other=None
   while step<=limit:
    r=probe(a,base[a]+sign*step); check(r)
    if pred(r,k)!=initial_pred: other=base[a]+sign*step; break
    step*=2
   if other is None: raise RuntimeError(f'{a} {k} not bracketed within {limit} f32 words')
   lo,hi=sorted((base[a],other)); left=pred(probe(a,lo),k)
   while hi-lo>1:
    mid=(lo+hi)//2; r=probe(a,mid); check(r)
    if pred(r,k)==left: lo=mid
    else: hi=mid
   result['boundaries'].append({'axis':a,'predicate':k,'lower':f'{lo:08x}','upper':f'{hi:08x}','gap':f32(f'{hi:08x}')-f32(f'{lo:08x}')})
 for a,w in sorted({(b['axis'],int(b[k],16)) for b in result['boundaries'] for k in ('lower','upper')}):
  r=probe(a,w)
  for mode in ('off','installed'):
   z=call(a,w,mode); assert all(z[k]==r[k] for k in keys); result['parity'].append({'axis':a,'word':f'{w:08x}','mode':mode,'match':True})
 result['status']='complete'
except Exception as e:
 result['status']='stopped'; result['reason']=str(e)
finally:
 result['input_sha256']=hashlib.sha256((p/'input.bin').read_bytes()).hexdigest(); result['selected_sha256']=hashlib.sha256((root/'selected_full.json').read_bytes()).hexdigest(); result['runner_sha256']=hashlib.sha256(runner.read_bytes()).hexdigest(); result['installed_dso_sha256']=hashlib.sha256(installed.read_bytes()).hexdigest(); result['capture_dso_sha256']=hashlib.sha256(research.read_bytes()).hexdigest(); (p/'sweep.json').write_text(json.dumps(result,indent=2)+'\n'); print('STATUS',result['status'],result.get('reason',''),flush=True)
