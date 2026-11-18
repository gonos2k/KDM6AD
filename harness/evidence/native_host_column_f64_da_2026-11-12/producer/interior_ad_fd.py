#!/usr/bin/env python3
import ctypes as C,hashlib,json,math,os,pathlib,struct
R=pathlib.Path(__file__).resolve().parent; P=R.parent; parent=P/'selected_full.json'; boundary=R/'result.json'; libpath=pathlib.Path('/Users/yhlee/KDM6AD-k/libtorch/install/lib/libkdm6_c.2.0.0.dylib'); sha=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
assert sha(parent)=='e3117d277a073042bbae648b87e7dd6661d14b600fc8245f6aeabc19fe715eae' and sha(boundary)=='c2a5260e2d1d3e33bf0bad718850394e72deeae7d1e7e4fa34ec84207a54b179' and sha(libpath)=='7adcb6921f6205af66c62720ce9447928a1608f5c261546183b928bebbd9dba7'
for k in list(os.environ):
 if k.startswith('KDM6'): del os.environ[k]
os.environ.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OMP_THREAD_LIMIT='1')
p=json.loads(parent.read_text()); b=json.loads(boundary.read_text()); fields=['th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg']; forcing=['rho','pii','p','delz']; f32=lambda w:struct.unpack('>f',bytes.fromhex(w))[0]; f64=lambda w:struct.unpack('>d',bytes.fromhex(w.zfill(16)))[0]; w32=lambda v:struct.pack('>f',v).hex(); w64=lambda v:struct.pack('>d',v).hex(); words=[w for k in fields+forcing for w in p['input_words_hex'][k]]; values=list(map(f32,words));assert len(values)==624 and list(map(w32,values))==words and b['input_words_f32']==words
D=C.c_double; H=C.c_void_p; PD=C.POINTER(D); PH=C.POINTER(H); A=lambda xs:(D*len(xs))(*xs); lib=C.CDLL(str(libpath)); step=lib.kdm6_step_ad_c; step.argtypes=[PD,PD,C.c_int,C.c_int,C.c_int,D,C.c_int,PD,PH,C.POINTER(C.c_float),D,D];step.restype=C.c_int
jvp=lib.kdm6_handle_jvp_c;vjp=lib.kdm6_handle_vjp_c
for fn in (jvp,vjp):fn.argtypes=[H,PD,PD];fn.restype=C.c_int
close=lib.kdm6_handle_closep_c;close.argtypes=[PH];close.restype=C.c_int
xland=C.c_float(2);forcing_in=A(values[468:]); events={v['th_word']:v for v in b['events']}; mask_names=['sw_positive','activation_fraction_pow_lt_one','activation_fraction_pow_eq_one','activation_fraction_pow_gt_one','ncact_raw_lt_nccn_rate_cap','ncact_raw_eq_nccn_rate_cap','ncact_raw_gt_nccn_rate_cap']; ni=8*39+15

def evaluate(word,graph):
 state=values[:468].copy();state[15]=f64(word); inp=A(state);out=A([float('nan')]*468);handle=H();rc=step(inp,forcing_in,1,39,1,20,0 if graph else 1,out,C.byref(handle),C.byref(xland),10,10); assert rc==0 and bool(handle.value)==graph
 data={'rc':rc,'output_words':list(map(w64,out)),'handle_nonnull_before_close':bool(handle.value)}
 if graph:
  v=A([1 if i==15 else 0 for i in range(468)]);u=A([1 if i==ni else 0 for i in range(468)]);jo=A([float('nan')]*468);vo=A([float('nan')]*468);jr=jvp(handle,v,jo);vr=vjp(handle,u,vo);cr=close(C.byref(handle));assert jr==vr==cr==0 and not handle.value
  data.update(jvp_rc=jr,vjp_rc=vr,close_rc=cr,handle_null_after_close=True,jvp_words=list(map(w64,jo)),vjp_words=list(map(w64,vo)),jvp_finite_count=sum(map(math.isfinite,jo)),vjp_finite_count=sum(map(math.isfinite,vo)),nc16_jvp=jo[ni],th16_vjp=vo[15]);assert math.isfinite(jo[ni]) and math.isfinite(vo[15])
 assert data['output_words']==events[word]['output_words'];return data
centers=[]
for c in b['centers']:
 cw=c['word']; graph=evaluate(cw,True); base=evaluate(cw,False); mask=lambda w:{k:events[w]['trace'][k] for k in mask_names}; base_mask=mask(cw); diffs=[]
 for h in (1e-3,1e-4,1e-5):
  ps=[v for v in c['probes'] if v['h']==h];lo=next(v for v in ps if v['sign']==-1);hi=next(v for v in ps if v['sign']==1); lw=lo['word'];uw=hi['word']; l=evaluate(lw,False);u=evaluate(uw,False); delta=f64(uw)-f64(lw); ylo=f64(l['output_words'][ni]);yhi=f64(u['output_words'][ni]);fd=(yhi-ylo)/delta; ad=graph['nc16_jvp'];adj=graph['th16_vjp'];res=fd-ad
  diffs.append({'h_requested':h,'lower_word':lw,'upper_word':uw,'lower_delta':f64(lw)-f64(cw),'upper_delta':f64(uw)-f64(cw),'denominator':delta,'lower':l,'upper':u,'lower_masks':mask(lw),'upper_masks':mask(uw),'selected_masks_stable':mask(lw)==base_mask==mask(uw),'nc16_lower':ylo,'nc16_upper':yhi,'output_difference':yhi-ylo,'resolved_distinct_output_words':l['output_words'][ni]!=u['output_words'][ni],'central_difference':fd,'jvp':ad,'vjp_dot_v':adj,'fd_minus_jvp':res,'absolute_residual':abs(res),'relative_residual_to_jvp':abs(res)/abs(ad) if ad else None,'jvp_minus_vjp_dot_v':ad-adj,'all_finite':all(map(math.isfinite,[fd,ad,adj,res]))})
 centers.append({'name':c['name'],'th_word':cw,'th_value':f64(cw),'selected_activation_masks':base_mask,'graph':graph,'value_only':base,'differences':diffs})
result={'schema':'kdm6.host_selected_f64_interior_ad_fd.v1','parent_sha256':sha(parent),'boundary_sha256':sha(boundary),'script_sha256':sha(__file__),'library_sha256':sha(libpath),'controls':{'shape':[1,39,1],'dt':20,'xland':2,'ncmin_land':10,'ncmin_sea':10,'threads':1,'physics_environment':'KDM6 variables unset'},'seed':'TH16 unit JVP; NC16 unit VJP; forcing fixed','centers':centers,'limitations':'Selected activation masks only; no assertion all process branches stable. Central differences are diagnostic; no pass tolerance imposed. Single-column f64 DA, not host-tile or f32 AD evidence.'};path=R/'interior_ad_fd.json';assert not path.exists();path.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n');print('sha',sha(path))
for c in centers:
 print(c['name'],c['th_value'],c['graph']['nc16_jvp'],c['graph']['th16_vjp'],[(d['h_requested'],d['central_difference'],d['relative_residual_to_jvp']) for d in c['differences']])
