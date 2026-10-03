#!/usr/bin/env python3
"""Prepare only the frozen C5 native column and input case; this script never runs RTTOV."""
from pathlib import Path
import hashlib, json, math, shutil, subprocess
import numpy as np
import torch
from netCDF4 import Dataset
from oracle.kdm6.state import State, Forcing
from oracle.kdm6.io.frame_reader import read_wrfout_frame
from oracle.kdm6.obs.gk2a_l1b import ko_grid_latlon, EARTH_RADIUS_M
from oracle.kdm6.obs.model_profile_builder import (
    RttovProfileConfig, model_to_rttov_tensors, qv_to_q_ppmv_moist,
)
from oracle.kdm6.obs.rttov_input_builder import RttovInput, RttovInputConfig
from oracle.kdm6.obs.rttov_case_writer import (
    _overlay_geometry, _overlay_surface,
    _validate_geometry, _validate_surface, write_rttov_case,
)

BASE = Path('/private/tmp/KDM6AD-c5-native39-prepared-2026-10-03')
NEW = Path('/private/tmp/KDM6AD-c5-native39-sea-supported-retry1-20261003')
SELECTED = BASE / 'evidence/c5_rttov_coefficient_support_selected_v2_20261003.npz'
CENSUS = BASE / 'evidence/c5_rttov_coefficient_support_census_v2_20261003.json'
RULE = BASE / 'evidence/c5_rttov_coefficient_support_rule_v4_sea_iremis_20261003.json'
FORECAST = Path('/private/tmp/KDM6AD-nccn-zero-merge603ea4a-host-confirm/case/runs/mp337_merge603ea4a_off_0min40s_hist0_20261003_102038_p26153/klfs_lc05_fcst.202507190000')
SOURCE_TEMPLATE = BASE / 'case_template'
L1B = Path('/Users/yhlee/KDM6AD-k/GK2A/00/gk2a_ami_le1b_ir105_ko020lc_202507190000.nc')
CHANNELS = tuple(range(8,17))

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def unused_solar_angle_defaults():
    # Active coefficient channels 8-16 are type-0 thermal-only and rt_all%solar is FALSE.
    # RTTOV's profile initializer defaults both unconsumed solar angles to zero.
    return 0.0,0.0

def view_angles(lat,lon):
    a=6378137.;b=6356752.31414;r=42164000.;slon=math.radians(128.2)
    phi=math.radians(lat);lam=math.radians(lon);e2=1-b*b/(a*a);N=a/math.sqrt(1-e2*math.sin(phi)**2)
    ground=np.array([N*math.cos(phi)*math.cos(lam),N*math.cos(phi)*math.sin(lam),N*(1-e2)*math.sin(phi)])
    sat=np.array([r*math.cos(slon),r*math.sin(slon),0.]);los=sat-ground
    east=np.array([-math.sin(lam),math.cos(lam),0.]);north=np.array([-math.sin(phi)*math.cos(lam),-math.sin(phi)*math.sin(lam),math.cos(phi)])
    up=np.array([math.cos(phi)*math.cos(lam),math.cos(phi)*math.sin(lam),math.sin(phi)])
    zen=math.degrees(math.acos(float(np.dot(los,up)/np.linalg.norm(los))))
    az=math.degrees(math.atan2(float(np.dot(los,east)),float(np.dot(los,north)))%(2*math.pi))
    return zen,az

def main():
    if NEW.exists(): raise FileExistsError(str(NEW))
    census=json.loads(CENSUS.read_text())
    if census['selection']['time_index_zero_based']!=1 or census['selection']['global_i_1based']!=73 or census['selection']['global_j_1based']!=157:
        raise ValueError('v2 input winner changed; stop and re-review before preparing')
    d=np.load(SELECTED);ti=int(d['time_index']);i=int(d['global_i_1based']);j=int(d['global_j_1based']);nx=234;b=(j-1)*nx+i-1
    state_bottom=np.asarray(d['state'],dtype=np.float64);forcing_bottom=np.asarray(d['forcing'],dtype=np.float64);rho_bottom=np.asarray(d['rho_dry'],dtype=np.float64);xland=float(d['xland'])
    frame=read_wrfout_frame(str(FORECAST),time_idx=ti,nccn_policy='as_stored')
    state_order=('th','qv','qc','qr','qi','qs','qg','nccn','nc','ni','nr','bg')
    forcing_order=('rho','pii','p','delz')
    frame_state=np.stack([getattr(frame.state,n).numpy() for n in state_order],axis=0)[:,b]
    frame_forcing=np.stack([getattr(frame.forcing,n).numpy() for n in forcing_order],axis=0)[:,b]
    if not np.array_equal(frame_state,state_bottom):raise ValueError('selected State differs from same-frame frame_reader')
    if not np.array_equal(frame_forcing,forcing_bottom):raise ValueError('selected Forcing differs from same-frame frame_reader')
    if float(frame.xland[b])!=xland:raise ValueError('selected XLAND differs from same-frame frame_reader')
    if not np.array_equal(frame_forcing[0]/(1.0+frame_state[1]),rho_bottom):raise ValueError('selected frozen rho_dry differs from the exact source formula')
    state=State(*(torch.as_tensor(state_bottom[k,::-1].copy(),dtype=torch.float64) for k in range(12)))
    forcing=Forcing(*(torch.as_tensor(forcing_bottom[k,::-1].copy(),dtype=torch.float64) for k in range(4)))
    rho_top=torch.as_tensor(rho_bottom[::-1].copy(),dtype=torch.float64);xland_t=torch.as_tensor([xland],dtype=torch.float64)
    pcfg=RttovProfileConfig(gas_units=2,qv_convention='mixing_ratio_kgkg_dry',cloud=True,rho_d=rho_top,dry_number=True)
    model=model_to_rttov_tensors(state,forcing,pcfg,xland=xland_t,ncmin_land=10.,ncmin_sea=10.)
    native_t=np.asarray(d['temperature_K'],dtype=np.float64)[-39:];native_q=np.asarray(d['q_ppmv_moist'],dtype=np.float64)[-39:]
    if not np.array_equal(model.t_lay.detach().numpy(),native_t):raise ValueError('native T builder mismatch')
    if not np.array_equal(model.q_lay.detach().numpy(),native_q):raise ValueError('native Q builder mismatch')
    clw=model.clw.detach().numpy();ciw=model.ciw.detach().numpy();dl=model.deff_liq.detach().numpy();di=model.deff_ice.detach().numpy();cf=model.cfrac.detach().numpy()
    nbg=int(np.asarray(d['native_background_mask']).sum())
    h6=np.r_[np.zeros(nbg),clw];h7=np.r_[np.zeros(nbg),ciw];d6=np.r_[np.zeros(nbg),dl];d7=np.r_[np.zeros(nbg),di];cfrac=np.r_[np.zeros(nbg),cf]
    prof={'T':np.asarray(d['temperature_K'],dtype=np.float64)[None,:],'Q':np.asarray(d['q_ppmv_moist'],dtype=np.float64)[None,:],
          'P':np.asarray(d['pressure_hPa'],dtype=np.float64)[None,:],'P_HALF':np.asarray(d['pressure_half_hPa'],dtype=np.float64)[None,:],
          'HYDRO6':h6[None,:],'HYDRO7':h7[None,:],'HYDRO_DEFF6':d6[None,:],'HYDRO_DEFF7':d7[None,:],'CFRAC':cfrac[None,:]}
    with Dataset(FORECAST) as f:
        def cell(name):return float(f.variables[name][ti,j-1,i-1])
        required=('TSK','PSFC','T2','Q2','U10','V10','XLAND','SEAICE','HGT','LANDMASK')
        missing=[k for k in required if k not in f.variables]
        if missing:raise KeyError(f'required same-frame surface fields missing: {missing}')
        optional=('LU_INDEX','IVGTYP','ISLTYP','SST')
        surf={k:cell(k) for k in required}
        surf.update({k:(cell(k) if k in f.variables else None) for k in optional})
        wrflat=float(f.variables['XLAT'][ti,j-1,i-1]);wrflon=float(f.variables['XLONG'][ti,j-1,i-1])
    if surf['XLAND']<1.5 or surf['LANDMASK']!=0. or surf['SEAICE']!=0.:raise ValueError('v2 winner outside frozen sea/IREMIS scope')
    with Dataset(L1B) as f: attrs={k:getattr(f,k) for k in f.ncattrs()}
    latgrid,longrid=ko_grid_latlon(attrs)
    lat0=math.radians(wrflat);lon0=math.radians(wrflon);latr=np.radians(latgrid);lonr=np.radians(longrid)
    dlat=latr-lat0;dlon=(lonr-lon0+np.pi)%(2*np.pi)-np.pi
    hav=np.sin(dlat/2)**2+np.cos(lat0)*np.cos(latr)*np.sin(dlon/2)**2
    dist=2*EARTH_RADIUS_M*np.arcsin(np.sqrt(np.minimum(hav,1.)))
    row,col=np.unravel_index(int(np.argmin(dist)),dist.shape);pixlat=float(latgrid[row,col]);pixlon=float(longrid[row,col]);distance_km=float(dist[row,col]/1000.)
    zen,az=view_angles(pixlat,pixlon);sunzen,sunaz=unused_solar_angle_defaults()
    q2=float(qv_to_q_ppmv_moist(torch.as_tensor(surf['Q2'],dtype=torch.float64),gas_units=2,qv_convention='mixing_ratio_kgkg_dry'))
    geom={'zenangle':zen,'azangle':az,'sunzenangle':sunzen,'sunazangle':sunaz,'latitude':pixlat,'longitude':pixlon,'elevation':surf['HGT']/1000.}
    surface={'skin':{'surftype':1,'watertype':1,'t':surf['TSK'],'salinity':0.,'foam_fraction':0.,'snow_fraction':0.,'fastem':[0.]*5},
       'near_surface':{'t2m':surf['T2'],'q2m':q2,'wind_u10m':surf['U10'],'wind_v10m':surf['V10'],'wind_fetch':0.}}
    _validate_geometry(geom,1);_validate_surface(surface,1,solar_enabled=False)
    cfg=RttovInputConfig(coef_id='rtcoef_gkompsat2_1_ami_o3co2.dat',channels=CHANNELS,gas_units=2,mmr_hydro=False,adk_bt=True,store_rad=True,surface=surface,geometry=geom)
    blob=json.dumps({'coef_id':cfg.coef_id,'channels':CHANNELS,'gas_units':2,'mmr_hydro':False,'adk_bt':True,'store_rad':True,'surface':surface,'geometry':geom},sort_keys=True,separators=(',',':')).encode()
    cfg_hash=hashlib.sha256(blob+b''.join(prof[k].tobytes() for k in sorted(prof))).hexdigest();rin=RttovInput(prof,cfg,cfg_hash,1,63)
    NEW.mkdir(parents=True);(NEW/'evidence').mkdir()
    npzpath=NEW/'evidence/c5_sea_iremis_selected_profile_20261003.npz'
    np.savez_compressed(npzpath,native_state_bottom_up=state_bottom,native_forcing_bottom_up=forcing_bottom,
      native_state_top_surface=state_bottom[:,::-1].copy(),native_forcing_top_surface=forcing_bottom[:,::-1].copy(),
      native_temperature_K=native_t,native_q_ppmv_moist=native_q,native_p_center_hPa=prof['P'][0][nbg:],
      native_p_half_hPa=prof['P_HALF'][0][nbg:],native_p8w_real4_Pa=d['native_p8w_real4_Pa'],
      native_rho_dry_top_surface=rho_top.numpy(),native_xland=np.float64(xland),native_liquid_content_g_m3=clw,native_ice_content_g_m3=ciw,
      native_deff_liquid_um=dl,native_deff_ice_um=di,native_cfrac=cf,extended_temperature_K=prof['T'][0],extended_q_ppmv_moist=prof['Q'][0],
      extended_p_center_hPa=prof['P'][0],extended_p_half_hPa=prof['P_HALF'][0],extended_o3_reference=d['o3_ppmv_moist'],
      extended_co2_reference=d['co2_ppmv_moist'],extended_hydro6_g_m3=h6,extended_hydro7_g_m3=h7,extended_hydro_deff6_um=d6,
      extended_hydro_deff7_um=d7,extended_cfrac=cfrac,native_mask=np.r_[np.zeros(nbg,dtype=np.uint8),np.ones(39,dtype=np.uint8)],
      above_model_top_background_mask=np.r_[np.ones(nbg,dtype=np.uint8),np.zeros(39,dtype=np.uint8)],
      clear_hydro_above_top_mask=np.r_[np.ones(nbg,dtype=np.uint8),np.zeros(39,dtype=np.uint8)],
      background_temperature_K=prof['T'][0][:nbg],background_q_ppmv_moist=prof['Q'][0][:nbg],
      background_p_center_hPa=prof['P'][0][:nbg],background_p_half_hPa=prof['P_HALF'][0][:nbg+1])
    fixture=NEW/'case_template';shutil.copytree(SOURCE_TEMPLATE,fixture);pd=fixture/'in/profiles/001';atm=pd/'atm'
    for fn,key in [('p.txt','P'),('p_half.txt','P_HALF'),('t.txt','T'),('q.txt','Q')]:np.savetxt(atm/fn,prof[key][0],fmt='%.17E')
    np.savetxt(atm/'o3.txt',d['o3_ppmv_moist'],fmt='%.17E');np.savetxt(atm/'co2.txt',d['co2_ppmv_moist'],fmt='%.17E')
    (pd/'datetime.txt').write_text('2025   7   19   0   0   0\n')
    (pd/'angles.txt').write_text('');_overlay_geometry(pd,geom)
    sfc=pd/'sfc/01';sfc.mkdir(parents=True,exist_ok=True)
    for fn in ('skin.txt','near_surface.txt'):(sfc/fn).write_text('')
    _overlay_surface(pd,surface)
    # Do not leave an executable runner in either review case.
    runner=fixture/'out/run.sh'
    if runner.exists():runner.unlink()
    opts=fixture/'out/rttov_test.txt';text=opts.read_text().replace('defn%nlevels                   = 70','defn%nlevels                   = 64');opts.write_text(text)
    staged=NEW/'prepared_case';write_rttov_case(rin,staged,fixture_case_dir=fixture,overwrite=False,solar_channels=())
    active=staged/'out/run.sh'
    if active.exists():active.unlink()
    # Exact native/grid/gas file verification after the existing writer round trip.
    sp=staged/'in/profiles/001/atm'
    checks={'p.txt':prof['P'][0],'p_half.txt':prof['P_HALF'][0],'t.txt':prof['T'][0],'q.txt':prof['Q'][0],
      'o3.txt':d['o3_ppmv_moist'],'co2.txt':d['co2_ppmv_moist']}
    for fn,expected in checks.items():
        if not np.array_equal(np.loadtxt(sp/fn),expected):raise ValueError(f'staged file mismatch {fn}')
    receipt={'status':'PREPARED_INPUTS_ONLY_PENDING_ROOT_REVIEW','engine_executed':False,'rttov_y_or_bt_evaluated':False,'native_fd_or_derivative_evaluated':False,
      'census_rule_id':json.loads(RULE.read_text())['rule_id'],'census_rule_sha256':sha(RULE),'census_receipt':str(CENSUS),'census_receipt_sha256':sha(CENSUS),
      'selected_npz':str(SELECTED),'selected_npz_sha256':sha(SELECTED),'profile_npz':str(npzpath),'profile_npz_sha256':sha(npzpath),
      'winner':{'time_index_zero_based':ti,'valid_time_utc':'2025-07-19_00:00:20','global_i_1based':i,'global_j_1based':j,'flat_b':b,'xland':xland,'sum_qc':float(d['input_sum_qc'])},
      'inputs':{'state_forcing_rho_dry_exact_selected_npz':True,'native_p8w_real4_exact_selected_npz':True,
        'native_profile_layers':39,'above_model_top_reference_layers':nbg,'layers':63,'interfaces':64,
        'rttov_profile_fields_P_P_HALF_T_Q_O3_CO2_exact_census_arrays':True,'ncmin_land':10.0,'ncmin_sea':10.0,
        'dry_number':True,'fixed_rho_dry':True,'gas_units':2,'mmr_hydro':False,'adk_bt':True,'store_rad':True},
      'observation':{'l1b_file':str(L1B),'l1b_sha256':sha(L1B),'pixel_row_zero_based':int(row),'pixel_column_zero_based':int(col),
        'pixel_latitude_deg':pixlat,'pixel_longitude_deg':pixlon,'wrf_cell_latitude_deg':wrflat,'wrf_cell_longitude_deg':wrflon,
        'nearest_pixel_distance_km':distance_km,'geometry_method':'nearest KO LCC geolocation from file metadata only; nominal GEO WGS84 ECEF line of sight; modeled nominal geometry, not measured ephemeris.',
        'view_zenith_deg':zen,'view_azimuth_deg_clockwise_from_north':az,'solar_zenith_deg':sunzen,'solar_azimuth_deg':sunaz,
        'solar_angles_consumed':False,'solar_angle_values_basis':'RTTOV initializer zero defaults; source-proved unconsumed because solar is disabled and channels 8-16 are thermal-only',
        'nominal_slot_utc':'2025-07-19 00:00:00','model_valid_time_utc':'2025-07-19 00:00:20','model_minus_slot_seconds':20,
        'nominal_orbit_primary_sources':['https://nmsc.kma.go.kr/resources/homepage/pdf/210428_GK2A_Fact_Sheets.pdf','https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf'],
        'nominal_orbit':{'sub_longitude_deg':128.2,'earth_center_radius_m':42164000.0,'wgs84_a_m':6378137.0,'wgs84_b_m':6356752.31414},
        'nominal_orbit_primary_sources':['https://nmsc.kma.go.kr/resources/homepage/pdf/210428_GK2A_Fact_Sheets.pdf','https://datasvc.nmsc.kma.go.kr/resources/common/pdf/%EC%B2%9C%EB%A6%AC%EC%95%88%EC%9C%84%EC%84%B1%202A%ED%98%B8%20%20%EC%9E%90%EB%A3%8C%ED%99%9C%EC%9A%A9%20QA.pdf'],
        'image_dn_or_bt_read':False},
      'number_optics':{'NC_native_nonzero_levels':int(np.count_nonzero(state_bottom[8]>0.0)),'NI_native_nonzero_levels':int(np.count_nonzero(state_bottom[9]>0.0)),
        'NC_range': [float(np.min(state_bottom[8])),float(np.max(state_bottom[8]))],
        'rho_dry_range_kg_m3':[float(np.min(rho_bottom)),float(np.max(rho_bottom))],
        'native_HYDRO6_content_g_m3_range':[float(np.min(clw)),float(np.max(clw))],
        'native_HYDRO7_content_g_m3_range':[float(np.min(ciw)),float(np.max(ciw))],
        'native_HYDRO_DEFF6_um_range':[float(np.min(dl)),float(np.max(dl))],
        'native_HYDRO_DEFF7_um_range':[float(np.min(di)),float(np.max(di))],
        'native_CFRAC_range':[float(np.min(cf)),float(np.max(cf))],
        'frozen_dry_number_basis':True,'ncmin_land_sea':10.0},
      'surface':{'same_c2_frame_surface':surf,'Q2_ppmv_moist':q2,'IREMIS':2,'sea_scope':{'XLAND':surf['XLAND'],'LANDMASK':surf['LANDMASK'],'SEAICE':surf['SEAICE']},
        'RTTOV_skin':surface['skin'],'RTTOV_near_surface':surface['near_surface'],
        'unused_initializer_fields':'salinity, foam_fraction, snow_fraction, FASTEM, wind_fetch remain initialized/unused for thermal-only IREMIS; no solar channels.'},
      'pressure_boundary':{'PSFC_Pa':surf['PSFC'],'p_half_bottom_Pa':float(d['native_p8w_real4_Pa'][0]),
        'difference_Pa':float(d['native_p8w_real4_Pa'][0])-surf['PSFC'],'native_reconstructed_P8W_preserved':True},
      'files':{'fixture':str(fixture),'prepared_case':str(staged),'channels':list(CHANNELS),'nlevels_namelist':64,
        'options_sha256':sha(staged/'out/rttov_test.txt'),'angles_sha256':sha(staged/'in/profiles/001/angles.txt'),
        'datetime_sha256':sha(staged/'in/profiles/001/datetime.txt'),'skin_sha256':sha(staged/'in/profiles/001/sfc/01/skin.txt'),
        'near_surface_sha256':sha(staged/'in/profiles/001/sfc/01/near_surface.txt')},
      'source':{'prep_script':str(Path(__file__)),'prep_script_sha256':sha(Path(__file__)),'writer_repo':str(Path('/private/tmp/KDM6AD-dry-number-optics')),
        'writer_head':subprocess.check_output(['git','-C','/private/tmp/KDM6AD-dry-number-optics','rev-parse','HEAD'],text=True).strip()},
      'limitations':['Root review required before RTTOV execution.','No BT/K/FD output was run for this new input.','Global S2 physical calibration remains distinct and open.',
        'This input-domain census excludes known T/Q/O3/CO2 coefficient-envelope failures; it does not predict all ReturnQuality bits, especially Delta-Eddington bit15.']}
    rc=NEW/'evidence/selected_profile_preparation_receipt_20261003.json';rc.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
    print('PREPARED',NEW,'winner',i,j,'pixel',row,col,'receipt sha',sha(rc),'BT/RT_NOT_RUN')

if __name__=='__main__':main()
