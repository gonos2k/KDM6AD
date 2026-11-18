import csv, gzip, hashlib, json, os, pathlib, shutil, struct, subprocess, time
R=pathlib.Path(__file__).resolve().parent; os.chdir(R)
runner=str(R/'runner_build/native_f32_cabi_probe'); lib=str(R/'source/build_f32_capture/libkdm6_c.dylib'); installed='/Users/yhlee/KDM6AD-k/libtorch/install/lib/libkdm6_c.2.0.0.dylib'
base={'th16':int('439ff9b6',16),'qv16':int('3befe5d1',16)}
out=R/'raw/sweep'; out.mkdir(exist_ok=False)
env={k:v for k,v in os.environ.items() if not k.startswith('KDM6')}; env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_THREAD_LIMIT='1')
cache={}; events=[]
def f(w): return struct.unpack('>f',bytes.fromhex(w))[0]
def call(axis,word,mode='on',library=lib):
 tag=f'{axis}_{word:08x}_{mode}'; d=out/tag; d.mkdir(); capture=mode=='on'; e=env.copy()
 if capture: e.update(KDM6_NATIVE_CAPTURE_DIR=str(d),KDM6_NATIVE_CAPTURE_ALL_K='1',KDM6_NATIVE_CAPTURE_CALL='1',KDM6_NATIVE_CAPTURE_B='0',KDM6_NATIVE_CAPTURE_MAX_ROWS='200000',KDM6_NATIVE_CAPTURE_MAX_BYTES='134217728')
 cmd=[runner,'--library',library,'--input',str(R/'input.bin'),'--output',str(d/'out.json'),'--axis',axis,'--word',f'{word:08x}']; t=time.time(); p=subprocess.run(cmd,env=e,capture_output=True,text=True); assert p.returncode==0,(tag,p.stderr)
 data=json.loads((d/'out.json').read_text()); trace={}
 if capture:
  path=next(d.glob('native_qnice*.csv')); lines=path.read_text().splitlines(); assert lines[-1].endswith('status=complete'),lines[-1]
  for row in csv.DictReader(x for x in lines if not x.startswith('#')):
   if row['stage']=='fd_satadj_inner' and row['k_zero']=='23':
    assert row['runtime_call']=='1' and row['substep']=='0' and row['field'] not in trace,row
    trace[row['field']]={'dtype':row['dtype'],'raw_hex':row['raw_hex']}
  assert len(trace)==33,(tag,len(trace)); assert trace['sw_percent']['dtype']=='f32'
 return {'axis':axis,'word':f'{word:08x}','value':f(f'{word:08x}'),'trace':trace,'state_output_f32_words':data['state_output_f32_words'],'precip_increment_f32_words':data['precip_increment_f32_words'],'rhog_output_f32_words':data['rhog_output_f32_words'],'elapsed_s':time.time()-t},d

def probe(axis,w):
 key=(axis,w)
 if key not in cache:
  result,d=call(axis,w); cache[key]=result; events.append(result); shutil.rmtree(d)
  print(axis,hex(w), f(result['trace']['sw_percent']['raw_hex']),f(result['trace']['activation_fraction_min_output']['raw_hex']),flush=True)
 return cache[key]
def pred(r,which):
 return f(r['trace']['sw_percent']['raw_hex'])>=0.48 if which=='sw' else f(r['trace']['activation_fraction_min_output']['raw_hex'])>=1.0
boundaries=[]
for axis in base:
 for which in ('sw','fraction'):
  origin=base[axis]; first=pred(probe(axis,origin),which); direction=1 if axis=='qv16' else -1
  # Move towards opposite predicate; orientation is increasing word for QV, decreasing for TH.
  step=1; sign=direction if not first else -direction
  while True:
   w=origin+sign*step; other=pred(probe(axis,w),which)
   if other!=first: break
   step*=2; assert step<2**24
  lo,hi=sorted((origin,w))
  while hi-lo>1:
   mid=(lo+hi)//2
   if pred(probe(axis,mid),which)==pred(probe(axis,lo),which): lo=mid
   else: hi=mid
  assert pred(probe(axis,lo),which)!=pred(probe(axis,hi),which)
  boundaries.append({'axis':axis,'predicate':which,'lower_word':f'{lo:08x}','upper_word':f'{hi:08x}','lower_predicate':pred(probe(axis,lo),which),'upper_predicate':pred(probe(axis,hi),which),'gap':f(f'{hi:08x}')-f(f'{lo:08x}'),'adjacent_words':hi-lo==1})
  print('BOUNDARY',boundaries[-1],flush=True)
checks=[]
for axis,w in sorted({(b['axis'],int(b[k],16)) for b in boundaries for k in ('lower_word','upper_word')}):
 on,d=call(axis,w,'on'); off,e=call(axis,w,'off'); inst,g=call(axis,w,'installed',installed)
 keys=['state_output_f32_words','precip_increment_f32_words','rhog_output_f32_words']; comparisons={k: on[k]==off[k]==inst[k] for k in keys}; assert all(comparisons.values()),(axis,w,comparisons)
 assert on['trace']==cache[(axis,w)]['trace']
 for path in d.glob('*.csv'):
  with open(path,'rb') as src,gzip.open(out/(f'{axis}_{w:08x}_'+path.name+'.gz'),'wb') as dst: shutil.copyfileobj(src,dst)
 checks.append({'axis':axis,'word':f'{w:08x}','comparisons':comparisons,'trace_repeated_exact':True})
 for q in (d,e,g): shutil.rmtree(q)
receipt={'schema':'kdm6.native_f32_activation_boundary.sweep.v1','input_sha256':hashlib.sha256((R/'input.bin').read_bytes()).hexdigest(),'events':events,'boundaries':boundaries,'terminal_checks':checks,'scope':'single native column, one value-only standard f32 C ABI call; no host tile or f64 AD claim','trace_identity':{'runtime_call':1,'one_step_call':1,'substep':0,'b_zero':0,'k_zero':23,'native_level':16},'environment':{'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','OMP_THREAD_LIMIT':'1','KDM6_physics_environment':'unset; capture controls only'},'unique_events':len(cache),'search':'exponential bracket then integer-word binary search; signs chosen from local expected orientation; adjacent endpoints certified, not global uniqueness'}
(out/'sweep.json').write_text(json.dumps(receipt,separators=(',',':'))+'\n')
print('DONE',len(events),flush=True)
