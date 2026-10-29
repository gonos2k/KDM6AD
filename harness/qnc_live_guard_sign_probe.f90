! A numerical sign certificate for the RK3 QNC numerator on saved f32 words.
! This does not identify a physical particle-number measure or select a scale.
MODULE qnc_live_guard_sign_probe
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_FLOAT, C_DOUBLE, C_INT, C_INT32_T
  USE, INTRINSIC :: IEEE_ARITHMETIC, ONLY: IEEE_IS_FINITE, IEEE_NEAREST, &
       IEEE_SUPPORT_ROUNDING
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: qnc_sign_certificate_f32
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
  LOGICAL FUNCTION qnc_f32_subnormal(value)
    REAL(C_FLOAT), INTENT(IN) :: value
    INTEGER(C_INT32_T) :: bits
    bits=TRANSFER(value,0_C_INT32_T)
    qnc_f32_subnormal=IAND(bits,INT(Z'7F800000',C_INT32_T))==0 .AND. &
         IAND(bits,INT(Z'007FFFFF',C_INT32_T))/=0
  END FUNCTION qnc_f32_subnormal

  SUBROUTINE qnc_sign_certificate_f32(words, mu_new, scalar_source, residual, bound, verdict) &
       BIND(C, NAME='qnc_sign_certificate_f32')
    REAL(C_FLOAT), INTENT(IN) :: words(26), mu_new, scalar_source
    REAL(C_DOUBLE), INTENT(OUT) :: residual, bound
    INTEGER(C_INT), INTENT(OUT) :: verdict
    REAL(C_DOUBLE) :: x(26), mn, src, terms(16), sum_abs, unit_roundoff, gamma
    INTEGER :: n

    verdict=0
    residual=0.0_C_DOUBLE
    bound=0.0_C_DOUBLE
    IF (STORAGE_SIZE(0.0_C_FLOAT)/=32 .OR. RADIX(0.0_C_FLOAT)/=2 .OR. &
        DIGITS(0.0_C_FLOAT)/=24 .OR. MAXEXPONENT(0.0_C_FLOAT)/=128 .OR. &
        STORAGE_SIZE(0.0_C_DOUBLE)/=64 .OR. RADIX(0.0_C_DOUBLE)/=2 .OR. &
        DIGITS(0.0_C_DOUBLE)/=53 .OR. MAXEXPONENT(0.0_C_DOUBLE)/=1024) RETURN
    IF (.NOT.IEEE_SUPPORT_ROUNDING(IEEE_NEAREST,1.0_C_DOUBLE)) RETURN
    IF (qnc_rounding_is_nearest()/=1_C_INT) RETURN
    IF (qnc_gradual_underflow_enabled()/=1_C_INT) RETURN
    IF (.NOT.IEEE_IS_FINITE(mu_new) .OR. .NOT.IEEE_IS_FINITE(scalar_source) .OR. &
        qnc_f32_subnormal(mu_new) .OR. qnc_f32_subnormal(scalar_source)) RETURN
    DO n=1,26
      IF (.NOT.IEEE_IS_FINITE(words(n)) .OR. qnc_f32_subnormal(words(n))) RETURN
      x(n)=REAL(words(n),C_DOUBLE)
    END DO
    mn=REAL(mu_new,C_DOUBLE)
    src=REAL(scalar_source,C_DOUBLE)
    ! RDZW is negative on the recorded native vertical coordinate; reject
    ! zero, not a valid negative orientation.
    IF (x(7)<=0.0_C_DOUBLE .OR. x(8)<=0.0_C_DOUBLE .OR. &
        x(9)<=0.0_C_DOUBLE .OR. x(10)<=0.0_C_DOUBLE .OR. &
        x(11)==0.0_C_DOUBLE .OR. x(6)<=0.0_C_DOUBLE) RETURN
    IF (x(2)*(x(4)+x(5))+x(3)<=0.0_C_DOUBLE .OR. &
        x(2)*(mn+x(5))+x(3)<=0.0_C_DOUBLE) RETURN

    ! Expand the source-equivalent exact expression into 16 signed monomials.
    ! Input words map to FIELD_OLD,C1H,C2H,MU_OLD,MU_BASE,DT,MSFTX,MSFTY,
    ! RDX,RDY,RDZW,PH_LOW,FLUX_OUT,SCALE, six LOW and six POST faces.
    terms(1)=x(2)*x(4)*x(1)
    terms(2)=x(2)*x(5)*x(1)
    terms(3)=x(3)*x(1)
    terms(4)=x(6)*src
    terms(5)=-x(6)*x(8)*x(11)*x(20)
    terms(6)= x(6)*x(8)*x(11)*x(19)
    terms(7)=-x(6)*x(8)*x(11)*x(26)
    terms(8)= x(6)*x(8)*x(11)*x(25)
    terms(9)=-x(6)*x(8)*x(7)*x(9)*x(16)
    terms(10)=x(6)*x(8)*x(7)*x(9)*x(15)
    terms(11)=-x(6)*x(8)*x(7)*x(9)*x(22)
    terms(12)=x(6)*x(8)*x(7)*x(9)*x(21)
    terms(13)=-x(6)*x(8)*x(7)*x(10)*x(18)
    terms(14)=x(6)*x(8)*x(7)*x(10)*x(17)
    terms(15)=-x(6)*x(8)*x(7)*x(10)*x(24)
    terms(16)=x(6)*x(8)*x(7)*x(10)*x(23)
    IF (.NOT.ALL(IEEE_IS_FINITE(terms))) RETURN

    residual=SUM(terms)
    sum_abs=SUM(ABS(terms))
    IF (.NOT.IEEE_IS_FINITE(residual) .OR. .NOT.IEEE_IS_FINITE(sum_abs)) RETURN
    unit_roundoff=EPSILON(1.0_C_DOUBLE)/2.0_C_DOUBLE
    gamma=(256.0_C_DOUBLE*unit_roundoff)/(1.0_C_DOUBLE-256.0_C_DOUBLE*unit_roundoff)
    ! Every nonzero monomial has at most five normal f32 factors, so its
    ! exact magnitude stays in binary64's normal range; 16 such terms also
    ! cannot overflow binary64. Two times gamma covers downward rounding
    ! of SUM(ABS) and bound construction. Inconclusive values fail closed.
    bound=2.0_C_DOUBLE*gamma*sum_abs/(1.0_C_DOUBLE-gamma)
    IF (.NOT.IEEE_IS_FINITE(bound)) RETURN
    IF (residual>bound) THEN
      verdict=1
    ELSE IF (residual< -bound) THEN
      verdict=-1
    END IF
  END SUBROUTINE qnc_sign_certificate_f32
END MODULE qnc_live_guard_sign_probe
