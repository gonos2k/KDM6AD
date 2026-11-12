#!/usr/bin/env python3
import ctypes as C, hashlib, json, math, os, pathlib, struct
R=pathlib.Path(__file__).resolve().parent; P=R.parent
for k in list(os.environ):
 if k.startswith('KDM6'): del os.environ[k]
os.environ.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_THREAD_LIMIT='1')
sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
parent=P/'selected_full.json'; expected='e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae'; assert sha(parent)==expected
libpath=pathlib.Path('/Users/yhlee/KDM6AD-k/libtorch/install/lib/libkdm6_c.2.0.0.dylib'); libsha='7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7'; assert sha(libpath)==libsha
old=P/'activation_boundary_coupled_fixed_20261112/th_439ffb36_installed/out.json'; oldsha='89d158afd6e69e04a394052384398e4b90179e810215767c803bcf7aa79f3aaf'; assert sha(old)==oldsha
p=json.loads(parent.read_text()); assert p['dt']==20 and p['ncmin_land']==10 and p['ncmin_sea']==10 and p['xland_word_hex']=='40000000'
fields=['th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg']; forcing=['rho','pii','p','delz']
words=[w for name in fields+forcing for w in p['input_words_hex'][name]]; assert len(words)==624 and all(len(p['input_words_hex'][n])==39 for n in fields+forcing)
f32=lambda w:struct.unpack('>f',bytes.fromhex(w))[0]
w32=lambda v:struct.pack('>f',v).hex()
w64=lambda v:struct.pack('>d',v).hex()
values=[f32(w) for w in words]; assert all(math.isfinite(v) for v in values); assert [w32(v) for v in values]==words
b=json.loads(old.read_text()); assert words[:468]==b['source_state_f32_words'] and words[468:]==b['source_forcing_f32_words']
D=C.c_double; H=C.c_void_p; PD=C.POINTER(D); PH=C.POINTER(H)
lib=C.CDLL(str(libpath)); step=lib.kdm6_step_ad_c; step.argtypes=[PD,PD,C.c_int,C.c_int,C.c_int,D,C.c_int,PD,PH,C.POINTER(C.c_float),D,D]; step.restype=C.c_int
jvp=lib.kdm6_handle_jvp_c; vjp=lib.kdm6_handle_vjp_c
for fn in (jvp,vjp): fn.argtypes=[H,PD,PD]; fn.restype=C.c_int
close=lib.kdm6_handle_closep_c; close.argtypes=[PH]; close.restype=C.c_int
arr=lambda vals:(D*len(vals))(*vals)
forcing_in=arr(values[468:]); xland=C.c_float(2); cases=[]
for name,th in [('baseline',values[15]),('candidate',320.0197)]:
 state=values[:468].copy();state[15]=th; inp=arr(state); record={'name':name,'th16':th,'th16_f64_word':w64(th),'input_state_f64_words':[w64(v) for v in state]}
 for flag,label in [(1,'value_only'),(0,'graph')]:
  out=arr([float('nan')]*468); handle=H(); rc=step(inp,forcing_in,1,39,1,20,flag,out,C.byref(handle),C.byref(xland),10,10); data={'rc':rc,'handle_nonnull':bool(handle.value),'output_f64_words':[w64(v) for v in out]}; record[label]=data
  if rc!=0: raise RuntimeError((name,label,rc))
  if flag==1: assert not handle.value
  else:
   assert handle.value; v=arr([1.0 if i==15 else 0.0 for i in range(468)]); u=arr([1.0 if i==8*39+15 else 0.0 for i in range(468)]); jout=arr([float('nan')]*468); gout=arr([float('nan')]*468)
   jr=jvp(handle,v,jout); vr=vjp(handle,u,gout); cr=close(C.byref(handle)); data.update(jvp_rc=jr,vjp_rc=vr,close_rc=cr,handle_null_after_close=not bool(handle.value),jvp_f64_words=[w64(x) for x in jout],vjp_f64_words=[w64(x) for x in gout],jvp_finite_count=sum(math.isfinite(x) for x in jout),vjp_finite_count=sum(math.isfinite(x) for x in gout),selected_jvp_nc16=jout[8*39+15],selected_vjp_th16=gout[15]); assert jr==vr==cr==0 and not handle.value
 record['value_graph_bitwise_equal']=record['value_only']['output_f64_words']==record['graph']['output_f64_words'];cases.append(record)
base=cases[0]['value_only']['output_f64_words']; f32out=[w for block in b['state_output_f32_words'] for w in block]; rounded=[w32(struct.unpack('>d',bytes.fromhex(w))[0]) for w in base];
result={'schema':'kdm6.host_selected_f64_da_ctypes_probe.v1','scope':'single host-selected input column; production-default f64 DA vs separate operational f32 value map; no branch capture or host tile parity','source':{'selected_full_path':str(parent),'selected_full_sha256':sha(parent),'source_tile_sha256':p['source_tile_sha256'],'input_f32_words':words,'input_widened_f64_words':[w64(v) for v in values],'roundtrip_f32_exact':True,'input_f64_exactly_widens_all_624':True,'selected_f32_call_path':str(old),'selected_f32_call_sha256':sha(old),'library_path':str(libpath),'library_sha256':sha(libpath),'probe_sha256':sha(__file__)},'controls':{'im':1,'kme':39,'jme':1,'dt':20,'xland_f32':2,'ncmin_land':10,'ncmin_sea':10,'omp_num_threads':1,'mkl_num_threads':1,'omp_thread_limit':1,'KDM6_environment':'unset'},'packing':{'state':fields,'forcing':forcing,'levels':'bottom-first','jvp_seed':'TH16=1','vjp_seed':'NC16=1'},'cases':cases,'separate_f32_baseline_comparison':{'note':'f64 output rounded to f32 versus stored operational f32 value output; distinct computational maps','count':468,'rounded_equal_count':sum(x==y for x,y in zip(rounded,f32out)),'rounded_different_count':sum(x!=y for x,y in zip(rounded,f32out)),'f64_output_rounded_to_f32_words':rounded,'operational_f32_output_words':f32out}}
outpath=R/'result.json'; assert not outpath.exists(); outpath.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n'); print('result',sha(outpath)); print([(c['name'],c['value_graph_bitwise_equal'],c['graph']['jvp_finite_count'],c['graph']['vjp_finite_count'],c['graph']['selected_jvp_nc16'],c['graph']['selected_vjp_th16']) for c in cases]); print(result['separate_f32_baseline_comparison']['rounded_different_count'])
