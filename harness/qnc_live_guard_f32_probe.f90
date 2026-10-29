! Source-compatible RK3 QNC sign envelope on saved binary32 operands.
! This reports arithmetic possibilities; it does not identify emitted opcodes.
MODULE qnc_live_guard_f32_probe
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_FLOAT, C_INT, C_INT32_T
  USE, INTRINSIC :: IEEE_ARITHMETIC, ONLY: IEEE_FMA, IEEE_IS_FINITE, &
       IEEE_NEAREST, IEEE_SUPPORT_ROUNDING
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: qnc_live_guard_predict_f32
  INTERFACE
    INTEGER(C_INT) FUNCTION qnc_rounding_is_nearest() BIND(C, NAME='qnc_rounding_is_nearest')
      IMPORT C_INT
    END FUNCTION qnc_rounding_is_nearest
    INTEGER(C_INT) FUNCTION qnc_gradual_underflow_enabled() &
         BIND(C, NAME='qnc_gradual_underflow_enabled')
      IMPORT C_INT
    END FUNCTION qnc_gradual_underflow_enabled
  END INTERFACE
CONTAINS
  LOGICAL FUNCTION qnc_bad_input(value)
    REAL(C_FLOAT), INTENT(IN) :: value
    INTEGER(C_INT32_T) :: bits
    bits=TRANSFER(value,0_C_INT32_T)
    qnc_bad_input=.NOT.IEEE_IS_FINITE(value) .OR. &
         (IAND(bits,INT(Z'7F800000',C_INT32_T))==0 .AND. &
          IAND(bits,INT(Z'007FFFFF',C_INT32_T))/=0)
  END FUNCTION qnc_bad_input

  LOGICAL FUNCTION qnc_bad_result(value)
    REAL(C_FLOAT), INTENT(IN) :: value
    qnc_bad_result=qnc_bad_input(value)
  END FUNCTION qnc_bad_result

  REAL(C_FLOAT) FUNCTION qnc_axis_tendency(words, mode) RESULT(value)
    REAL(C_FLOAT), INTENT(IN) :: words(26)
    INTEGER, INTENT(IN) :: mode
    REAL(C_FLOAT) :: delta, inner, factor, term
    LOGICAL :: fused

    value=0.0_C_FLOAT

    ! Axis order and parenthesization match the public Python replay:
    ! vertical, x, then y; each face difference rounds separately to f32.
    delta=words(26)-words(25)
    delta=delta+words(20)
    delta=delta-words(19)
    factor=words(11)
    inner=factor*delta
    fused=BTEST(mode,2)
    IF (fused) THEN
      value=IEEE_FMA(-factor,delta,value)
    ELSE
      value=value-inner
    END IF

    delta=words(22)-words(21)
    delta=delta+words(16)
    delta=delta-words(15)
    factor=words(9)
    inner=factor*delta
    term=words(7)*inner
    fused=BTEST(mode,1)
    IF (fused) THEN
      value=IEEE_FMA(-words(7),inner,value)
    ELSE
      value=value-term
    END IF

    delta=words(24)-words(23)
    delta=delta+words(18)
    delta=delta-words(17)
    factor=words(10)
    inner=factor*delta
    term=words(7)*inner
    fused=BTEST(mode,0)
    IF (fused) THEN
      value=IEEE_FMA(-words(7),inner,value)
    ELSE
      value=value-term
    END IF
  END FUNCTION qnc_axis_tendency

  SUBROUTINE qnc_live_guard_predict_f32(words, mu_new, scalar_source, &
       predicted_bits, all_positive, status) BIND(C, NAME='qnc_live_guard_predict_f32')
    ! words(1:14): FIELD_OLD,C1H,C2H,MU_OLD,MU_BASE,DT,MSFTX,MSFTY,
    ! RDX,RDY,RDZW,PH_LOW,FLUX_OUT,SCALE.  words(15:20): low west/east,
    ! south/north,bottom/top.  words(21:26): post west/east,south/north,
    ! bottom/top.  Output order is axis mode 0..7 then RK mode 0..23.
    REAL(C_FLOAT), INTENT(IN) :: words(26)
    REAL(C_FLOAT), VALUE, INTENT(IN) :: mu_new, scalar_source
    INTEGER(C_INT32_T), INTENT(OUT) :: predicted_bits(192)
    INTEGER(C_INT), INTENT(OUT) :: all_positive, status
    REAL(C_FLOAT) :: advect, mu_old_total, mu_new_total
    REAL(C_FLOAT) :: tendency, old_factor, new_factor, dt_tendency
    REAL(C_FLOAT) :: old_product, numerator, qnc_value, product
    INTEGER :: axis_mode, rk_mode, site_mode, numerator_mode, index, word_index
    LOGICAL :: fused_tendency, fused_old, fused_new

    predicted_bits=0_C_INT32_T
    all_positive=0_C_INT
    status=0_C_INT
    IF (STORAGE_SIZE(0.0_C_FLOAT)/=32 .OR. RADIX(0.0_C_FLOAT)/=2 .OR. &
        DIGITS(0.0_C_FLOAT)/=24 .OR. MAXEXPONENT(0.0_C_FLOAT)/=128) RETURN
    IF (.NOT.IEEE_SUPPORT_ROUNDING(IEEE_NEAREST,1.0_C_FLOAT)) RETURN
    IF (qnc_rounding_is_nearest()/=1_C_INT) RETURN
    IF (qnc_gradual_underflow_enabled()/=1_C_INT) RETURN
    IF (qnc_bad_input(mu_new) .OR. qnc_bad_input(scalar_source)) RETURN
    DO word_index=1,26
      IF (qnc_bad_input(words(word_index))) RETURN
    END DO

    mu_old_total=words(4)+words(5)
    mu_new_total=mu_new+words(5)
    product=words(2)*mu_old_total
    old_factor=product+words(3)
    product=words(2)*mu_new_total
    new_factor=product+words(3)
    IF (qnc_bad_result(mu_old_total) .OR. qnc_bad_result(mu_new_total) .OR. &
        qnc_bad_result(old_factor) .OR. qnc_bad_result(new_factor)) RETURN
    IF (old_factor<=0.0_C_FLOAT .OR. new_factor<=0.0_C_FLOAT) RETURN

    all_positive=1_C_INT
    DO axis_mode=0,7
      advect=qnc_axis_tendency(words,axis_mode)
      IF (.NOT.IEEE_IS_FINITE(advect)) THEN
        all_positive=0_C_INT
        RETURN
      END IF
      DO rk_mode=0,23
        site_mode=rk_mode/3
        numerator_mode=MOD(rk_mode,3)
        fused_tendency=BTEST(site_mode,2)
        fused_old=BTEST(site_mode,1)
        fused_new=BTEST(site_mode,0)

        IF (fused_tendency) THEN
          tendency=IEEE_FMA(advect,words(8),scalar_source)
        ELSE
          product=advect*words(8)
          tendency=product+scalar_source
        END IF
        IF (fused_old) THEN
          old_factor=IEEE_FMA(words(2),mu_old_total,words(3))
        ELSE
          product=words(2)*mu_old_total
          old_factor=product+words(3)
        END IF
        IF (fused_new) THEN
          new_factor=IEEE_FMA(words(2),mu_new_total,words(3))
        ELSE
          product=words(2)*mu_new_total
          new_factor=product+words(3)
        END IF
        IF (qnc_bad_result(tendency) .OR. qnc_bad_result(old_factor) .OR. &
            qnc_bad_result(new_factor) .OR. old_factor<=0.0_C_FLOAT .OR. &
            new_factor<=0.0_C_FLOAT) THEN
          all_positive=0_C_INT
          RETURN
        END IF

        dt_tendency=words(6)*tendency
        old_product=old_factor*words(1)
        SELECT CASE (numerator_mode)
        CASE (0)
          numerator=old_product+dt_tendency
        CASE (1)
          numerator=IEEE_FMA(old_factor,words(1),dt_tendency)
        CASE (2)
          numerator=IEEE_FMA(words(6),tendency,old_product)
        END SELECT
        qnc_value=numerator/new_factor
        IF (qnc_bad_result(dt_tendency) .OR. qnc_bad_result(old_product) .OR. &
            qnc_bad_result(numerator) .OR. qnc_bad_result(qnc_value)) THEN
          all_positive=0_C_INT
          RETURN
        END IF
        index=axis_mode*24+rk_mode+1
        predicted_bits(index)=TRANSFER(qnc_value,0_C_INT32_T)
        IF (qnc_value<=0.0_C_FLOAT) all_positive=0_C_INT
      END DO
    END DO
    status=1_C_INT
  END SUBROUTINE qnc_live_guard_predict_f32
END MODULE qnc_live_guard_f32_probe
