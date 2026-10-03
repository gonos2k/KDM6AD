"""Input-chosen chronological follow-up, same coordinate; no RTTOV evaluation."""
from pathlib import Path
import sys,importlib.util,shutil,json,hashlib
import numpy as np,torch
from netCDF4 import Dataset
sys.path.insert(0,'/private/tmp/KDM6AD-dry-number-optics')
from oracle.kdm6.io.frame_reader import read_wrfout_frame
from oracle.kdm6.state import State,Forcing
from oracle.kdm6.obs.model_profile_builder import RttovProfileConfig,model_to_rttov_tensors,qv_to_q_ppmv_moist
from oracle.kdm6.obs.rttov_case_writer import _overlay_surface,_overlay_geometry,_validate_surface
root=Path('/private/tmp/KDM6AD-entry-frame40-20261003');root.mkdir()
source=Path('/private/tmp/KDM6AD-dry-number-optics/harness/evidence/C5_coefficient_support_census_2026-10-03.py')
spec=importlib.util.spec_from_file_location('screen',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
fr=read_wrfout_frame(str(m.FORECAST),time_idx=2,nccn_policy='as_stored');b=156*fr.meta['nx']+72
s=np.stack([x.numpy()[b] for x in fr.state]);f=np.stack([x.numpy()[b] for x in fr.forcing]);rd=f[0]/(1+s[1])
assert np.isfinite(s).all() and (s[1:]>=0).all()
for mi,ni in ((2,8),(3,10),(4,9),(6,11)):assert ((s[mi]==0)==(s[ni]==0)).all()
with Dataset(m.FORECAST) as ds:
 raw={name:np.asarray(ds[name][2],dtype=np.float32) for name in ('P','PB','PH','PHB','ZNW')}
 p8=m.p8w_for_columns(raw,[b],fr.meta['nx'],fr.meta['ny'])[0]
 surface={name:float(ds[name][2,156,72]) for name in ('TSK','T2','Q2','U10','V10','HGT','XLAND','LANDMASK','SEAICE')}
 assert surface['XLAND']==2 and surface['LANDMASK']==surface['SEAICE']==0
ext=m.profile_extended(s[0]*f[1],m.gas_q_moist(s[1]),f[2]/100,p8.astype(np.float64)/100,m.load_reference())
top=State(*(torch.tensor(x[::-1].copy(),dtype=torch.float64) for x in s));fc=Forcing(*(torch.tensor(x[::-1].copy(),dtype=torch.float64) for x in f))
rho=torch.tensor(rd[::-1].copy(),dtype=torch.float64)
p=model_to_rttov_tensors(top,fc,RttovProfileConfig(2,'mixing_ratio_kgkg_dry',cloud=True,rho_d=rho,dry_number=True),xland=torch.tensor([2.]),ncmin_land=10,ncmin_sea=10)
nb=len(ext[0])-39;assert nb==24
with np.load('/private/tmp/KDM6AD-c5-native39-sea-supported-retry1-20261003/evidence/c5_sea_iremis_selected_profile_20261003.npz') as old:payload={k:old[k].copy() for k in old.files}
payload.update(native_state_bottom_up=s,native_forcing_bottom_up=f,native_state_top_surface=s[:,::-1].copy(),native_forcing_top_surface=f[:,::-1].copy(),native_rho_dry_top_surface=rd[::-1].copy(),native_p8w_real4_Pa=p8)
for key,v in zip(('extended_p_center_hPa','extended_p_half_hPa','extended_temperature_K','extended_q_ppmv_moist','extended_o3_reference','extended_co2_reference'),ext):payload[key]=v
for key,attr in (('hydro6_g_m3','clw'),('hydro7_g_m3','ciw'),('hydro_deff6_um','deff_liq'),('hydro_deff7_um','deff_ice'),('cfrac','cfrac')):payload['extended_'+key]=np.r_[np.zeros(nb),getattr(p,attr).numpy()]
for key,v in [('native_temperature_K',ext[2][nb:]),('native_q_ppmv_moist',ext[3][nb:]),('native_p_center_hPa',ext[0][nb:]),('native_p_half_hPa',ext[1][nb:]),('native_liquid_content_g_m3',p.clw.numpy()),('native_ice_content_g_m3',p.ciw.numpy()),('native_deff_liquid_um',p.deff_liq.numpy()),('native_deff_ice_um',p.deff_ice.numpy()),('native_cfrac',p.cfrac.numpy())]:payload[key]=v
for k,v in [('background_temperature_K',ext[2][:nb]),('background_q_ppmv_moist',ext[3][:nb]),('background_p_center_hPa',ext[0][:nb]),('background_p_half_hPa',ext[1][:nb+1])]:payload[k]=v
np.savez_compressed(root/'profile.npz',**payload)
fixture=root/'fixture';shutil.copytree('/private/tmp/KDM6AD-c5-dom32-fixture-20261003',fixture);pd=fixture/'in/profiles/001'
np.savetxt(pd/'atm/o3.txt',ext[4],fmt='%.16E');np.savetxt(pd/'atm/co2.txt',ext[5],fmt='%.16E')
skin={'surftype':1,'watertype':1,'t':surface['TSK'],'salinity':0.,'foam_fraction':0.,'snow_fraction':0.,'fastem':[0.]*5}
q2=float(qv_to_q_ppmv_moist(torch.tensor(surface['Q2'],dtype=torch.float64),gas_units=2,qv_convention='mixing_ratio_kgkg_dry'))
sfc={'skin':skin,'near_surface':dict(t2m=surface['T2'],q2m=q2,wind_u10m=surface['U10'],wind_v10m=surface['V10'],wind_fetch=0.)}
_validate_surface(sfc,1,solar_enabled=False);_overlay_surface(pd,sfc)
r={'selection':'fixed prior input-selected73,157; next chronological retained40s frame, before BT/FD','profile_sha256':hashlib.sha256((root/'profile.npz').read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'forecast_sha256':m.sha(m.FORECAST),'time_index':2,'global_i':73,'global_j':157,'surface':surface,'reference_bg_layers':nb,'native_levels':39,'radiance_evaluated':False,'scope':'fixed forcing20s KDM diagnostic; not native60s forecast; no observationcost approval'}
(root/'preexecution.json').write_text(json.dumps(r,indent=2)+'\n');print(root,r['profile_sha256'])
