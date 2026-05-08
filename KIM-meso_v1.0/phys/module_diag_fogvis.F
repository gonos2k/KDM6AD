!WRF:MEDIATION_LAYER:PHYSICS
MODULE module_diag_fogvis

  USE module_configure,         ONLY: grid_config_rec_type
  USE module_state_description, ONLY: P_QV, P_QC, P_QR, P_QI, P_QS, P_QG
  USE module_state_description, ONLY: P_qnc, F_qnc
  USE module_wrf_error
  IMPLICIT NONE

  PRIVATE
  PUBLIC :: diag_fogvis

  REAL, PARAMETER :: Rd   = 287.0
  REAL, PARAMETER :: Cp   = 1004.0
  REAL, PARAMETER :: p0   = 100000.0
  REAL, PARAMETER :: pi   = 3.141592653589793
  REAL, PARAMETER :: grav = 9.81

CONTAINS

  PURE REAL FUNCTION clamp(x,a,b)
    REAL, INTENT(IN) :: x,a,b
    clamp = MAX(a, MIN(b, x))
  END FUNCTION clamp

  PURE REAL FUNCTION sigmoid(x)
    REAL, INTENT(IN) :: x
    REAL :: y
    y = clamp(x, -40.0, 40.0)
    sigmoid = 1.0 / (1.0 + EXP(-y))
  END FUNCTION sigmoid

  PURE REAL FUNCTION esat_liq_pa(Tk)
    REAL, INTENT(IN) :: Tk
    REAL :: Tc
    Tc = Tk - 273.15
    esat_liq_pa = 611.2 * EXP( 17.67*Tc / (Tc + 243.5) )
  END FUNCTION esat_liq_pa

  PURE REAL FUNCTION qsat_liq(Tk, p_pa)
    REAL, INTENT(IN) :: Tk, p_pa
    REAL, PARAMETER :: eps = 0.622
    REAL :: es
    es = esat_liq_pa(Tk)
    es = MIN(es, 0.99*p_pa)
    qsat_liq = eps * es / (p_pa - es)
  END FUNCTION qsat_liq

  PURE REAL FUNCTION temp_from_theta(theta, p_pa)
    REAL, INTENT(IN) :: theta, p_pa
    REAL :: kappa
    kappa = Rd / Cp
    temp_from_theta = theta * (p_pa / p0) ** kappa
  END FUNCTION temp_from_theta

  PURE REAL FUNCTION rho_moist(p_pa, Tk, qv)
    REAL, INTENT(IN) :: p_pa, Tk, qv
    rho_moist = p_pa / ( Rd * Tk * (1.0 + 0.61*qv) )
  END FUNCTION rho_moist

  PURE REAL FUNCTION erfc_approx(x)
    REAL, INTENT(IN) :: x
    REAL :: ax, t, s
    REAL, PARAMETER :: a1=0.254829592, a2=-0.284496736, a3=1.421413741
    REAL, PARAMETER :: a4=-1.453152027, a5=1.061405429, p=0.3275911
    ax = ABS(x)
    t = 1.0 / (1.0 + p*ax)
    s = 1.0 - (((((a5*t + a4)*t + a3)*t + a2)*t + a1)*t) * EXP(-ax*ax)
    IF (x < 0.0) s = -s
    erfc_approx = 1.0 - s
  END FUNCTION erfc_approx

  PURE LOGICAL FUNCTION is_water_xland(xland)
    REAL, INTENT(IN) :: xland
    ! typical: XLAND ~ 1 land, 2 water
    is_water_xland = (xland > 1.5)
  END FUNCTION is_water_xland

  PURE SUBROUTINE beta_clw_from_lwc_nc( cfg, rho, qc, qnc, is_sea, beta_clw, nd_cm3, re_um )
    ! If qnc>0: Nc-based extinction from (LWC, Nc).
    ! Else: power-law fallback (+ optional diagnostic Nd scaling if enabled).
    TYPE(grid_config_rec_type), INTENT(IN) :: cfg
    REAL, INTENT(IN) :: rho, qc, qnc
    LOGICAL, INTENT(IN) :: is_sea
    REAL, INTENT(OUT) :: beta_clw, nd_cm3, re_um

    REAL :: LWC_kgm3, Nc_m3, rv_m, re_m
    REAL :: qext, rho_w, re_mult, re_min_um, re_max_um
    REAL :: lwc_gm3, Aclw_mult
    REAL :: nd_ref, nd_gamma, nd_use

    beta_clw = 0.0
    nd_cm3   = 0.0
    re_um    = 0.0

    LWC_kgm3 = MAX(0.0, rho * qc)
    Nc_m3    = MAX(0.0, rho * qnc)     ! qnc[#/kg] -> Nc[#/m3]

    qext      = cfg%fogvis_qext
    rho_w     = cfg%fogvis_rho_w
    re_mult   = cfg%fogvis_re_mult
    re_min_um = cfg%fogvis_re_min_um
    re_max_um = cfg%fogvis_re_max_um

    IF ( (qnc > 0.0) .AND. (LWC_kgm3 > 0.0) .AND. (Nc_m3 > 1.0e3) ) THEN
      rv_m = ( 3.0*LWC_kgm3 / (4.0*pi*rho_w*Nc_m3) ) ** (1.0/3.0)
      re_m = re_mult * rv_m
      re_um = clamp(re_m*1.0e6, re_min_um, re_max_um)
      re_m  = re_um * 1.0e-6
      beta_clw = qext * pi * re_m*re_m * Nc_m3     ! [1/m]
      nd_cm3   = Nc_m3 * 1.0e-6                    ! [cm^-3]
      RETURN
    ENDIF

    ! ---- fallback power-law (A in km^-1-like convention -> *1e-3) ----
    lwc_gm3 = rho * MAX(0.0, qc) * 1000.0
    Aclw_mult = 1.0
    IF (is_sea) Aclw_mult = cfg%fogvis_A_clw_sea_mult

    IF (lwc_gm3 > 0.0) THEN
      beta_clw = (cfg%fogvis_A_clw * Aclw_mult) * (lwc_gm3 ** cfg%fogvis_B_clw) * 1.0e-3
    ELSE
      beta_clw = 0.0
    ENDIF

    IF (cfg%fogvis_nd_opt /= 0) THEN
      nd_ref   = MAX(1.0, cfg%fogvis_nd_ref_cm3)
      nd_gamma = cfg%fogvis_nd_gamma
      IF (is_sea) THEN
        nd_use = MAX(1.0, cfg%fogvis_nd_sea_cm3)
      ELSE
        nd_use = MAX(1.0, cfg%fogvis_nd_land_cm3)
      ENDIF
      beta_clw = beta_clw * (nd_use / nd_ref) ** nd_gamma
    ENDIF
  END SUBROUTINE beta_clw_from_lwc_nc

  SUBROUTINE fog_layer_diag_ij( cfg, i, j, ims, ime, jms, jme, kms, kme, kts, kte, num_moist, num_scalar, xland_ij, &
                                p, pb, t, ph, phb, moist, scalar, &
                                fogmask_ij, fogbase_m_ij, fogtop_m_ij, fogdepth_m_ij )
    ! Optional: diagnose surface-based fog layer using PH/PHB.
    ! IMPORTANT: For fog layer detection, we IGNORE aerosol extinction to avoid haze->fog false positives.
    TYPE(grid_config_rec_type), INTENT(IN) :: cfg
    INTEGER, INTENT(IN) :: i, j, ims, ime, jms, jme, kms, kme, kts, kte, num_moist, num_scalar
    REAL, INTENT(IN) :: xland_ij
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme), INTENT(IN) :: p, pb, t
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme), INTENT(IN) :: ph, phb
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme, num_moist), INTENT(IN) :: moist
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme, num_scalar), INTENT(IN) :: scalar
    REAL, INTENT(OUT) :: fogmask_ij, fogbase_m_ij, fogtop_m_ij, fogdepth_m_ij

    INTEGER :: k, k_base, k_top
    INTEGER :: k_end, kstag_end
    LOGICAL :: is_sea, started, fog_here
    LOGICAL :: bad_z
    LOGICAL, SAVE :: logged_bounds = .FALSE.
    INTEGER, SAVE :: warn_count = 0
    REAL :: z_w_k, z_w_kp1, z_m, z_base, z_top
    REAL :: p_k, theta_k, Tk_k
    REAL :: qv_k, qc_k, qr_k, qi_k, qs_k, qg_k, qnc_k
    REAL :: rho, qsat_k, rh_k
    REAL :: beta_clw, beta_rain, beta_ice, beta_snow, beta_grau
    REAL :: beta_ext_fog, vis_k, ln1C, wc_gm3
    REAL :: nd_cm3_loc, re_um_loc
    CHARACTER(LEN=256) :: msg

    fogmask_ij    = 0.0
    fogbase_m_ij  = 0.0
    fogtop_m_ij   = 0.0
    fogdepth_m_ij = 0.0

    IF (cfg%fogvis_vlayer_opt == 0) RETURN

    ln1C    = LOG(1.0 / MAX(1.0e-6, cfg%fogvis_C_contrast))
    is_sea  = (cfg%fogvis_sea_mode /= 0) .AND. is_water_xland(xland_ij)

    k_end     = MIN(kte, UBOUND(p,2))
    kstag_end = MIN(kte+1, UBOUND(ph,2))

    IF (.NOT. logged_bounds) THEN
      WRITE(msg,'(A,2(I6,1X),A,2(I6,1X))') 'FOGVIS vlayer bounds p(k)=', &
           LBOUND(p,2), UBOUND(p,2), ' ph(k)=', LBOUND(ph,2), UBOUND(ph,2)
      CALL wrf_message(TRIM(msg))
      WRITE(msg,'(A,2(I6,1X),A,2(I6,1X))') 'FOGVIS vlayer bounds p(i)=', &
           LBOUND(p,1), UBOUND(p,1), ' p(j)=', LBOUND(p,3), UBOUND(p,3)
      CALL wrf_message(TRIM(msg))
      WRITE(msg,'(A,4(I6,1X))') 'FOGVIS vlayer kts/kte/k_end/kstag_end=', &
           kts, kte, k_end, kstag_end
      CALL wrf_message(TRIM(msg))
      logged_bounds = .TRUE.
    ENDIF

    IF (i < LBOUND(p,1) .OR. i > UBOUND(p,1) .OR. j < LBOUND(p,3) .OR. j > UBOUND(p,3)) THEN
      IF (warn_count < 20) THEN
        WRITE(msg,'(A,2(I6,1X),A,4(I6,1X))') 'FOGVIS vlayer ij out of bounds i/j=', &
             i, j, ' p(i/j) bounds=', LBOUND(p,1), UBOUND(p,1), LBOUND(p,3), UBOUND(p,3)
        CALL wrf_message(TRIM(msg))
      ENDIF
      warn_count = warn_count + 1
      RETURN
    ENDIF

    IF (kts < LBOUND(p,2) .OR. kte > UBOUND(p,2)) THEN
      IF (warn_count < 20) THEN
        WRITE(msg,'(A,2(I6,1X),A,2(I6,1X))') 'FOGVIS vlayer k out of bounds kts/kte=', &
             kts, kte, ' p(k) bounds=', LBOUND(p,2), UBOUND(p,2)
        CALL wrf_message(TRIM(msg))
      ENDIF
      warn_count = warn_count + 1
      RETURN
    ENDIF

    IF (k_end < kts .OR. kstag_end <= kts) THEN
      IF (warn_count < 20) THEN
        WRITE(msg,'(A,4(I6,1X))') 'FOGVIS vlayer k range invalid kts/kte/k_end/kstag_end=', &
             kts, kte, k_end, kstag_end
        CALL wrf_message(TRIM(msg))
      ENDIF
      warn_count = warn_count + 1
      RETURN
    ENDIF

    started = .FALSE.
    k_base  = -1
    k_top   = -1

    DO k = kts, k_end
      IF (k+1 > kstag_end) EXIT

      z_w_k   = (ph(i,k  ,j) + phb(i,k  ,j)) / grav
      z_w_kp1 = (ph(i,k+1,j) + phb(i,k+1,j)) / grav
      z_m     = 0.5 * (z_w_k + z_w_kp1)
      IF (z_m > cfg%fogvis_top_max_m) EXIT

      p_k     = p(i,k,j) + pb(i,k,j)
      theta_k = t(i,k,j) + 300.0
      Tk_k    = temp_from_theta(theta_k, p_k)

      qv_k = 0.0; qc_k = 0.0; qr_k = 0.0; qi_k = 0.0; qs_k = 0.0; qg_k = 0.0
      IF (P_QV>0 .AND. P_QV<=num_moist) qv_k = MAX(0.0, moist(i,k,j,P_QV))
      IF (P_QC>0 .AND. P_QC<=num_moist) qc_k = MAX(0.0, moist(i,k,j,P_QC))
      IF (P_QR>0 .AND. P_QR<=num_moist) qr_k = MAX(0.0, moist(i,k,j,P_QR))
      IF (P_QI>0 .AND. P_QI<=num_moist) qi_k = MAX(0.0, moist(i,k,j,P_QI))
      IF (P_QS>0 .AND. P_QS<=num_moist) qs_k = MAX(0.0, moist(i,k,j,P_QS))
      IF (P_QG>0 .AND. P_QG<=num_moist) qg_k = MAX(0.0, moist(i,k,j,P_QG))

      qnc_k = 0.0
      IF (F_qnc) THEN
        IF (P_qnc >= 1 .AND. P_qnc <= num_scalar) qnc_k = MAX(0.0, scalar(i,k,j,P_qnc))
      ENDIF
      IF (cfg%fogvis_nd_src == 0) qnc_k = 0.0
      IF (cfg%fogvis_nd_src == 1) THEN
        IF (cfg%mp_physics /= 37 .AND. cfg%mp_physics /= 137) qnc_k = 0.0
      ENDIF

      qsat_k = qsat_liq(Tk_k, p_k)
      rh_k   = clamp(qv_k / MAX(1.0e-12, qsat_k), 0.0, 1.2)
      rho    = rho_moist(p_k, Tk_k, qv_k)

      CALL beta_clw_from_lwc_nc(cfg, rho, qc_k, qnc_k, is_sea, beta_clw, nd_cm3_loc, re_um_loc)

      beta_rain = 0.0; beta_ice = 0.0; beta_snow = 0.0; beta_grau = 0.0
      IF (cfg%fogvis_ext_opt /= 0) THEN
        IF (qr_k > 0.0) THEN
          wc_gm3 = rho*qr_k*1000.0
          beta_rain = cfg%fogvis_A_rain * (wc_gm3 ** cfg%fogvis_B_rain) * 1.0e-3
        ENDIF
        IF (qi_k > 0.0) THEN
          wc_gm3 = rho*qi_k*1000.0
          beta_ice  = cfg%fogvis_A_ice  * (wc_gm3 ** cfg%fogvis_B_ice ) * 1.0e-3
        ENDIF
        IF (qs_k > 0.0) THEN
          wc_gm3 = rho*qs_k*1000.0
          beta_snow = cfg%fogvis_A_snow * (wc_gm3 ** cfg%fogvis_B_snow) * 1.0e-3
        ENDIF
        IF (qg_k > 0.0) THEN
          wc_gm3 = rho*qg_k*1000.0
          beta_grau = cfg%fogvis_A_grau * (wc_gm3 ** cfg%fogvis_B_grau) * 1.0e-3
        ENDIF
      ENDIF

      beta_ext_fog = beta_clw + beta_rain + beta_ice + beta_snow + beta_grau
      beta_ext_fog = MAX(cfg%fogvis_beta_min, beta_ext_fog)
      vis_k = ln1C / beta_ext_fog

      fog_here = (vis_k < cfg%fogvis_vis_thr_m) .OR. ( (rh_k > cfg%fogvis_rh0) .AND. (qc_k > cfg%fogvis_qc0) )

      IF (.NOT. started) THEN
        IF (fog_here) THEN
          started = .TRUE.
          k_base  = k
          k_top   = k
        ENDIF
      ELSE
        IF (fog_here) THEN
          k_top = k
        ELSE
          EXIT
        ENDIF
      ENDIF
    END DO

    IF (k_base > 0) THEN
      IF (k_top+1 > UBOUND(ph,2) .OR. k_top+1 < LBOUND(ph,2)) THEN
        IF (warn_count < 20) THEN
          WRITE(msg,'(A,2(I6,1X),A,2(I6,1X))') 'FOGVIS vlayer k_top+1 out of bounds k_top=', &
               k_top, k_top+1, ' ph(k) bounds=', LBOUND(ph,2), UBOUND(ph,2)
          CALL wrf_message(TRIM(msg))
        ENDIF
        warn_count = warn_count + 1
        RETURN
      ENDIF

      z_base = (ph(i,k_base  ,j) + phb(i,k_base  ,j)) / grav
      z_top  = (ph(i,k_top+1,j) + phb(i,k_top+1,j)) / grav
      bad_z = .FALSE.
      IF (z_base /= z_base .OR. z_top /= z_top) bad_z = .TRUE.
      IF (ABS(z_base) > 1.0e6 .OR. ABS(z_top) > 1.0e6) bad_z = .TRUE.
      IF (bad_z) THEN
        WRITE(msg,'(A,2(I6,1X),A,2(I6,1X),A,2(ES13.5,1X))') &
             'FOGVIS vlayer bad z i/j=', i, j, ' k_base/k_top=', k_base, k_top, &
             ' z_base/z_top=', z_base, z_top
        CALL wrf_message(TRIM(msg))
        WRITE(msg,'(A,2(ES13.5,1X))') 'FOGVIS vlayer ph/phb top=', &
             ph(i,k_top+1,j), phb(i,k_top+1,j)
        CALL wrf_message(TRIM(msg))
        RETURN
      ENDIF
      IF (z_base <= cfg%fogvis_base_max_m) THEN
        fogmask_ij    = 1.0
        fogbase_m_ij  = MAX(0.0, z_base)
        fogtop_m_ij   = MAX(fogbase_m_ij, z_top)
        fogdepth_m_ij = fogtop_m_ij - fogbase_m_ij
      ENDIF
    ENDIF
  END SUBROUTINE fog_layer_diag_ij

  SUBROUTINE diag_fogvis(                                         &
       ids,ide, jds,jde, kds,kde,                                  &
       ims,ime, jms,jme, kms,kme,                                  &
       its,ite, jts,jte, kts,kte,                                  &
       config_flags,                                               &
       xland,                                                      &
       t2, q2, psfc, u10, v10, ust,                                &
       hfx, qfx, pblh,                                             &
       p, pb, t, ph, phb,                                          &
       moist, num_moist,                                           &
       scalar, num_scalar,                                         &
       beta_aer_sfc, aod_sfc,                                       &
       vis_sfc, vis_sfc_raw, vis_sfc_capped, fogfrac_sfc,           &
       fogmask, fogbase_m, fogtop_m, fogdepth_m,                   &
       betaext_sfc, lwc_sfc_gm3, nd_sfc_cm3, re_sfc_um )

    TYPE(grid_config_rec_type), INTENT(IN) :: config_flags
    INTEGER, INTENT(IN) :: ids,ide, jds,jde, kds,kde
    INTEGER, INTENT(IN) :: ims,ime, jms,jme, kms,kme
    INTEGER, INTENT(IN) :: its,ite, jts,jte, kts,kte
    INTEGER, INTENT(IN) :: num_moist, num_scalar

    REAL, DIMENSION(ims:ime, jms:jme), INTENT(IN) :: xland
    REAL, DIMENSION(ims:ime, jms:jme), INTENT(IN) :: t2, q2, psfc, u10, v10, ust
    REAL, DIMENSION(ims:ime, jms:jme), INTENT(IN) :: hfx, qfx, pblh
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme), INTENT(IN) :: p, pb, t
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme), INTENT(IN) :: ph, phb
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme, num_moist),  INTENT(IN) :: moist
    REAL, DIMENSION(ims:ime, kms:kme, jms:jme, num_scalar), INTENT(IN) :: scalar
    REAL, DIMENSION(ims:ime, jms:jme), INTENT(IN) :: beta_aer_sfc
    REAL, DIMENSION(ims:ime, jms:jme), INTENT(IN) :: aod_sfc

    REAL, DIMENSION(ims:ime, jms:jme), INTENT(OUT) :: vis_sfc, vis_sfc_raw, vis_sfc_capped, fogfrac_sfc
    REAL, DIMENSION(ims:ime, jms:jme), INTENT(OUT) :: fogmask, fogbase_m, fogtop_m, fogdepth_m
    REAL, DIMENSION(ims:ime, jms:jme), INTENT(OUT) :: betaext_sfc, lwc_sfc_gm3, nd_sfc_cm3, re_sfc_um

    INTEGER :: i, j
    LOGICAL :: is_sea, use_qnc
    REAL :: qsat2, rh2, wind10
    REAL :: p_bot, theta_bot, Tk_bot
    REAL :: qv_bot, qc_bot, qr_bot, qi_bot, qs_bot, qg_bot
    REAL :: qnc_bot
    REAL :: rho, lwc_gm3, rwc_gm3, iwc_gm3, swc_gm3, gwc_gm3
    REAL :: beta_clw, beta_rain, beta_ice, beta_snow, beta_grau
    REAL :: beta_ext, beta_ext_eff, vis, vis_raw, ln1C
    REAL :: beta_thr, beta_soft, vis_max_m, vis_soft_m
    REAL :: soft_x, soft_val
    REAL :: ff, f_rh, f_qc, f_u
    REAL :: s_mean, sigma_s, z, mix_factor
    REAL :: rh0_use, qc0_use, u0_use
    REAL :: beta_aer_use, beta_aer_aod
    REAL :: aod_use, zeff_m, h_scale_m, z_top_m, denom, pblh_use
    REAL :: nd_cm3_loc, re_um_loc
    REAL :: f_cool, f_shallow, f_moist

    ln1C = LOG(1.0 / MAX(1.0e-6, config_flags%fogvis_C_contrast))
    vis_max_m = MAX(1.0, config_flags%fogvis_vis_max_m)
    beta_thr = ln1C / vis_max_m
    vis_soft_m = MAX(0.0, config_flags%fogvis_vis_soft_m)
    beta_soft = -1.0
    IF (vis_soft_m > 0.0 .AND. vis_soft_m < vis_max_m) THEN
      beta_soft = ln1C / MAX(1.0, vis_max_m - vis_soft_m) - beta_thr
      beta_soft = MAX(1.0e-12, beta_soft)
    ENDIF

    DO j=jts,jte
      DO i=its,ite

        is_sea = (config_flags%fogvis_sea_mode /= 0) .AND. is_water_xland(xland(i,j))

        rh0_use = config_flags%fogvis_rh0
        qc0_use = config_flags%fogvis_qc0
        u0_use  = config_flags%fogvis_u0
        IF (is_sea) THEN
          rh0_use = config_flags%fogvis_rh0_sea
          qc0_use = config_flags%fogvis_qc0_sea
          u0_use  = config_flags%fogvis_u0_sea
        ENDIF

        qsat2 = qsat_liq(t2(i,j), psfc(i,j))
        rh2   = clamp( q2(i,j) / MAX(1.0e-12, qsat2), 0.0, 1.2 )
        wind10 = SQRT(u10(i,j)*u10(i,j) + v10(i,j)*v10(i,j))

        p_bot     = p(i,kts,j) + pb(i,kts,j)
        theta_bot = t(i,kts,j) + 300.0
        Tk_bot    = temp_from_theta(theta_bot, p_bot)

        qv_bot = 0.0; qc_bot = 0.0; qr_bot = 0.0; qi_bot = 0.0; qs_bot = 0.0; qg_bot = 0.0
        IF (P_QV>0 .AND. P_QV<=num_moist) qv_bot = MAX(0.0, moist(i,kts,j,P_QV))
        IF (P_QC>0 .AND. P_QC<=num_moist) qc_bot = MAX(0.0, moist(i,kts,j,P_QC))
        IF (P_QR>0 .AND. P_QR<=num_moist) qr_bot = MAX(0.0, moist(i,kts,j,P_QR))
        IF (P_QI>0 .AND. P_QI<=num_moist) qi_bot = MAX(0.0, moist(i,kts,j,P_QI))
        IF (P_QS>0 .AND. P_QS<=num_moist) qs_bot = MAX(0.0, moist(i,kts,j,P_QS))
        IF (P_QG>0 .AND. P_QG<=num_moist) qg_bot = MAX(0.0, moist(i,kts,j,P_QG))

        qnc_bot = 0.0
        IF (F_qnc) THEN
          IF (P_qnc >= 1 .AND. P_qnc <= num_scalar) qnc_bot = MAX(0.0, scalar(i,kts,j,P_qnc))
        ENDIF

        rho = rho_moist(p_bot, Tk_bot, qv_bot)

        lwc_gm3 = rho * qc_bot * 1000.0
        rwc_gm3 = rho * qr_bot * 1000.0
        iwc_gm3 = rho * qi_bot * 1000.0
        swc_gm3 = rho * qs_bot * 1000.0
        gwc_gm3 = rho * qg_bot * 1000.0

        lwc_sfc_gm3(i,j) = lwc_gm3

        ! aerosol extinction: AOD->beta if enabled, else external input if positive, else constants
        beta_aer_use = -1.0
        IF (config_flags%fogvis_aod_opt > 0 .AND. aod_sfc(i,j) > 0.0) THEN
          aod_use = aod_sfc(i,j)
          beta_aer_aod = -1.0
          SELECT CASE (config_flags%fogvis_aod_opt)
          CASE (1)
            zeff_m = MAX(1.0, config_flags%fogvis_aod_zeff_m)
            beta_aer_aod = aod_use / zeff_m
          CASE (2)
            h_scale_m = MAX(1.0, config_flags%fogvis_aod_scale_h_m)
            z_top_m = MAX(0.0, config_flags%fogvis_aod_top_m)
            IF (z_top_m > 0.0) THEN
              denom = h_scale_m * (1.0 - EXP(-z_top_m / h_scale_m))
            ELSE
              denom = h_scale_m
            ENDIF
            beta_aer_aod = aod_use / MAX(1.0e-6, denom)
          CASE (3)
            pblh_use = pblh(i,j)
            IF (pblh_use <= 0.0) pblh_use = config_flags%fogvis_aod_pblh_default_m
            zeff_m = MAX(1.0, pblh_use * MAX(0.0, config_flags%fogvis_aod_pblh_mult))
            beta_aer_aod = aod_use / zeff_m
          CASE DEFAULT
            beta_aer_aod = -1.0
          END SELECT
          IF (beta_aer_aod > 0.0) beta_aer_use = beta_aer_aod
        ENDIF
        IF (beta_aer_use <= 0.0) THEN
          IF (beta_aer_sfc(i,j) > 0.0) THEN
            beta_aer_use = beta_aer_sfc(i,j)
          ELSE
            beta_aer_use = config_flags%fogvis_beta_aer
            IF (is_sea) beta_aer_use = MAX(beta_aer_use, config_flags%fogvis_beta_aer_sea)
          ENDIF
        ENDIF

        use_qnc = .FALSE.
        IF (config_flags%fogvis_nd_src == 2) THEN
          use_qnc = (qnc_bot > 0.0)
        ELSEIF (config_flags%fogvis_nd_src == 1) THEN
          use_qnc = (config_flags%mp_physics == 37 .OR. config_flags%mp_physics == 137) .AND. (qnc_bot > 0.0)
        ENDIF

        IF (use_qnc) THEN
          CALL beta_clw_from_lwc_nc(config_flags, rho, qc_bot, qnc_bot, is_sea, beta_clw, nd_cm3_loc, re_um_loc)
        ELSE
          CALL beta_clw_from_lwc_nc(config_flags, rho, qc_bot, 0.0,     is_sea, beta_clw, nd_cm3_loc, re_um_loc)
        ENDIF

        nd_sfc_cm3(i,j) = nd_cm3_loc
        re_sfc_um(i,j)  = re_um_loc

        beta_rain = 0.0; beta_ice = 0.0; beta_snow = 0.0; beta_grau = 0.0
        IF (config_flags%fogvis_ext_opt /= 0) THEN
          IF (rwc_gm3 > 0.0) beta_rain = config_flags%fogvis_A_rain * (rwc_gm3 ** config_flags%fogvis_B_rain) * 1.0e-3
          IF (iwc_gm3 > 0.0) beta_ice  = config_flags%fogvis_A_ice  * (iwc_gm3 ** config_flags%fogvis_B_ice ) * 1.0e-3
          IF (swc_gm3 > 0.0) beta_snow = config_flags%fogvis_A_snow * (swc_gm3 ** config_flags%fogvis_B_snow) * 1.0e-3
          IF (gwc_gm3 > 0.0) beta_grau = config_flags%fogvis_A_grau * (gwc_gm3 ** config_flags%fogvis_B_grau) * 1.0e-3
        ENDIF

        beta_ext = beta_aer_use + beta_clw + beta_rain + beta_ice + beta_snow + beta_grau
        beta_ext = MAX(config_flags%fogvis_beta_min, beta_ext)
        betaext_sfc(i,j) = beta_ext

        vis_raw = ln1C / beta_ext
        vis_sfc_raw(i,j) = vis_raw
        vis_sfc_capped(i,j) = 0.0
        IF (vis_raw >= vis_max_m) vis_sfc_capped(i,j) = 1.0

        IF (beta_soft > 0.0) THEN
          soft_x = (beta_ext - beta_thr) / beta_soft
          IF (soft_x > 40.0) THEN
            soft_val = soft_x
          ELSEIF (soft_x < -40.0) THEN
            soft_val = EXP(soft_x)
          ELSE
            soft_val = LOG(1.0 + EXP(soft_x))
          ENDIF
          beta_ext_eff = beta_thr + beta_soft * soft_val
        ELSE
          beta_ext_eff = MAX(beta_ext, beta_thr)
        ENDIF

        vis = ln1C / beta_ext_eff
        vis = clamp(vis, 1.0, vis_max_m)
        vis_sfc(i,j) = vis

        ! Fog Fraction
        IF (config_flags%fogvis_opt == 1) THEN
          f_rh = sigmoid( (rh2 - rh0_use) / MAX(1.0e-6, config_flags%fogvis_drh) )
          f_qc = sigmoid( (qc_bot - qc0_use) / MAX(1.0e-12, config_flags%fogvis_dqc) )
          f_u  = sigmoid( (u0_use - wind10) / MAX(1.0e-6, config_flags%fogvis_du) )
          ff   = MIN(1.0, f_rh * f_qc * f_u)

        ELSEIF (config_flags%fogvis_opt == 2) THEN
          s_mean = q2(i,j) - qsat2

          mix_factor = MIN(1.0, MAX(0.0, ust(i,j)) / MAX(1.0e-6, config_flags%fogvis_ust_ref))
          sigma_s    = config_flags%fogvis_sigma_min + config_flags%fogvis_alpha_sig * qsat2 * (1.0 - mix_factor)

          IF (config_flags%fogvis_sigma_opt >= 2) THEN
            f_cool = sigmoid( ( -hfx(i,j) - config_flags%fogvis_hfx0 ) / MAX(1.0e-6, config_flags%fogvis_dhfx) )
            sigma_s = sigma_s * (1.0 + config_flags%fogvis_alpha_hfx * f_cool)
            f_shallow = EXP( -MAX(0.0, pblh(i,j)) / MAX(1.0, config_flags%fogvis_pblh0) )
            sigma_s = sigma_s * (1.0 + config_flags%fogvis_alpha_pblh * f_shallow)
          ENDIF

          IF (config_flags%fogvis_sigma_opt >= 3) THEN
            f_moist = sigmoid( ( qfx(i,j) - config_flags%fogvis_qfx0 ) / MAX(1.0e-12, config_flags%fogvis_dqfx) )
            sigma_s = sigma_s * (1.0 + config_flags%fogvis_alpha_qfx * f_moist)
          ENDIF

          IF (is_sea) sigma_s = sigma_s * MAX(0.1, config_flags%fogvis_sigma_sea_mult)

          sigma_s = MAX(config_flags%fogvis_sigma_min, sigma_s)
          z  = (-s_mean) / (SQRT(2.0) * sigma_s)
          ff = 0.5 * erfc_approx(z)

          f_u = sigmoid( (u0_use - wind10) / MAX(1.0e-6, config_flags%fogvis_du) )
          ff  = clamp(ff * f_u, 0.0, 1.0)
        ELSE
          ff = 0.0
        ENDIF

        fogfrac_sfc(i,j) = ff

        ! Vertical fog layer (optional)
        fogmask(i,j)    = 0.0
        fogbase_m(i,j)  = 0.0
        fogtop_m(i,j)   = 0.0
        fogdepth_m(i,j) = 0.0

        IF (config_flags%fogvis_vlayer_opt /= 0) THEN
          CALL fog_layer_diag_ij( config_flags, i, j, ims, ime, jms, jme, kms, kme, &
                                  kts, kte, num_moist, num_scalar, xland(i,j), &
                                  p, pb, t, ph, phb, moist, scalar, &
                                  fogmask(i,j), fogbase_m(i,j), fogtop_m(i,j), fogdepth_m(i,j) )
        ENDIF

        IF (config_flags%fogvis_ff_floor_opt /= 0) THEN
          IF (fogmask(i,j) > 0.5) fogfrac_sfc(i,j) = MAX(fogfrac_sfc(i,j), config_flags%fogvis_ff_floor)
        ENDIF

        IF (config_flags%fogvis_entrain_opt /= 0) THEN
          IF (fogmask(i,j) > 0.5) THEN
            IF (fogtop_m(i,j) > config_flags%fogvis_top_pen_m) THEN
              f_u = sigmoid( (config_flags%fogvis_pen_u0 - wind10) / MAX(1.0e-6, config_flags%fogvis_pen_du) )
              fogfrac_sfc(i,j) = fogfrac_sfc(i,j) * f_u * EXP( - (fogtop_m(i,j) - config_flags%fogvis_top_pen_m) / &
                                   MAX(1.0, config_flags%fogvis_top_pen_scale_m) )
              fogfrac_sfc(i,j) = clamp(fogfrac_sfc(i,j), 0.0, 1.0)
            ENDIF
          ENDIF
        ENDIF

      END DO
    END DO

  END SUBROUTINE diag_fogvis

END MODULE module_diag_fogvis
