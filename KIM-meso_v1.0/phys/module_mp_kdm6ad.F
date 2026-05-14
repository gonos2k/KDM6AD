MODULE module_mp_kdm6ad

  USE, INTRINSIC :: iso_c_binding, ONLY: c_double, c_int, c_ptr
  USE module_wrf_error
  USE kdm6_iso_c, ONLY: kdm6_step, kdm6_handle_close, KDM6_OK

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

    REAL(c_double), ALLOCATABLE :: TH_IN(:,:,:), Q_IN(:,:,:), QC_IN(:,:,:), QR_IN(:,:,:)
    REAL(c_double), ALLOCATABLE :: QI_IN(:,:,:), QS_IN(:,:,:), QG_IN(:,:,:)
    REAL(c_double), ALLOCATABLE :: NN_IN(:,:,:), NC_IN(:,:,:), NI_IN(:,:,:), NR_IN(:,:,:), BG_IN(:,:,:)
    REAL(c_double), ALLOCATABLE :: DEN_IN(:,:,:), PII_IN(:,:,:), P_IN(:,:,:), DELZ_IN(:,:,:)
    REAL(c_double), ALLOCATABLE :: TH_OUT(:,:,:), Q_OUT(:,:,:), QC_OUT(:,:,:), QR_OUT(:,:,:)
    REAL(c_double), ALLOCATABLE :: QI_OUT(:,:,:), QS_OUT(:,:,:), QG_OUT(:,:,:)
    REAL(c_double), ALLOCATABLE :: NN_OUT(:,:,:), NC_OUT(:,:,:), NI_OUT(:,:,:), NR_OUT(:,:,:), BG_OUT(:,:,:)

    IM = ITE - ITS + 1
    KM = KTE - KTS + 1
    JM = JTE - JTS + 1

    WRITE(0,*) 'KDM6AD_PHASE wrapper entry im/km/jm/dt=', IM, KM, JM, DELT
    FLUSH(0)
    CALL wrf_debug(100, 'module_mp_kdm6ad: entering kdm6ad wrapper')

    ALLOCATE(TH_IN(IM, KM, JM), Q_IN(IM, KM, JM), QC_IN(IM, KM, JM), QR_IN(IM, KM, JM))
    ALLOCATE(QI_IN(IM, KM, JM), QS_IN(IM, KM, JM), QG_IN(IM, KM, JM))
    ALLOCATE(NN_IN(IM, KM, JM), NC_IN(IM, KM, JM), NI_IN(IM, KM, JM), NR_IN(IM, KM, JM), BG_IN(IM, KM, JM))
    ALLOCATE(DEN_IN(IM, KM, JM), PII_IN(IM, KM, JM), P_IN(IM, KM, JM), DELZ_IN(IM, KM, JM))
    ALLOCATE(TH_OUT(IM, KM, JM), Q_OUT(IM, KM, JM), QC_OUT(IM, KM, JM), QR_OUT(IM, KM, JM))
    ALLOCATE(QI_OUT(IM, KM, JM), QS_OUT(IM, KM, JM), QG_OUT(IM, KM, JM))
    ALLOCATE(NN_OUT(IM, KM, JM), NC_OUT(IM, KM, JM), NI_OUT(IM, KM, JM), NR_OUT(IM, KM, JM), BG_OUT(IM, KM, JM))

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

    ! KDM6AD step-1 forward-consistency dump (slot 137 path, pre-physics)
    IF (ITIMESTEP == 1) THEN
      OPEN(UNIT=8802, FILE='kdm6_step1_kdm6ad_in.bin', FORM='UNFORMATTED', &
           ACCESS='STREAM', STATUS='REPLACE')
      WRITE(8802) IMS, IME, KMS, KME, JMS, JME
      WRITE(8802) Q
      WRITE(8802) QC
      WRITE(8802) QR
      WRITE(8802) QI
      WRITE(8802) QS
      WRITE(8802) QG
      WRITE(8802) NC
      WRITE(8802) NR
      WRITE(8802) NI
      WRITE(8802) NN
      WRITE(8802) BG
      WRITE(8802) TH
      CLOSE(8802)
    END IF

    DO J = JTS, JTE
      JJ = J - JTS + 1
      DO K = KTS, KTE
        KK = K - KTS + 1
        DO I = ITS, ITE
          II = I - ITS + 1
          TH_IN(II, KK, JJ) = REAL(TH(I, K, J), c_double)
          Q_IN(II, KK, JJ) = REAL(Q(I, K, J), c_double)
          QC_IN(II, KK, JJ) = REAL(QC(I, K, J), c_double)
          QR_IN(II, KK, JJ) = REAL(QR(I, K, J), c_double)
          QI_IN(II, KK, JJ) = REAL(QI(I, K, J), c_double)
          QS_IN(II, KK, JJ) = REAL(QS(I, K, J), c_double)
          QG_IN(II, KK, JJ) = REAL(QG(I, K, J), c_double)
          NN_IN(II, KK, JJ) = REAL(NN(I, K, J), c_double)
          NC_IN(II, KK, JJ) = REAL(NC(I, K, J), c_double)
          NI_IN(II, KK, JJ) = REAL(NI(I, K, J), c_double)
          NR_IN(II, KK, JJ) = REAL(NR(I, K, J), c_double)
          BG_IN(II, KK, JJ) = REAL(BG(I, K, J), c_double)
          DEN_IN(II, KK, JJ) = REAL(DEN(I, K, J), c_double)
          PII_IN(II, KK, JJ) = REAL(PII(I, K, J), c_double)
          P_IN(II, KK, JJ) = REAL(P(I, K, J), c_double)
          DELZ_IN(II, KK, JJ) = REAL(DELZ(I, K, J), c_double)
        END DO
      END DO
    END DO

    RC = kdm6_step(TH_IN, Q_IN, QC_IN, QR_IN, QI_IN, QS_IN, QG_IN, &
                   NN_IN, NC_IN, NI_IN, NR_IN, BG_IN,              &
                   DEN_IN, PII_IN, P_IN, DELZ_IN,                  &
                   INT(IM, c_int), INT(KM, c_int), INT(JM, c_int), REAL(DELT, c_double), &
                   0_c_int, 1_c_int,                               &
                   TH_OUT, Q_OUT, QC_OUT, QR_OUT, QI_OUT, QS_OUT, QG_OUT, &
                   NN_OUT, NC_OUT, NI_OUT, NR_OUT, BG_OUT, HANDLE)

    IF (RC /= KDM6_OK) THEN
      CALL wrf_error_fatal('kdm6ad: kdm6_step failed')
    END IF

    RC = kdm6_handle_close(HANDLE)
    IF (RC /= KDM6_OK) THEN
      CALL wrf_error_fatal('kdm6ad: kdm6_handle_close failed')
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
        END DO
      END DO
    END DO
    IF (ANY(TH(ITS:ITE,KTS:KTE,JTS:JTE) /= TH(ITS:ITE,KTS:KTE,JTS:JTE)) .OR. &
        ANY(Q(ITS:ITE,KTS:KTE,JTS:JTE) /= Q(ITS:ITE,KTS:KTE,JTS:JTE)) .OR. &
        ANY(QC(ITS:ITE,KTS:KTE,JTS:JTE) /= QC(ITS:ITE,KTS:KTE,JTS:JTE)) .OR. &
        ANY(QI(ITS:ITE,KTS:KTE,JTS:JTE) /= QI(ITS:ITE,KTS:KTE,JTS:JTE))) THEN
      CALL wrf_error_fatal('kdm6ad: NaN after copy-back')
    END IF

    ! KDM6AD step-1 forward-consistency dump (slot 137 path, post-physics)
    IF (ITIMESTEP == 1) THEN
      OPEN(UNIT=8802, FILE='kdm6_step1_kdm6ad_out.bin', FORM='UNFORMATTED', &
           ACCESS='STREAM', STATUS='REPLACE')
      WRITE(8802) IMS, IME, KMS, KME, JMS, JME
      WRITE(8802) Q
      WRITE(8802) QC
      WRITE(8802) QR
      WRITE(8802) QI
      WRITE(8802) QS
      WRITE(8802) QG
      WRITE(8802) NC
      WRITE(8802) NR
      WRITE(8802) NI
      WRITE(8802) NN
      WRITE(8802) BG
      WRITE(8802) TH
      CLOSE(8802)
    END IF

  END SUBROUTINE kdm6ad

END MODULE module_mp_kdm6ad
