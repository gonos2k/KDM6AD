#!/usr/bin/env python3
import ctypes as C,csv,hashlib,json,math,os,pathlib,struct,subprocess,sys,tempfile
R=pathlib.Path(__file__).resolve().parent; P=R.parent; parent=P/'selected_full.json'; baseprobe=P/'f64_da_probe_20261112/result.json'; inst='/Users/yhlee/KDM6AD-k/libtorch/install/lib/libkdm6_c.2.0.0.dylib'; cap='/Users/yhlee/KDM6AD-k/host/research_evidence/native_f32_activation_boundary_20261111/source/build_f32_capture/libkdm6_c.dylib'
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest(); assert sha(parent)=='e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae'; assert sha(inst)=='7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7'; assert sha(cap)=='eabb607b08760a5b757031f864f6644e5f75aa83aebdc4c32f8fdfc8c2245c95'
fields=['th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg']; forcing=['rho','pii','p','delz']; p=json.loads(parent.read_text()); words=[w for k in fields+forcing for w in p['input_words_hex'][k]]; f32=lambda w:struct.unpack('>f',bytes.fromhex(w))[0]; w32=lambda v:struct.pack('>f',v).hex(); w64=lambda v:struct.pack('>d',v).hex(); f64=lambda h:struct.unpack('>d',bytes.fromhex(h.zfill(16)))[0]; values=list(map(f32,words)); assert len(values)==624 and list(map(w32,values))==words and p['xland_word_hex']=='40000000' and (p['dt'],p['ncmin_land'],p['ncmin_sea'])==(20,10,10)
D=C.c_double; H=C.c_void_p; PD=C.POINTER(D); PH=C.POINTER(H); arr=lambda x:(D*len(x))(*x)
def worker(mode,hexword):
 lib=C.CDLL(inst if mode.startswith('installed') else cap); fn=lib.kdm6_step_ad_c; fn.argtypes=[PD,PD,C.c_int,C.c_int,C.c_int,D,C.c_int,PD,PH,C.POINTER(C.c_float),D,D]; fn.restype=C.c_int; close=lib.kdm6_handle_closep_c; close.argtypes=[PH]; close.restype=C.c_int
 state=values[:468].copy();state[15]=f64(hexword); inp=arr(state); forc=arr(values[468:]);out=arr([float('nan')]*468); h=H(); xland=C.c_float(2); graph=mode.endswith('graph'); rc=fn(inp,forc,1,39,1,20,0 if graph else 1,out,C.byref(h),C.byref(xland),10,10); had=bool(h.value); cr=close(C.byref(h)) if had else None
 print(json.dumps({'mode':mode,'th_word':hexword,'rc':rc,'handle_nonnull':had,'close_rc':cr,'handle_null_after':not bool(h.value),'output_words':list(map(w64,out))}))
if len(sys.argv)>1:
 worker(sys.argv[1],sys.argv[2]); sys.exit(0)
env={k:v for k,v in os.environ.items() if not k.startswith('KDM6')}; env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_THREAD_LIMIT='1',DYLD_LIBRARY_PATH='/opt/homebrew/Caskroom/miniforge/base/lib/python3.9/site-packages/torch/lib')
events={}; log=[]
def call(mode,word):
 e=env.copy()
 with tempfile.TemporaryDirectory(prefix='capture_',dir=R) as td:
  if mode=='capture_on': e.update(KDM6_NATIVE_CAPTURE_DIR=td,KDM6_NATIVE_CAPTURE_ALL_K='1',KDM6_NATIVE_CAPTURE_CALL='1',KDM6_NATIVE_CAPTURE_B='0',KDM6_NATIVE_CAPTURE_MAX_ROWS='200000',KDM6_NATIVE_CAPTURE_MAX_BYTES='134217728')
  proc=subprocess.run([sys.executable,str(R/'probe.py'),mode,word],env=e,text=True,capture_output=True)
  if proc.returncode: raise RuntimeError((mode,word,proc.returncode,proc.stderr))
  result=json.loads(proc.stdout); assert result['rc']==0 and result['handle_null_after'] and (result['handle_nonnull']==mode.endswith('graph'))
  if mode=='capture_on':
   matches=list(pathlib.Path(td).glob('native_qnice*.csv')); assert len(matches)==1,(mode,word,matches,proc.stderr); lines=matches[0].read_text().splitlines(); assert lines[-1].endswith('status=complete')
   trace={}
   for row in csv.DictReader(x for x in lines if not x.startswith('#')):
    if row['stage']=='fd_satadj_inner' and row['k_zero']=='23':
     assert (row['runtime_call'],row['one_step_call'],row['substep'],row['b_zero'])==('1','1','0','0') and row['field'] not in trace
     trace[row['field']]={'dtype':row['dtype'],'raw_hex':row['raw_hex']}
   assert len(trace)==33 and trace['sw_percent']['dtype']=='f64',(word,trace)
   result['trace']=trace
  return result
def probe(w):
 if w not in events:
  r=call('capture_on',w);events[w]=r; print('event',w,f64(r['trace']['sw_percent']['raw_hex']),f64(r['trace']['activation_fraction_min_output']['raw_hex']),flush=True)
 return events[w]
def pred(w,k):
 t=probe(w)['trace'];return f64(t['sw_percent']['raw_hex'])>=0.48 if k=='sw' else f64(t['activation_fraction_min_output']['raw_hex'])>=1
base=w64(values[15]); bounds=[]
for k in ['sw','fraction']:
 lo=values[15]; hi=321.0; assert pred(w64(lo),k) and not pred(w64(hi),k)
 a=int(w64(lo),16);b=int(w64(hi),16)
 while b-a>1:
  m=(a+b)//2
  if pred(f'{m:016x}',k): a=m
  else: b=m
 bounds.append({'predicate':k,'lower_word':f'{a:016x}','upper_word':f'{b:016x}','lower_true':pred(f'{a:016x}',k),'upper_true':pred(f'{b:016x}',k),'gap':f64(f'{b:016x}')-f64(f'{a:016x}')})
 print('boundary',bounds[-1],flush=True)
# centers separated by 0.01 K from outermost boundaries; probes at +/- 1e-3, 1e-4, 1e-5 K
low=min(f64(b['lower_word']) for b in bounds)-0.01; high=max(f64(b['upper_word']) for b in bounds)+0.01
centers=[]
for name,center in [('lower',low),('upper',high)]:
 cw=w64(center); c=probe(cw); t=c['trace']; below=f64(t['activation_fraction_pow']['raw_hex'])<1; above=f64(t['activation_fraction_pow']['raw_hex'])>1
 assert (above if name=='lower' else below); signature=lambda x:tuple(x['trace'][key]['raw_hex'] for key in ('sw_positive','activation_fraction_pow_lt_one','activation_fraction_pow_eq_one','activation_fraction_pow_gt_one','ncact_raw_lt_nccn_rate_cap','ncact_raw_eq_nccn_rate_cap','ncact_raw_gt_nccn_rate_cap'))
 ps=[]
 for h in [1e-3,1e-4,1e-5]:
  for sign in (-1,1):
   w=w64(center+sign*h); v=probe(w); stable=signature(v)==signature(c); assert stable,(name,h,sign); ps.append({'h':h,'sign':sign,'word':w,'same_selected_activation_masks':stable})
 centers.append({'name':name,'word':cw,'value':center,'delta_from_nearest_boundary':min(abs(center-f64(b['lower_word'])) for b in bounds),'sw_percent':f64(t['sw_percent']['raw_hex']),'fraction_pow':f64(t['activation_fraction_pow']['raw_hex']),'probes':ps})
# compare every center, boundary endpoint, baseline, and +/-h event against installed value-only and graph and capture-off value and graph
comparisons=[]
for w in list(events):
 on=events[w]; runs={mode:call(mode,w) for mode in ('installed_value','installed_graph','capture_value','capture_graph')}; equal={mode:run['output_words']==on['output_words'] for mode,run in runs.items()}; assert all(equal.values()),(w,equal); comparisons.append({'word':w,'exact':equal,'return_codes':{k:{'rc':v['rc'],'close_rc':v['close_rc']} for k,v in runs.items()}})
 print('compared',w,flush=True)
result={'schema':'kdm6.host_selected_f64_da_boundary.v1','scope':'B=1 selected native column; standard f64 C ABI; capture is value-only; no host tile or f32 derivative claim','parent_sha256':sha(parent),'source_tile_sha256':p['source_tile_sha256'],'baseline_probe_sha256':sha(baseprobe),'source_sha256':sha(__file__),'installed_dso_sha256':sha(inst),'capture_dso_sha256':sha(cap),'input_words_f32':words,'roundtrip_f32_exact':True,'controls':{'shape':[1,39,1],'dt':20,'xland':2,'ncmin_land':10,'ncmin_sea':10,'thread_counts':1,'physics_environment':'KDM6 variables unset; capture controls only'},'trace_identity':{'runtime_call':1,'one_step_call':1,'substep':0,'b_zero':0,'k_zero':23,'native_level':16},'boundaries':bounds,'centers':centers,'events':list(events.values()),'parity':comparisons,'limitations':'Adjacent crossings establish local endpoint predicates; not global uniqueness. Selected masks stable over sampled +/-h only; no claim all process branches stable.'}
path=R/'result.json'; assert not path.exists();path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n'); print('RESULT_SHA',sha(path),flush=True)
