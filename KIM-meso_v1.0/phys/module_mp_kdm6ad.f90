MODULE module_mp_kdm6ad

  USE, INTRINSIC :: iso_c_binding, ONLY: c_double, c_float, c_int, c_ptr
  USE module_wrf_error
  USE kdm6_iso_c, ONLY: kdm6_step, kdm6_handle_close, KDM6_OK
  
  
  
  USE module_mp_kdm6, ONLY: effectRad_kdm6, refl10cm_kdm6
  USE module_model_constants, ONLY: RE_QC_BG, RE_QI_BG, RE_QS_BG

  IMPLICIT NONE

CONTAINS

  SUBROUTINE kdm6ad(TH, Q, QC, QR, QI, QS, QG, NN, NC, NI, NR, BG, diag_rhog, &
                    DEN, PII, P, DELZ, DELT, G, CPD, CPV, CCN0, RD, RV, T0C, &
                    EP1, EP2, QMIN, XLS, XLV0, XLF0, DEN0, DENR,             &
                    scale_h, ncmin_land, ncmin_sea, CLIQ, CICE, PSAT,        &
                    XLAND, RAIN, RAINNCV, SNOW, SNOWNCV, SR,                 &
                    REFL_10CM, diagflag, do_radar_ref, GRAUPEL, GRAUPELNCV,  &
                    ITIMESTEP, has_reqc, has_reqi, has_reqs,                 &
                    re_cloud, re_ice, re_snow,                               &
                    IMS, IME, JMS, JME, KMS, KME,                             &
                    ITS, ITE, JTS, JTE, KTS, KTE)

    IMPLICIT NONE

    INTEGER, INTENT(IN) :: IMS, IME, JMS, JME, KMS, KME
    INTEGER, INTENT(IN) :: ITS, ITE, JTS, JTE, KTS, KTE
    REAL, INTENT(INOUT) :: TH(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: Q(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: QC(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: QR(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: QI(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: QS(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: QG(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: NN(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: NC(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: NI(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: NR(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: BG(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: diag_rhog(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(IN)    :: DEN(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(IN)    :: PII(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(IN)    :: P(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(IN)    :: DELZ(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(IN)    :: DELT
    REAL, INTENT(IN)    :: G, CPD, CPV, CCN0, RD, RV, T0C
    REAL, INTENT(IN)    :: EP1, EP2, QMIN, XLS, XLV0, XLF0, DEN0, DENR
    REAL, INTENT(IN)    :: scale_h, ncmin_land, ncmin_sea, CLIQ, CICE, PSAT
    REAL, INTENT(IN)    :: XLAND(IMS:IME, JMS:JME)
    REAL, INTENT(INOUT) :: RAIN(IMS:IME, JMS:JME), RAINNCV(IMS:IME, JMS:JME)
    REAL, INTENT(INOUT) :: SNOW(IMS:IME, JMS:JME), SNOWNCV(IMS:IME, JMS:JME)
    REAL, INTENT(INOUT) :: SR(IMS:IME, JMS:JME)
    REAL, INTENT(INOUT) :: REFL_10CM(IMS:IME, KMS:KME, JMS:JME)
    LOGICAL, INTENT(IN) :: diagflag
    INTEGER, INTENT(IN) :: do_radar_ref
    REAL, INTENT(INOUT) :: GRAUPEL(IMS:IME, JMS:JME), GRAUPELNCV(IMS:IME, JMS:JME)
    INTEGER, INTENT(IN) :: ITIMESTEP
    INTEGER, INTENT(IN) :: has_reqc, has_reqi, has_reqs
    REAL, INTENT(INOUT) :: re_cloud(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: re_ice(IMS:IME, KMS:KME, JMS:JME)
    REAL, INTENT(INOUT) :: re_snow(IMS:IME, KMS:KME, JMS:JME)

    INTEGER :: I, J, K, II, JJ, KK
    INTEGER :: IM, KM, JM
    INTEGER(c_int) :: RC
    TYPE(c_ptr) :: HANDLE
    REAL :: Z_SUM

    REAL(c_float), ALLOCATABLE :: TH_IN(:,:,:), Q_IN(:,:,:), QC_IN(:,:,:), QR_IN(:,:,:)
    REAL(c_float), ALLOCATABLE :: QI_IN(:,:,:), QS_IN(:,:,:), QG_IN(:,:,:)
    REAL(c_float), ALLOCATABLE :: NN_IN(:,:,:), NC_IN(:,:,:), NI_IN(:,:,:), NR_IN(:,:,:), BG_IN(:,:,:)
    REAL(c_float), ALLOCATABLE :: DEN_IN(:,:,:), PII_IN(:,:,:), P_IN(:,:,:), DELZ_IN(:,:,:)
    REAL(c_float), ALLOCATABLE :: TH_OUT(:,:,:), Q_OUT(:,:,:), QC_OUT(:,:,:), QR_OUT(:,:,:)
    REAL(c_float), ALLOCATABLE :: QI_OUT(:,:,:), QS_OUT(:,:,:), QG_OUT(:,:,:)
    REAL(c_float), ALLOCATABLE :: NN_OUT(:,:,:), NC_OUT(:,:,:), NI_OUT(:,:,:), NR_OUT(:,:,:), BG_OUT(:,:,:)
    
    
    REAL(c_float), ALLOCATABLE :: XLAND_IN(:,:)
    
    
    
    REAL(c_float), ALLOCATABLE :: RAIN_INC(:,:), SNOW_INC(:,:), GRAUPEL_INC(:,:)
    REAL :: TOTAL_INC, SOLID_INC
    
    
    REAL(c_float), ALLOCATABLE :: RHOG_OUT(:,:,:)

    

    
    REAL :: t1d(KTS:KTE), den1d(KTS:KTE), qc1d(KTS:KTE), qi1d(KTS:KTE), qs1d(KTS:KTE)
    REAL :: nc1d(KTS:KTE), ni1d(KTS:KTE), re_qc(KTS:KTE), re_qi(KTS:KTE), re_qs(KTS:KTE)

    
    
    REAL :: qv1d(KTS:KTE), qr1d(KTS:KTE), nr1d(KTS:KTE), qg1d(KTS:KTE), p1d(KTS:KTE)
    REAL :: n0so1d(KTS:KTE), n0go1d(KTS:KTE), cmg1d(KTS:KTE), dBZ(KTS:KTE)
    REAL :: refl_pi

    IM = ITE - ITS + 1
    KM = KTE - KTS + 1
    JM = JTE - JTS + 1

    CALL wrf_debug(100, 'module_mp_kdm6ad: entering kdm6ad wrapper')

    ALLOCATE(TH_IN(IM, KM, JM), Q_IN(IM, KM, JM), QC_IN(IM, KM, JM), QR_IN(IM, KM, JM))
    ALLOCATE(QI_IN(IM, KM, JM), QS_IN(IM, KM, JM), QG_IN(IM, KM, JM))
    ALLOCATE(NN_IN(IM, KM, JM), NC_IN(IM, KM, JM), NI_IN(IM, KM, JM), NR_IN(IM, KM, JM), BG_IN(IM, KM, JM))
    ALLOCATE(DEN_IN(IM, KM, JM), PII_IN(IM, KM, JM), P_IN(IM, KM, JM), DELZ_IN(IM, KM, JM))
    ALLOCATE(TH_OUT(IM, KM, JM), Q_OUT(IM, KM, JM), QC_OUT(IM, KM, JM), QR_OUT(IM, KM, JM))
    ALLOCATE(QI_OUT(IM, KM, JM), QS_OUT(IM, KM, JM), QG_OUT(IM, KM, JM))
    ALLOCATE(NN_OUT(IM, KM, JM), NC_OUT(IM, KM, JM), NI_OUT(IM, KM, JM), NR_OUT(IM, KM, JM), BG_OUT(IM, KM, JM))
    ALLOCATE(XLAND_IN(IM, JM))
    ALLOCATE(RAIN_INC(IM, JM), SNOW_INC(IM, JM), GRAUPEL_INC(IM, JM))
    ALLOCATE(RHOG_OUT(IM, KM, JM))
    RHOG_OUT = 0.0_c_float   
                             

    IF (ITIMESTEP == 1) THEN
      DO J = JMS, JME
        DO I = IMS, IME
          Z_SUM = 0.0
          DO K = KMS, KME
            Z_SUM = Z_SUM + DELZ(I, K, J)
            IF (XLAND(I, J) == 1.0) THEN
              NN(I, K, J) = (5000.0 * EXP(-0.4 * Z_SUM / 1000.0) + 100.0) * 1.0E6
            ELSE
              NN(I, K, J) = (150.0 * EXP(-0.35 * Z_SUM / 1000.0) + 10.0) * 1.0E6
            END IF
          END DO
        END DO
      END DO
    END IF

    

    

    DO J = JTS, JTE
      JJ = J - JTS + 1
      DO K = KTS, KTE
        KK = K - KTS + 1
        DO I = ITS, ITE
          II = I - ITS + 1
          TH_IN(II, KK, JJ) = REAL(TH(I, K, J), c_float)
          Q_IN(II, KK, JJ) = REAL(Q(I, K, J), c_float)
          QC_IN(II, KK, JJ) = REAL(QC(I, K, J), c_float)
          QR_IN(II, KK, JJ) = REAL(QR(I, K, J), c_float)
          QI_IN(II, KK, JJ) = REAL(QI(I, K, J), c_float)
          QS_IN(II, KK, JJ) = REAL(QS(I, K, J), c_float)
          QG_IN(II, KK, JJ) = REAL(QG(I, K, J), c_float)
          NN_IN(II, KK, JJ) = REAL(NN(I, K, J), c_float)
          NC_IN(II, KK, JJ) = REAL(NC(I, K, J), c_float)
          NI_IN(II, KK, JJ) = REAL(NI(I, K, J), c_float)
          NR_IN(II, KK, JJ) = REAL(NR(I, K, J), c_float)
          BG_IN(II, KK, JJ) = REAL(BG(I, K, J), c_float)
          DEN_IN(II, KK, JJ) = REAL(DEN(I, K, J), c_float)
          PII_IN(II, KK, JJ) = REAL(PII(I, K, J), c_float)
          P_IN(II, KK, JJ) = REAL(P(I, K, J), c_float)
          DELZ_IN(II, KK, JJ) = REAL(DELZ(I, K, J), c_float)
        END DO
      END DO
    END DO

    
    
    DO J = JTS, JTE
      JJ = J - JTS + 1
      DO I = ITS, ITE
        II = I - ITS + 1
        XLAND_IN(II, JJ) = REAL(XLAND(I, J), c_float)
      END DO
    END DO

    RC = kdm6_step(TH_IN, Q_IN, QC_IN, QR_IN, QI_IN, QS_IN, QG_IN, &
                   NN_IN, NC_IN, NI_IN, NR_IN, BG_IN,              &
                   DEN_IN, PII_IN, P_IN, DELZ_IN,                  &
                   INT(IM, c_int), INT(KM, c_int), INT(JM, c_int), REAL(DELT, c_double), &
                   0_c_int, 1_c_int,                               &
                   TH_OUT, Q_OUT, QC_OUT, QR_OUT, QI_OUT, QS_OUT, QG_OUT, &
                   NN_OUT, NC_OUT, NI_OUT, NR_OUT, BG_OUT, HANDLE, &
                   XLAND_IN, REAL(ncmin_land, c_double), REAL(ncmin_sea, c_double), &
                   RAIN_INC, SNOW_INC, GRAUPEL_INC, &
                   RHOG_OUT)

    IF (RC /= KDM6_OK) THEN
      CALL wrf_error_fatal3("<stdin>",190,&
'kdm6ad: kdm6_step failed')
    END IF

    RC = kdm6_handle_close(HANDLE)
    IF (RC /= KDM6_OK) THEN
      CALL wrf_error_fatal3("<stdin>",196,&
'kdm6ad: kdm6_handle_close failed')
    END IF
    DO J = JTS, JTE
      JJ = J - JTS + 1
      DO K = KTS, KTE
        KK = K - KTS + 1
        DO I = ITS, ITE
          II = I - ITS + 1
          TH(I, K, J) = REAL(TH_OUT(II, KK, JJ))
          Q(I, K, J) = REAL(Q_OUT(II, KK, JJ))
          QC(I, K, J) = REAL(QC_OUT(II, KK, JJ))
          QR(I, K, J) = REAL(QR_OUT(II, KK, JJ))
          QI(I, K, J) = REAL(QI_OUT(II, KK, JJ))
          QS(I, K, J) = REAL(QS_OUT(II, KK, JJ))
          QG(I, K, J) = REAL(QG_OUT(II, KK, JJ))
          NN(I, K, J) = REAL(NN_OUT(II, KK, JJ))
          NC(I, K, J) = REAL(NC_OUT(II, KK, JJ))
          NI(I, K, J) = REAL(NI_OUT(II, KK, JJ))
          NR(I, K, J) = REAL(NR_OUT(II, KK, JJ))
          BG(I, K, J) = REAL(BG_OUT(II, KK, JJ))
          diag_rhog(I, K, J) = REAL(RHOG_OUT(II, KK, JJ))
        END DO
      END DO
    END DO

    
    
    
    
    
    
    
    
    
    IF (has_reqc /= 0 .AND. has_reqi /= 0 .AND. has_reqs /= 0) THEN
      DO J = JTS, JTE
        DO I = ITS, ITE
          DO K = KTS, KTE
            re_qc(K) = RE_QC_BG
            re_qi(K) = RE_QI_BG
            re_qs(K) = RE_QS_BG
            t1d(K)   = TH(I, K, J) * PII(I, K, J)
            den1d(K) = DEN(I, K, J)
            qc1d(K)  = QC(I, K, J)
            qi1d(K)  = QI(I, K, J)
            qs1d(K)  = QS(I, K, J)
            nc1d(K)  = NC(I, K, J)
            ni1d(K)  = NI(I, K, J)
          END DO
          CALL effectRad_kdm6(t1d, qc1d, nc1d, qi1d, ni1d, qs1d, den1d, &
                              QMIN, T0C, re_qc, re_qi, re_qs, KTS, KTE, I, J)
          DO K = KTS, KTE
            re_cloud(I, K, J) = MAX(RE_QC_BG, MIN(re_qc(K),  50.E-6))
            re_ice(I, K, J)   = MAX(RE_QI_BG, MIN(re_qi(K), 125.E-6))
            re_snow(I, K, J)  = MAX(RE_QS_BG, MIN(re_qs(K), 999.E-6))
          END DO
        END DO
      END DO
    END IF

    
    
    
    
    
    
    
    

    
    IF (diagflag .AND. do_radar_ref == 1) THEN
      refl_pi = 4.0 * ATAN(1.0)
      DO J = JTS, JTE
        JJ = J - JTS + 1
        DO I = ITS, ITE
          II = I - ITS + 1
          DO K = KTS, KTE
            KK = K - KTS + 1
            t1d(K)    = TH(I, K, J) * PII(I, K, J)
            p1d(K)    = P(I, K, J)
            qv1d(K)   = Q(I, K, J)
            qr1d(K)   = QR(I, K, J)
            nr1d(K)   = NR(I, K, J)
            qs1d(K)   = QS(I, K, J)
            qg1d(K)   = QG(I, K, J)
            n0so1d(K) = 2.E6
            n0go1d(K) = 4.E6
            cmg1d(K)  = refl_pi * RHOG_OUT(II, KK, JJ) / 6.0
          END DO
          CALL refl10cm_kdm6(qv1d, qr1d, nr1d, qs1d, qg1d, n0so1d, &
                             n0go1d, t1d, p1d, dBZ, KTS, KTE, I, J, cmg1d)
          DO K = KTS, KTE
            REFL_10CM(I, K, J) = MAX(-35.0, dBZ(K))
          END DO
        END DO
      END DO
    END IF

    
    
    
    
    
    
    
    

    
    
    
    
    
    
    DO J = JTS, JTE
      JJ = J - JTS + 1
      DO I = ITS, ITE
        II = I - ITS + 1
        
        RAINNCV(I, J)    = 0.0
        SNOWNCV(I, J)    = 0.0
        GRAUPELNCV(I, J) = 0.0
        SR(I, J)         = 0.0

        TOTAL_INC = REAL(RAIN_INC(II, JJ))
        SOLID_INC = REAL(SNOW_INC(II, JJ) + GRAUPEL_INC(II, JJ))
        IF (TOTAL_INC > 0.0) THEN
          RAINNCV(I, J) = TOTAL_INC
          RAIN(I, J)    = TOTAL_INC + RAIN(I, J)
        END IF
        IF (REAL(SNOW_INC(II, JJ)) > 0.0) THEN
          SNOWNCV(I, J) = REAL(SNOW_INC(II, JJ))
          SNOW(I, J)    = REAL(SNOW_INC(II, JJ)) + SNOW(I, J)
        END IF
        IF (REAL(GRAUPEL_INC(II, JJ)) > 0.0) THEN
          GRAUPELNCV(I, J) = REAL(GRAUPEL_INC(II, JJ))
          GRAUPEL(I, J)    = REAL(GRAUPEL_INC(II, JJ)) + GRAUPEL(I, J)
        END IF
        
        
        
        IF (TOTAL_INC > 0.0) THEN
          SR(I, J) = SOLID_INC / (RAINNCV(I, J) + 1.0E-12)
        END IF
      END DO
    END DO

    IF (ANY(TH(ITS:ITE,KTS:KTE,JTS:JTE) /= TH(ITS:ITE,KTS:KTE,JTS:JTE)) .OR. &
        ANY(Q(ITS:ITE,KTS:KTE,JTS:JTE) /= Q(ITS:ITE,KTS:KTE,JTS:JTE)) .OR. &
        ANY(QC(ITS:ITE,KTS:KTE,JTS:JTE) /= QC(ITS:ITE,KTS:KTE,JTS:JTE)) .OR. &
        ANY(QI(ITS:ITE,KTS:KTE,JTS:JTE) /= QI(ITS:ITE,KTS:KTE,JTS:JTE))) THEN
      CALL wrf_error_fatal3("<stdin>",347,&
'kdm6ad: NaN after copy-back')
    END IF

    
    

  END SUBROUTINE kdm6ad

END MODULE module_mp_kdm6ad
