#!/usr/bin/env python3
"""Validate the independent fp64 state+forcing ABI on a supplied native trace.

No model integration, observation evaluation, normalization of native QN, or
full-host derivative is performed. A private trace remains a caller input.
"""
from __future__ import annotations
import argparse
import ctypes as ct
import hashlib
import json
from pathlib import Path
import numpy as np
from harness.native_trace_records import read_native_trace

STATE_FIELDS = ('TH','Q','QC','QR','QI','QS','QG','NN','NC','NI','NR','BG')
FORCING_FIELDS = ('DEN','PII','P','DELZ')
OUTPUT_SCALES = np.array([1.,1e-3,1e-3,1e-3,1e-3,1e-3,1e-3,1e8,1e8,1e6,1e6,1e-6])[:,None]
EPSILONS = (1e-2,3e-3,1e-3,3e-4,1e-4,3e-5,1e-5,3e-6,1e-6)
D = ct.POINTER(ct.c_double)

def ptr(a):
    return a.ctypes.data_as(D)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8388608),b''):h.update(b)
    return h.hexdigest()

class Kernel:
    def __init__(self, library, levels, dt, xland, ncmin_land, ncmin_sea):
        self.lib=ct.CDLL(str(Path(library).resolve()));self.levels=levels;self.dt=dt
        self.xland=np.array([xland],dtype=np.float32)
        self.ncmin=(ncmin_land,ncmin_sea)
        base=[D,D,ct.c_int,ct.c_int,ct.c_int,ct.c_double,ct.c_int,D,ct.POINTER(ct.c_void_p),ct.POINTER(ct.c_float),ct.c_double,ct.c_double,ct.c_uint32,ct.c_int64]
        for n in ['kdm6_step_ad_number_c','kdm6_step_ad_state_forcing_c']:
            fn=getattr(self.lib,n);fn.argtypes=base;fn.restype=ct.c_int
        self.lib.kdm6_handle_state_forcing_jvp_c.argtypes=[ct.c_void_p,D,D,D]
        self.lib.kdm6_handle_state_forcing_vjp_c.argtypes=[ct.c_void_p,D,D,D]
        self.lib.kdm6_handle_closep_c.argtypes=[ct.POINTER(ct.c_void_p)]
    def check(self, rc):
        if rc != 0:raise RuntimeError(f'C ABI returned {rc}')
    def forward(self,s,f,*,joint=True,record=False):
        s=np.ascontiguousarray(s,dtype=np.float64);f=np.ascontiguousarray(f,dtype=np.float64)
        out=np.empty_like(s);h=ct.c_void_p()
        fn=getattr(self.lib,'kdm6_step_ad_state_forcing_c' if joint else 'kdm6_step_ad_number_c')
        self.check(fn(ptr(s),ptr(f),1,self.levels,1,self.dt,int(not record),ptr(out),ct.byref(h),self.xland.ctypes.data_as(ct.POINTER(ct.c_float)),*self.ncmin,0,0))
        if not np.isfinite(out).all():raise RuntimeError('nonfinite forward')
        return out,h
    def jvp(self,h,vs,vf):
        out=np.empty_like(vs);self.check(self.lib.kdm6_handle_state_forcing_jvp_c(h,ptr(vs),ptr(vf),ptr(out)))
        if not np.isfinite(out).all():raise RuntimeError('nonfinite JVP')
        return out
    def vjp(self,h,u):
        gs=np.empty_like(u);gf=np.empty((4,self.levels),dtype=np.float64)
        self.check(self.lib.kdm6_handle_state_forcing_vjp_c(h,ptr(u),ptr(gs),ptr(gf)))
        if not (np.isfinite(gs).all() and np.isfinite(gf).all()):raise RuntimeError('nonfinite VJP')
        return gs,gf
    def close(self,h):self.check(self.lib.kdm6_handle_closep_c(ct.byref(h)))

def input_branch_summary(s,f):
    """Value-only initial-state diagnostics; not a full executed branch trace."""
    t=s[0]*f[1]
    return {'warm_initial_cells':int((t>=273.15).sum()),'cold_initial_cells':int((t<273.15).sum()),
            'minimum_distance_to_273_15_K':float(np.min(np.abs(t-273.15))),
            'zero_cells_by_state':{n:int((s[j]==0).sum()) for j,n in enumerate(STATE_FIELDS)},
            'rain_initial_inactive':int(((s[3]<=1e-9)|(s[10]<=1e-2)).sum()),
            'scope':'initial input diagnostics only; integer substep schedules and downstream limiter signatures not exposed by this ABI'}

def verify(a):
    output=Path(a.output).absolute()
    sources=[Path(a.trace).resolve(),Path(a.library).resolve(),Path(__file__).resolve()]
    if output.resolve() in sources or output.exists() or output.is_symlink():
        raise ValueError('output must be a new file distinct from every input/source')
    if min(a.i,a.j,a.levels,a.step)<=0:
        raise ValueError('native indices, step and level count must be positive')
    source_hashes={str(p):sha(p) for p in sources}
    rows=read_native_trace(a.trace);selected=[rows[('MP_INPUT',a.step,a.i,k,a.j)] for k in range(1,a.levels+1)]
    s=np.ascontiguousarray([[r.value(n) for r in selected] for n in STATE_FIELDS],dtype=np.float64)
    f=np.ascontiguousarray([[r.value(n) for r in selected] for n in FORCING_FIELDS],dtype=np.float64)
    dt=float(selected[0].value('dt'))
    if not all(r.value('dt')==dt for r in selected):
        raise ValueError('trace level time steps differ')
    kernel=Kernel(a.library,a.levels,dt,a.xland,a.ncmin_land,a.ncmin_sea)
    report={'schema':'kdm6.state_forcing_ad.v1','scope':'local independent K_s/K_F in fp64, legacy raw native coordinates; no full host/tendency/RTTOV derivative',
            'trace_sha256':sha(a.trace),'library_sha256':sha(a.library),'script_sha256':sha(__file__),
            'source':{'step':a.step,'i':a.i,'j':a.j,'levels':a.levels,'dt':dt,'physics_variant':0,'dry_number':0,'xland':a.xland,'ncmin_land':a.ncmin_land,'ncmin_sea':a.ncmin_sea},
            'number_basis':'as-executed legacy raw; NN may contain the native volume CCN profile; no homogeneous dry-number interpretation asserted',
            'criteria':{'fd_relative_per_field':3e-5,'fd_absolute_per_field_in_output_scale':1e-8,'dot_relative':1e-9,'epsilons':EPSILONS},'initial_branch_summary':input_branch_summary(s,f),'directions':{}}
    old,h0=kernel.forward(s,f,joint=False);kernel.close(h0)
    value,h0=kernel.forward(s,f);kernel.close(h0)
    out,h=kernel.forward(s,f,record=True)
    report['forward_raw_bitwise_equal']=bool(np.array_equal(old.view('u8'),value.view('u8')) and np.array_equal(old.view('u8'),out.view('u8')))
    if not report['forward_raw_bitwise_equal']:raise RuntimeError('old/new fp64 forward differs')
    phase=np.arange(a.levels,dtype=np.float64)
    vs=np.zeros_like(s);vs[0]=.2*np.sin(.37*(phase+1));vs[1]=.02*s[1]*np.cos(.29*(phase+2))
    vf=.01*f*np.sin(.31*(phase[None,:]+np.arange(4)[:,None]+1))
    u=np.ascontiguousarray(np.sin(.23*(np.arange(s.size).reshape(s.shape)+1))/OUTPUT_SCALES)
    try:
        gs,gf=kernel.vjp(h,u);report['forcing_cotangent_maxabs']={n:float(np.max(np.abs(gf[j]))) for j,n in enumerate(FORCING_FIELDS)}
        directions={'state_theta_qv':(vs,np.zeros_like(f))}
        for j,n in enumerate(FORCING_FIELDS):
            only=np.zeros_like(f);only[j]=vf[j];directions['forcing_'+n]=(np.zeros_like(s),only)
        directions['mixed']=(vs,vf)
        for name,(ds,df) in directions.items():
            jv=kernel.jvp(h,ds,df);lhs=float(np.sum(u*jv));rhs=float(np.sum(gs*ds)+np.sum(gf*df));dot_error=abs(lhs-rhs)/max(abs(lhs),abs(rhs),1e-12)
            trials=[]
            for eps in EPSILONS:
                yp,hp=kernel.forward(s+eps*ds,f+eps*df);kernel.close(hp)
                ym,hm=kernel.forward(s-eps*ds,f-eps*df);kernel.close(hm)
                fd=(yp-ym)/(2*eps);diff=np.max(np.abs((fd-jv)/OUTPUT_SCALES),axis=1)
                scale=np.maximum(np.max(np.abs(jv/OUTPUT_SCALES),axis=1),np.max(np.abs(fd/OUTPUT_SCALES),axis=1))
                ratio=diff/(1e-8+3e-5*scale)
                trials.append({'epsilon':eps,'max_tolerance_ratio':float(np.max(ratio)),
                               'per_field_tolerance_ratio':dict(zip(STATE_FIELDS,map(float,ratio))),
                               'per_field_scaled_absolute_error':dict(zip(STATE_FIELDS,map(float,diff))),
                               'weighted_relative_error':float(np.linalg.norm((fd-jv)/OUTPUT_SCALES)/max(np.linalg.norm(jv/OUTPUT_SCALES),np.linalg.norm(fd/OUTPUT_SCALES),1e-12)),
                               'initial_plus_branch_summary':input_branch_summary(s+eps*ds,f+eps*df),
                               'initial_minus_branch_summary':input_branch_summary(s-eps*ds,f-eps*df)})
            best=min(trials,key=lambda x:x['max_tolerance_ratio'])
            report['directions'][name]={'dot_lhs':lhs,'dot_rhs':rhs,'dot_relative_error':dot_error,'best_epsilon':best['epsilon'],'best_max_tolerance_ratio':best['max_tolerance_ratio'],'trials':trials,'passed':bool(dot_error<=1e-9 and best['max_tolerance_ratio']<=1)}
        report['passed']=all(x['passed'] for x in report['directions'].values())
    finally:kernel.close(h)
    if any(sha(p)!=digest for p,digest in source_hashes.items()):
        raise RuntimeError('a pinned input/source changed during verification')
    serialized=json.dumps(report,indent=2,allow_nan=False)+'\n'
    with output.open('x') as stream:
        stream.write(serialized)
    print(json.dumps({'passed':report['passed'],'directions':{n:{k:v for k,v in r.items() if k!='trials'} for n,r in report['directions'].items()}},indent=2))
    if not report['passed']:raise SystemExit(1)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--library',type=Path,required=True);p.add_argument('--trace',type=Path,required=True);p.add_argument('--step',type=int,required=True);p.add_argument('--i',type=int,required=True);p.add_argument('--j',type=int,required=True);p.add_argument('--levels',type=int,default=39);p.add_argument('--xland',type=float,required=True);p.add_argument('--ncmin-land',type=float,default=0);p.add_argument('--ncmin-sea',type=float,default=0);p.add_argument('--output',type=Path,required=True);verify(p.parse_args())
