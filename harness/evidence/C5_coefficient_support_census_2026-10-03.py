#!/usr/bin/env python3
"""Input-only C5 RTTOV coefficient-domain census; no RT, BT, FD, or K calls."""
from __future__ import annotations
import ctypes, hashlib, json, os, subprocess, tempfile
from pathlib import Path
import numpy as np
import netCDF4

REPO = Path('/private/tmp/KDM6AD-dry-number-optics')
EVIDENCE = Path('/private/tmp/KDM6AD-c5-native39-prepared-2026-10-03/evidence')
RULE = EVIDENCE / 'c5_rttov_coefficient_support_rule_v4_sea_iremis_20261003.json'
INPUT_RECEIPT = Path('/private/tmp/KDM6AD-c5-liquid-input-2026-10-03/evidence/c5_liquid_input_census_2026-10-03.json')
INPUT_NPZ = Path('/private/tmp/KDM6AD-c5-liquid-input-2026-10-03/evidence/c5_selected_liquid_input.npz')
PREPARED_NPZ = EVIDENCE / 'prepared_c5_native39_plus_reference_top_profile.npz'
FORECAST = Path('/private/tmp/KDM6AD-nccn-zero-merge603ea4a-host-confirm/case/runs/mp337_merge603ea4a_off_0min40s_hist0_20261003_102038_p26153/klfs_lc05_fcst.202507190000')
RTTOV = Path('/Users/yhlee/AD-RTTOV/external/rttov14/src')
COEF = RTTOV / 'rtcoef_rttov14/rttov13pred54L/rtcoef_gkompsat2_1_ami_o3co2.dat'
REF = RTTOV / 'rttov_test/tests.1.gfortran-openmp/ami/501/in/profiles/004/atm'
TIMES = (1, 2)
NATIVE_K = 39
EPS_QC = 1e-15

F90 = r'''subroutine get_weights(ncoef,nuser,pcoef,puser,weights,starts,ends) bind(C,name="get_weights")
  use iso_c_binding, only: c_int, c_double
  use rttov_kinds, only: jpim, jprv
  implicit none
  integer(c_int), value :: ncoef,nuser
  real(c_double), intent(in) :: pcoef(ncoef),puser(nuser)
  real(c_double), intent(out) :: weights(nuser,ncoef)
  integer(c_int), intent(out) :: starts(ncoef),ends(ncoef)
  real(jprv) :: px1(ncoef),px2(nuser),pz(nuser,ncoef)
  integer(jpim) :: kstart(ncoef),kend(ncoef)
#include "rttov_layeravg.interface"
  pz=0.0_jprv
  px1=log(real(pcoef,kind=jprv))
  px2=log(real(puser,kind=jprv))
  call rttov_layeravg(px1,px2,int(ncoef,jpim),int(nuser,jpim),pz,kstart,kend,int(4,jpim))
  weights=real(pz,kind=c_double)
  starts=int(kstart,kind=c_int)
  ends=int(kend,kind=c_int)
end subroutine get_weights

subroutine map_profiles(ncoef,nuser,pcoef,puser,values,mapped,starts,ends) bind(C,name="map_profiles")
  use iso_c_binding, only: c_int, c_double
  use rttov_kinds, only: jpim, jprv
  implicit none
  integer(c_int), value :: ncoef,nuser
  real(c_double), intent(in) :: pcoef(ncoef),puser(nuser),values(nuser,4)
  real(c_double), intent(out) :: mapped(ncoef,4)
  integer(c_int), intent(out) :: starts(ncoef),ends(ncoef)
  real(jprv) :: px1(ncoef),px2(nuser),pz(nuser,ncoef)
  real(jprv) :: qmoist(nuser),o3moist(nuser),co2moist(nuser),factor(nuser)
  real(jprv) :: qdry(nuser),o3dry(nuser),co2dry(nuser),tprof(nuser)
  integer(jpim) :: kstart(ncoef),kend(ncoef),j
#include "rttov_layeravg.interface"
  pz=0.0_jprv
  px1=log(real(pcoef,kind=jprv))
  px2=log(real(puser,kind=jprv))
  call rttov_layeravg(px1,px2,int(ncoef,jpim),int(nuser,jpim),pz,kstart,kend,int(4,jpim))
  tprof=real(values(:,1),kind=jprv)
  qmoist=real(values(:,2),kind=jprv)
  o3moist=real(values(:,3),kind=jprv)
  co2moist=real(values(:,4),kind=jprv)
  factor=1.0_jprv/(1.0_jprv-qmoist*1.0E-06_jprv)
  qdry=factor*qmoist
  o3dry=factor*o3moist
  co2dry=factor*co2moist
  do j=1,ncoef
    mapped(j,1)=real(sum(pz(kstart(j):kend(j),j)*tprof(kstart(j):kend(j))),kind=c_double)
    mapped(j,2)=real(sum(pz(kstart(j):kend(j),j)*qdry(kstart(j):kend(j))),kind=c_double)
    mapped(j,3)=real(sum(pz(kstart(j):kend(j),j)*o3dry(kstart(j):kend(j))),kind=c_double)
    mapped(j,4)=real(sum(pz(kstart(j):kend(j),j)*co2dry(kstart(j):kend(j))),kind=c_double)
  enddo
  starts=int(kstart,kind=c_int)
  ends=int(kend,kind=c_int)
end subroutine map_profiles
'''

def sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''): h.update(block)
    return h.hexdigest()

def compile_weights(tmp: Path):
    src=tmp/'rttov_weights.F90'; obj=tmp/'rttov_weights.o'; lib=tmp/'rttov_weights.dylib'
    src.write_text(F90)
    inc=RTTOV/'include'; mod=RTTOV/'mod'; archive=RTTOV/'lib/librttov14_main.a'
    sdk=subprocess.check_output(['xcrun','--show-sdk-path'],text=True).strip()
    subprocess.run(['gfortran',f'-I{inc}',f'-I{mod}','-c',str(src),'-o',str(obj)],check=True)
    subprocess.run(['gfortran','-dynamiclib',f'-Wl,-syslibroot,{sdk}',f'-I{inc}',f'-I{mod}',str(obj),str(archive),'-o',str(lib)],check=True)
    fn=ctypes.CDLL(str(lib)).map_profiles
    fn.argtypes=[ctypes.c_int,ctypes.c_int,
        np.ctypeslib.ndpointer(np.float64,flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(np.float64,flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(np.float64,flags='F_CONTIGUOUS'),
        np.ctypeslib.ndpointer(np.float64,flags='F_CONTIGUOUS'),
        np.ctypeslib.ndpointer(np.int32,flags='C_CONTIGUOUS'),
        np.ctypeslib.ndpointer(np.int32,flags='C_CONTIGUOUS')]
    fn.restype=None
    compiler=subprocess.check_output(['gfortran','--version'],text=True).splitlines()[0]
    return fn,sha(src),sha(lib),sha(archive),compiler,sdk

def parse_coef():
    lines=COEF.read_text().splitlines()
    # v13 reference pressure half/full grid comes from mixed-gas REFERENCE_PROFILE.
    # Extract the file's actual gas order from FAST_MODEL_VARIABLES.
    names=[]
    for line in lines[lines.index('FAST_MODEL_VARIABLES')+1:lines.index('README_SPECTRAL_RESPONSE_FUNCTION')]:
        token=line.split('!')[0].strip()
        if token in ('Mixed_gases','Water_vapour','Ozone','WV_Continuum','CO2'): names.append(token)
    if names != ['Mixed_gases','Water_vapour','Ozone','WV_Continuum','CO2']:
        raise ValueError(f'unexpected coefficient gas order: {names}')
    nlev=54
    rp=[]; vals={}
    i=lines.index('REFERENCE_PROFILE')+1
    while i<len(lines) and len(rp)<nlev:
        q=lines[i].strip(); i+=1
        if not q or q.startswith('!'): continue
        a=[float(x) for x in q.split()]
        if len(a)>=2: rp.append(a[0])
    vals['reference_temperature']=[]
    # First table after REFERENCE_PROFILE is Mixed_gases: [p,T,mixed...]
    i=lines.index('REFERENCE_PROFILE')+1
    while i<len(lines):
        if lines[i].strip().startswith('!     Mixed_gases'): i+=1; break
        i+=1
    for _ in range(nlev):
        a=[float(x) for x in lines[i].split()]; vals['reference_temperature'].append(a[1]); i+=1
    # The selected separate RTTOV profile 004 is the declared background source.
    # Coefficient limits: first 54 numeric rows are T envelope; then named gas blocks.
    env=lines.index('PROFILE_ENVELOPE')+1
    while env<len(lines) and (not lines[env].strip() or lines[env].lstrip().startswith('!')): env+=1
    tenv=[]
    for _ in range(nlev):
        a=[float(x) for x in lines[env].split()]; tenv.append(a[1:3]); env+=1
    genv={}
    for name in names:
        while env<len(lines) and name not in lines[env]: env+=1
        if env>=len(lines): raise ValueError(f'missing coefficient envelope gas {name}')
        env+=1
        while env<len(lines) and (not lines[env].strip() or lines[env].lstrip().startswith('!')): env+=1
        row=[]
        for _ in range(nlev):
            a=[float(x) for x in lines[env].split()]; row.append(a[1:3]); env+=1
        genv[name]=np.asarray(row,dtype=np.float64)
    ph=np.asarray(rp,dtype=np.float64); pc=(ph[:-1]+ph[1:])*0.5
    tenv=np.asarray(tenv,dtype=np.float64)
    # Source: v13 envelope levels are averaged onto coefficient layers; defaults T=10%, gas=20%.
    tmax=0.5*(tenv[:-1,0]+tenv[1:,0])*1.1
    tmin=0.5*(tenv[:-1,1]+tenv[1:,1])*0.9
    limits={}
    for name,a in genv.items():
        limits[name]=(0.5*(a[:-1,1]+a[1:,1])*0.8,
                      0.5*(a[:-1,0]+a[1:,0])*1.2)
    return ph,pc,tmin,tmax,limits,names

def load_reference():
    return {name:np.loadtxt(REF/f'{name}.txt',dtype=np.float64) for name in ('p','p_half','t','q','o3','co2')}

def profile_extended(native_t,native_q_moist,native_p,native_half_bottom_up,ref):
    # All internal arrays are RTTOV order: top to surface. Native values preserved.
    native_p=native_p[::-1].copy(); native_t=native_t[::-1].copy(); native_q_moist=native_q_moist[::-1].copy()
    native_half=native_half_bottom_up[::-1].copy()
    ptop=float(native_half[0]); ip=int(np.searchsorted(ref['p_half'],ptop,side='left'))
    bg_half=np.concatenate((ref['p_half'][:ip],[ptop]))
    if bg_half.size<2: raise ValueError('no above-top reference layers')
    bg_p=ref['p'][:max(ip-1,0)]
    partial=float(np.sqrt(bg_half[-2]*bg_half[-1]))
    p_user=np.concatenate((bg_p,[partial],native_p))
    def extend(x):
        xx=ref[x]
        partial_v=float(np.interp(np.log(partial),np.log(ref['p']),xx))
        return np.concatenate((xx[:max(ip-1,0)],[partial_v],native_t if x=='t' else native_q_moist))
    t_user=extend('t')
    q_user=extend('q')
    o3=np.interp(np.log(p_user),np.log(ref['p']),ref['o3'])
    co2=np.interp(np.log(p_user),np.log(ref['p']),ref['co2'])
    p_half=np.concatenate((bg_half[:-1],native_half))
    return p_user,p_half,t_user,q_user,o3,co2

def p8w_for_columns(ds,ids,nx,ny):
    # Port of the source-backed REAL(4) phy_prep P8W interpolation/extrapolation.
    ij=np.asarray(ids,dtype=np.int64); jj=ij//nx; ii=ij%nx
    p=(ds['P'][:,jj,ii]+ds['PB'][:,jj,ii]).astype(np.float32).T
    ph=ds['PH'][:,jj,ii].astype(np.float32).T
    phb=ds['PHB'][:,jj,ii].astype(np.float32).T
    zw=(ph+phb)/np.float32(9.81); zm=np.float32(0.5)*(zw[:,:-1]+zw[:,1:])
    znw=ds['ZNW'].astype(np.float32); dnw=znw[1:]-znw[:-1]
    dn=np.float32(0.5)*(dnw[1:]+dnw[:-1])
    fnm=np.zeros(39,dtype=np.float32); fnp=np.zeros(39,dtype=np.float32)
    fnm[1:39]=np.float32(0.5)*dnw[:-1]/dn
    fnp[1:39]=np.float32(0.5)*dnw[1:]/dn
    out=np.zeros((len(ids),40),dtype=np.float32)
    out[:,1:39]=fnm[1:39]*p[:,1:39]+fnp[1:39]*p[:,:38]
    w1=(zw[:,0]-zm[:,1])/(zm[:,0]-zm[:,1]); w2=np.float32(1)-w1
    out[:,0]=w1*p[:,0]+w2*p[:,1]
    w1=(zw[:,-1]-zm[:,-2])/(zm[:,-1]-zm[:,-2]); w2=np.float32(1)-w1
    out[:,-1]=np.exp(w1*np.log(p[:,-1])+w2*np.log(p[:,-2]))
    return out

def gas_q_moist(qv):
    # Existing builder mapping for model kg/kg dry to RTTOV gas_units=2 ppmv moist.
    w=np.maximum(np.asarray(qv,dtype=np.float64),0.)
    num=w/0.01801528
    return 1.e6*num/(1./0.0289647+num)

def prep_one(frame, raw, b, ref, saved=None):
    s=frame.state; f=frame.forcing
    t=(s.th*f.pii).numpy()[b]
    q=gas_q_moist(s.qv.numpy()[b])
    p=(f.p.numpy()[b]/100.)
    # Single-column P8W uses same vectorized REAL(4) reconstruction as the census.
    p8w=p8w_for_columns(raw,[b],frame.meta['nx'],frame.meta['ny'])[0]
    ext=profile_extended(t,q,p,p8w.astype(np.float64)/100.0,ref)
    return p8w,ext

def checked_profile(fn,pc,tmin,tmax,limits, ext, p_surface):
    p,p_half,t,q,o3,co2=ext
    values=np.asfortranarray(np.column_stack((t,q,o3,co2)),dtype=np.float64)
    mapped_array=np.zeros((len(pc),4),dtype=np.float64,order='F')
    start=np.zeros(len(pc),dtype=np.int32); end=np.zeros(len(pc),dtype=np.int32)
    fn(len(pc),len(p),np.ascontiguousarray(pc),np.ascontiguousarray(p),values,mapped_array,start,end)
    mapped={'T':mapped_array[:,0].copy(),'Water_vapour':mapped_array[:,1].copy(),
            'Ozone':mapped_array[:,2].copy(),'CO2':mapped_array[:,3].copy()}
    nlayer=len(pc)
    # Source rttov_check_reg_limits lay_lower (surface) and lay_upper (top extrapolation exclusion).
    lay_lower=nlayer
    for k in range(nlayer,1,-1):
        if pc[k-2] < p_surface: break
    else: k=1
    lay_lower=k
    if nlayer>1 and pc[1] < p[0]:
        lay_upper=nlayer
        for k in range(3,nlayer+1):
            if pc[k-1] > p[0]:
                lay_upper=k; break
    else: lay_upper=1
    lo=lay_upper-1; hi=lay_lower
    failures={}
    for name,x in mapped.items():
        mn,mx=(tmin,tmax) if name=='T' else limits[name]
        bad=(x[lo:hi]<mn[lo:hi]) | (x[lo:hi]>mx[lo:hi])
        failures[name]=np.flatnonzero(bad)+lay_upper
    return not any(v.size for v in failures.values()), failures, mapped, (lay_upper,lay_lower)

def main():
    if not RULE.exists(): raise FileNotFoundError(f'Frozen v4 rule missing: {RULE}')
    rule=json.loads(RULE.read_text()); in_receipt=json.loads(INPUT_RECEIPT.read_text())
    if rule['rule_id']!='C5_RTTOV_COEFFICIENT_PROFILE_SUPPORT_V4_SEA_IREMIS': raise ValueError('unexpected frozen rule')
    if sha(COEF)!=rule['source_data']['coefficient_sha256']: raise ValueError('coefficient hash changed')
    if sha(FORECAST)!=rule['source_data']['forecast_sha256']: raise ValueError('forecast hash changed')
    if sha(INPUT_RECEIPT)!=rule['source_data']['input_census_sha256']: raise ValueError('input census receipt hash changed')
    if sha(INPUT_NPZ)!=rule['source_data']['original_selected_npz_sha256']: raise ValueError('original selected input NPZ hash changed')
    phalf,pcoef,tmin,tmax,limits,names=parse_coef(); ref=load_reference()
    sys_path=str(REPO)
    import sys
    if sys_path not in sys.path: sys.path.insert(0,sys_path)
    from oracle.kdm6.io.frame_reader import read_wrfout_frame
    counts=[]; selected=[]; saved=np.load(PREPARED_NPZ); saved_in=np.load(INPUT_NPZ)
    # Check exact model/native source and selected-profile preparation before census claims.
    with netCDF4.Dataset(FORECAST) as ds, tempfile.TemporaryDirectory(prefix='c5support-') as td:
        raw_by_time={ti:{name:np.asarray(ds[name][ti],dtype=np.float32) for name in ('P','PB','PH','PHB')} | {'ZNW':np.asarray(ds['ZNW'][ti],dtype=np.float32)} for ti in TIMES}
        fn,helper_src_sha,helper_bin_sha,helper_archive_sha,helper_compiler,helper_sdk=compile_weights(Path(td))
        frame1=read_wrfout_frame(str(FORECAST),time_idx=1,nccn_policy='as_stored')
        bsel=100*frame1.meta['nx']+70
        if not np.array_equal(np.stack([getattr(frame1.state,k).numpy() for k in ('th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg')])[:,bsel],saved['native_state_bottom_up']): raise ValueError('selected native State parity failed')
        native_state=np.stack([getattr(frame1.state,k).numpy() for k in ('th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg')])[:,bsel]
        native_forcing=np.stack([getattr(frame1.forcing,k).numpy() for k in ('rho','pii','p','delz')])[:,bsel]
        if not np.array_equal(native_state,saved['native_state_bottom_up']): raise ValueError('selected native State parity failed')
        if not np.array_equal(native_forcing,saved['native_forcing_bottom_up']): raise ValueError('selected native Forcing parity failed')
        if not np.array_equal(native_state,saved_in['state']) or not np.array_equal(native_forcing,saved_in['forcing']): raise ValueError('selected frozen input NPZ parity failed')
        p8w,ext=prep_one(frame1,raw_by_time[1],bsel,ref)
        if not np.array_equal(p8w,saved['native_p8w_real4_Pa']): raise ValueError('selected P8W parity failed')
        p,p_half,t,q,o3,co2=ext
        for key,got in [('extended_p_center_hPa',p),('extended_p_half_hPa',p_half),('extended_temperature_K',t),('extended_q_ppmv_moist',q),('extended_o3_reference',o3),('extended_co2_reference',co2)]:
            if not np.array_equal(got,saved[key]): raise ValueError(f'selected prepared parity failed: {key}; maxdiff={np.max(np.abs(got-saved[key]))}')
        parity={'selected_native_state_forcing_exact':True,'selected_P8W_REAL4_exact':True,'selected_extended_profile_exact':True}
        for time_idx in TIMES:
            frame=read_wrfout_frame(str(FORECAST),time_idx=time_idx,nccn_policy='as_stored')
            nx,ny=frame.meta['nx'],frame.meta['ny']; B=nx*ny
            state=frame.state; forcing=frame.forcing
            st=np.stack([getattr(state,k).numpy() for k in ('th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg')])
            fo=np.stack([getattr(forcing,k).numpy() for k in ('rho','pii','p','delz')])
            xland=frame.xland.numpy()
            lm=np.asarray(ds['LANDMASK'][time_idx,:,:],dtype=np.float64).reshape(-1)
            seaice=np.asarray(ds['SEAICE'][time_idx,:,:],dtype=np.float64).reshape(-1)
            interior=np.zeros(B,dtype=bool); interior.reshape(ny,nx)[1:-1,1:-1]=True
            finite=np.all(np.isfinite(st),axis=(0,2)) & np.all(np.isfinite(fo),axis=(0,2))
            numerical=finite & np.all(st[0]>0,axis=1) & np.all(st[1:]>=0,axis=(0,2)) & np.all(fo>0,axis=(0,2))
            pair_pass=np.ones(B,dtype=bool)
            for mi,ni in ((2,8),(3,10),(4,9),(6,11)):
                m=st[mi]; n=st[ni]
                pair_pass &= np.all((m>=0)&(n>=0)&((m==0)==(n==0)),axis=1)
            dryrho=fo[0]/(1.+st[1])
            active=np.any((st[2]>EPS_QC)&(dryrho*st[8]>(10.0)),axis=1)
            sea=(xland>=1.5)&(lm==0)&(seaice==0)
            land=xland<1.5
            strict_active=interior&numerical&pair_pass&active
            candidate=np.flatnonzero(interior&numerical&pair_pass&active&sea)
            p8w=p8w_for_columns(raw_by_time[time_idx],candidate,nx,ny)
            passed=[]; failures={k:0 for k in ('T','Water_vapour','Ozone','CO2')}; violation_layers={k:np.zeros(len(pcoef),dtype=np.int64) for k in failures}
            for b,p8 in zip(candidate,p8w):
                t=(state.th.numpy()[b]*forcing.pii.numpy()[b]).copy()
                q=gas_q_moist(state.qv.numpy()[b])
                p=forcing.p.numpy()[b]/100.
                x=profile_extended(t,q,p,p8.astype(np.float64)/100.0,ref)
                ok,bad,mapped,krange=checked_profile(fn,pcoef,tmin,tmax,limits,x,float(p8[0])/100.)
                if ok:
                    qc_sum=0.0
                    for v in st[2,b]: qc_sum+=float(v)
                    j,i=divmod(int(b),nx)
                    passed.append((qc_sum,j+1,i+1,int(b),x,krange,st[:,b].copy(),fo[:,b].copy(),float(xland[b]),dryrho[b].copy(),p8.copy()))
                else:
                    for key,ids in bad.items():
                        if ids.size:
                            failures[key]+=1
                            violation_layers[key][ids-1]+=1
            passed.sort(key=lambda a:(a[0],a[1],a[2]))
            rec={'time_index_zero_based':time_idx,'valid_time':str(frame.meta.get('valid_time_utc',f'frame{time_idx}')),
                 'owned_interior':int(interior.sum()),'numeric_pass':int(np.count_nonzero(interior&numerical)),
                 'strict_pair_pass':int(np.count_nonzero(interior&numerical&pair_pass)),
                 'active_liquid_before_pair_filter':int(np.count_nonzero(interior&numerical&active)),
                 'sea_iremis_scope_pass_before_state_gates':int(np.count_nonzero(interior&sea)),
                 'strict_active_sea_liquid_candidates':len(candidate),'coefficient_domain_pass':len(passed),
                 'candidate_rejected_profiles_by_any_field':len(candidate)-len(passed),
                 'profiles_with_layer_violation_by_field':failures,
                 'violation_counts_by_coef_layer':{k:v.tolist() for k,v in violation_layers.items()},
                 'land_columns_xland_lt_1_5':int(np.count_nonzero(interior&land)),
                 'strict_active_liquid_land_profiles_excluded_by_sea_scope':int(np.count_nonzero(strict_active&land)),
                 'strict_active_liquid_sea_columns_rejected_surface_mismatch':int(np.count_nonzero(strict_active&(xland>=1.5)&~sea)),
                 'surface_scope_note':'WRF output is one full-domain field; no tile-owner ID is serialized. Counts are global owned interior plus explicit sea/land/surface-mismatch splits.',
                 'selected':False}
            counts.append(rec)
            for c in passed:
                qc_sum,j,i,b,x,krange,state_raw,forcing_raw,xland_raw,rho_dry_raw,p8raw=c
                selected.append((time_idx,qc_sum,j,i,b,x,krange,state_raw,forcing_raw,xland_raw,rho_dry_raw,p8raw))
            print(f"frame={time_idx} candidates={len(candidate)} coefficient_pass={len(passed)} field_profile_failures={failures}",flush=True)
        # Earliest frame with passing support; median by qc sum then row-major j,i.
        chosen_frame=next((ti for ti in TIMES if any(x[0]==ti for x in selected)),None)
        if chosen_frame is None:
            out={'schema':'C5_RTTOV_COEFFICIENT_SUPPORT_CENSUS_V2','status':'NO_CANDIDATE_PASSES_FROZEN_V4_INPUT_ONLY_GATE_V2','script_sha256':sha(Path(__file__)),'census_script_path':str(Path(__file__)),'rule_id':rule['rule_id'],'rule_sha256':sha(RULE),'input_census_sha256':sha(INPUT_RECEIPT),'forecast_sha256':sha(FORECAST),'coefficient_sha256':sha(COEF),'rttov_layeravg_helper_source_sha256':helper_src_sha,'rttov_layeravg_helper_binary_sha256':helper_bin_sha,'rttov_layeravg_archive_path':str(RTTOV/'lib/librttov14_main.a'),'rttov_layeravg_archive_sha256':helper_archive_sha,'helper_compiler':helper_compiler,'helper_sdk':helper_sdk,'helper_build_commands':[f'gfortran -I{RTTOV}/include -I{RTTOV}/mod -c <tmp>/rttov_weights.F90 -o <tmp>/rttov_weights.o',f'gfortran -dynamiclib -Wl,-syslibroot,{helper_sdk} -I{RTTOV}/include -I{RTTOV}/mod <tmp>/rttov_weights.o {RTTOV}/lib/librttov14_main.a -o <tmp>/rttov_weights.dylib'],'rttov_layeravg_archive_path':str(RTTOV/'lib/librttov14_main.a'),'rttov_layeravg_archive_sha256':helper_archive_sha,'rttov_layeravg_helper_source':F90,'helper_compiler':helper_compiler,'helper_sdk':helper_sdk,'helper_build_commands':[f'gfortran -I{RTTOV}/include -I{RTTOV}/mod -c <tmp>/rttov_weights.F90 -o <tmp>/rttov_weights.o',f'gfortran -dynamiclib -Wl,-syslibroot,{helper_sdk} -I{RTTOV}/include -I{RTTOV}/mod <tmp>/rttov_weights.o {RTTOV}/lib/librttov14_main.a -o <tmp>/rttov_weights.dylib'],'frame_counts':counts,'output_partition':{'wrf_numtiles':in_receipt['namelist']['numtiles'],'note':'The serialized WRF history is one full-domain field and does not preserve per-tile owner IDs; report domain and land/sea counts.'},'selection':{'selected':False},'no_rttov_output_called':True}
            path=EVIDENCE/'c5_rttov_coefficient_support_census_v2_20261003.json'; path.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n'); print('no candidate; receipt',path,'sha256',sha(path)); return
        pool=sorted([x for x in selected if x[0]==chosen_frame],key=lambda a:(a[1],a[2],a[3]))
        chosen=pool[len(pool)//2]; ti,score,j,i,b,ext,krange,state_raw,forcing_raw,xland_raw,rho_dry_raw,p8raw=chosen
        next(c for c in counts if c['time_index_zero_based']==ti)['selected']=True
        nbg=len(ext[0])-NATIVE_K
        np.savez_compressed(EVIDENCE/'c5_rttov_coefficient_support_selected_v2_20261003.npz',
             time_index=np.int64(ti),global_j_1based=np.int64(j),global_i_1based=np.int64(i),xland=np.float64(xland_raw),
             input_sum_qc=np.float64(score),state=state_raw,forcing=forcing_raw,rho_dry=rho_dry_raw,
             native_p8w_real4_Pa=p8raw,native_background_mask=np.concatenate((np.ones(nbg,dtype=np.uint8),np.zeros(NATIVE_K,dtype=np.uint8))),
             pressure_hPa=ext[0],pressure_half_hPa=ext[1],temperature_K=ext[2],q_ppmv_moist=ext[3],o3_ppmv_moist=ext[4],co2_ppmv_moist=ext[5],checked_layers=np.array(krange,dtype=np.int32))
        out={'schema':'C5_RTTOV_COEFFICIENT_SUPPORT_CENSUS_V2','status':'INPUT_ONLY_SUPPORT_CENSUS_V2_COMPLETE_NO_RTTOV_OUTPUTS','script_sha256':sha(Path(__file__)),'census_script_path':str(Path(__file__)),
             'rule_id':rule['rule_id'],'rule_sha256':sha(RULE),'input_census_sha256':sha(INPUT_RECEIPT),'forecast_sha256':sha(FORECAST),
             'coefficient_sha256':sha(COEF),'rttov_layeravg_helper_source_sha256':helper_src_sha,'rttov_layeravg_helper_binary_sha256':helper_bin_sha,'rttov_layeravg_archive_path':str(RTTOV/'lib/librttov14_main.a'),'rttov_layeravg_archive_sha256':helper_archive_sha,'helper_compiler':helper_compiler,'helper_sdk':helper_sdk,'helper_build_commands':[f'gfortran -I{RTTOV}/include -I{RTTOV}/mod -c <tmp>/rttov_weights.F90 -o <tmp>/rttov_weights.o',f'gfortran -dynamiclib -Wl,-syslibroot,{helper_sdk} -I{RTTOV}/include -I{RTTOV}/mod <tmp>/rttov_weights.o {RTTOV}/lib/librttov14_main.a -o <tmp>/rttov_weights.dylib'],
             'rttov_layeravg_helper_source':F90,'rttov_layeravg_call':'map_profiles(ncoef,nuser,pcoef,puser,values,mapped,starts,ends): values is F-contiguous [nuser,4] as T/Qmoist/O3moist/CO2moist; mapped is F-contiguous [ncoef,4]. It invokes installed rttov_layeravg mode4, applies RTTOV jprv moist-to-dry factor to Q/O3/CO2, then uses Fortran SUM over returned start:end bounds.',
             'profile_preparation_exactness':parity,'enabled_fields_checked':['T','Q','O3','CO2'],'gas_units':'Q/O3/CO2 ppmv moist, common source factor to dry before exact layer averaging; T K',
             'coefficient_domain':'v13 PROFILE_ENVELOPE adjacent-level average, default T scales +/-10%, gas scales +/-20%; exact coefficient centers, source Rochon helper; exact source layer bounds.',
             'census_scope':'input-only strict active liquid AND XLAND>=1.5 LANDMASK=0 SEAICE=0 (sea/IREMIS); no radiance, BT, FD, K or ReturnQuality consulted. The raw WRF history is full-domain and has no tile-owner IDs; frame and land/sea profile counts are reported.',
             'frame_counts':counts,'output_partition':{'wrf_numtiles':in_receipt['namelist']['numtiles'],'note':'The serialized WRF history is one full-domain field and does not preserve per-tile owner IDs; report domain and land/sea counts.'},'state_order':['th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg'],'forcing_order':['rho','pii','p','delz'],'selection':{'selected':True,'time_index_zero_based':ti,'valid_time_utc':next(c['valid_time'] for c in counts if c['time_index_zero_based']==ti),'global_j_1based':j,'global_i_1based':i,'xland':xland_raw,'sum_qc':score,'passing_profiles_in_selected_frame':len(pool),'median_index_zero_based':len(pool)//2,'rank_rule':'earliest frame with support; median of ascending sequential-f64 sum(qc), tie row-major (j,i)'},
             'limitations':['This gate does not screen the Delta-Eddington 20 km^-1 bit15; later RTTOV quality flags must remain unmodified.',
                            'Input gate does not certify physical S2 number calibration, observation agreement, or radiative accuracy.',
                            'Fortran SUM is replayed at source level by a gfortran wrapper; it is not asserted bitwise identical to the installed RTTOV object build. Later actual ReturnQuality remains decisive.',
                            'No RTTOV executable or radiance/K/FD was invoked by this script.'],
             'source_hashes':{'reader':sha(REPO/'oracle/kdm6/io/frame_reader.py'),'model_profile_builder':sha(REPO/'oracle/kdm6/obs/model_profile_builder.py'),'rttov_convert_profile_units':sha(RTTOV/'src/main/rttov_convert_profile_units.F90'),'rttov_intavg_prof':sha(RTTOV/'src/main/rttov_intavg_prof.F90'),'rttov_layeravg':sha(RTTOV/'src/main/rttov_layeravg.F90'),'rttov_check_reg_limits':sha(RTTOV/'src/main/rttov_check_reg_limits.F90'),'rttov_read_ascii_coef':sha(RTTOV/'src/coef_io/rttov_read_ascii_coef.F90'),'rttov_init_coef':sha(RTTOV/'src/coef_io/rttov_init_coef.F90'),'rttov_reference_profile_t':sha(REF/'t.txt'),'rttov_reference_profile_q':sha(REF/'q.txt'),'rttov_reference_profile_o3':sha(REF/'o3.txt'),'rttov_reference_profile_co2':sha(REF/'co2.txt'),'rttov_reference_profile_p':sha(REF/'p.txt'),'rttov_reference_profile_p_half':sha(REF/'p_half.txt'),'host_phy_prep':sha(Path('/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/dyn_em/module_big_step_utilities_em.F')),'host_initialize_real':sha(Path('/Users/yhlee/KDM6AD-k/host/KIM-meso_v1.0/dyn_em/module_initialize_real.F'))},
             'selected_profile_npz':'c5_rttov_coefficient_support_selected_v2_20261003.npz','output_npz_sha256':sha(EVIDENCE/'c5_rttov_coefficient_support_selected_v2_20261003.npz')}
        path=EVIDENCE/'c5_rttov_coefficient_support_census_v2_20261003.json'; path.write_text(json.dumps(out,indent=2,allow_nan=False)+'\n')
        print(json.dumps(out['selection'],indent=2))
        print('receipt',path,'sha256',sha(path))
if __name__=='__main__': main()
