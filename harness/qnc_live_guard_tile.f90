! Opt-in selected-54 QNC face-scale pilot for the pinned PR475 tile layout.
! This is a numerical research rule, not a physical particle-number claim.
MODULE qnc_live_guard_tile
  USE, INTRINSIC :: ISO_C_BINDING, ONLY: C_FLOAT, C_DOUBLE, C_INT, C_INT32_T
  USE, INTRINSIC :: IEEE_ARITHMETIC, ONLY: IEEE_IS_FINITE
  USE qnc_live_guard_sign_probe, ONLY: qnc_sign_certificate_f32
  USE qnc_live_guard_f32_probe, ONLY: qnc_live_guard_predict_f32
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER, PUBLIC :: QNC_LIVE_GUARD_NDONOR=54
  INTEGER, PARAMETER, PUBLIC :: QNC_LIVE_GUARD_NTARGET=382
  INTEGER, PARAMETER :: QNC_LIVE_GUARD_MAX_ULP=16
  INTEGER, PARAMETER :: QNC_LIVE_GUARD_MAX_FACE=6*QNC_LIVE_GUARD_NDONOR
  CHARACTER(LEN=*), PARAMETER :: QNC_LIVE_GUARD_COORD_SHA = &
       '9813c6b79b087233c61e348e92cc394f8a66d952da81cd5c821895a5eeae1536'

  INTEGER, PARAMETER :: DONOR_I(QNC_LIVE_GUARD_NDONOR)=(/ &
       57,70,91,107,108,112,113,120,133,134,137,150, &
       152,153,155,155,176,180,189,190,191,192,192,193, &
       195,196,196,198,201,202,202,202,205,208,208,209, &
       209,210,210,212,212,214,222,222,223,225,226,226, &
       227,228,229,229,230,231 /)
  INTEGER, PARAMETER :: DONOR_K(QNC_LIVE_GUARD_NDONOR)=(/ &
       4,5,4,8,8,11,12,13,11,15,15,9, &
       11,4,13,15,14,4,4,14,4,4,10,17, &
       11,4,9,4,5,4,5,18,4,4,18,4, &
       7,4,4,4,11,15,4,8,4,19,4,11, &
       12,4,5,8,13,4 /)
  INTEGER, PARAMETER :: DONOR_J(QNC_LIVE_GUARD_NDONOR)=(/ &
       159,180,94,131,98,242,70,94,152,96,100,268, &
       268,111,115,120,155,121,228,111,124,136,128,153, &
       131,229,167,232,250,207,252,111,197,193,113,198, &
       190,199,217,203,155,181,193,184,194,205,188,188, &
       148,214,234,166,132,252 /)

  INTEGER, PARAMETER :: SEAM_I(8)=(/113,113,116,116,131,131,198,198/)
  INTEGER, PARAMETER :: SEAM_K(8)=(/12,12,6,6,8,8,12,12/)
  INTEGER, PARAMETER :: SEAM_J(8)=(/142,143,142,143,142,143,142,143/)

  INTEGER, SAVE :: TARGET_I(QNC_LIVE_GUARD_NTARGET)
  INTEGER, SAVE :: TARGET_K(QNC_LIVE_GUARD_NTARGET)
  INTEGER, SAVE :: TARGET_J(QNC_LIVE_GUARD_NTARGET)
  INTEGER, SAVE :: DONOR_TARGET(QNC_LIVE_GUARD_NDONOR)
  LOGICAL, SAVE :: TARGETS_READY=.FALSE.
  LOGICAL, SAVE :: CONTEXT_ACTIVE=.FALSE.
  INTEGER, SAVE :: LAST_FAILURE_TARGET=0
  LOGICAL, SAVE :: TARGET_PREDICTED(QNC_LIVE_GUARD_NTARGET)=.FALSE.
  REAL(C_FLOAT), SAVE :: SOURCE_CONTEXT(QNC_LIVE_GUARD_NTARGET)=0.0_C_FLOAT
  REAL(C_FLOAT), SAVE :: MU_NEW_CONTEXT(QNC_LIVE_GUARD_NTARGET)=0.0_C_FLOAT
  INTEGER(C_INT32_T), SAVE :: PREDICTED_BITS(192,QNC_LIVE_GUARD_NTARGET)=0_C_INT32_T

  PUBLIC :: qnc_live_guard_set_context
  PUBLIC :: qnc_live_guard_clear_context
  PUBLIC :: qnc_live_guard_is_active
  PUBLIC :: qnc_live_guard_apply_tile
  PUBLIC :: qnc_live_guard_check_tile
  PUBLIC :: qnc_live_guard_target_coord
  PUBLIC :: qnc_live_guard_apply_compact
  PUBLIC :: qnc_live_guard_receiver_failure_ok
CONTAINS
  SUBROUTINE qnc_set_failure(status,code,target_index)
    INTEGER(C_INT), INTENT(OUT) :: status
    INTEGER(C_INT), INTENT(IN) :: code
    INTEGER, INTENT(IN) :: target_index
    status=code
    LAST_FAILURE_TARGET=target_index
  END SUBROUTINE qnc_set_failure

  SUBROUTINE qnc_report_reject(tile_id,status)
    INTEGER, INTENT(IN) :: tile_id
    INTEGER(C_INT), INTENT(IN) :: status
    IF (status<0_C_INT) WRITE(*,*) 'QNC_LIVE_GUARD_REJECT',tile_id,status,LAST_FAILURE_TARGET
  END SUBROUTINE qnc_report_reject

  LOGICAL FUNCTION qnc_env_is_one(name)
    CHARACTER(LEN=*), INTENT(IN) :: name
    CHARACTER(LEN=64) :: value
    INTEGER :: env_status, env_length
    value=' '
    CALL GET_ENVIRONMENT_VARIABLE(name,value,length=env_length,status=env_status)
    qnc_env_is_one=env_status==0 .AND. TRIM(value)=='1'
  END FUNCTION qnc_env_is_one

  SUBROUTINE qnc_add_coord(coords,n,i,k,j)
    INTEGER, INTENT(INOUT) :: coords(3,386),n
    INTEGER, INTENT(IN) :: i,k,j
    INTEGER :: p
    DO p=1,n
      IF (coords(1,p)==i .AND. coords(2,p)==k .AND. coords(3,p)==j) RETURN
    END DO
    n=n+1
    IF (n>SIZE(coords,2)) RETURN
    coords(:,n)=(/i,k,j/)
  END SUBROUTINE qnc_add_coord

  SUBROUTINE qnc_build_targets(status)
    INTEGER(C_INT), INTENT(OUT) :: status
    INTEGER :: coords(3,386),n,p,q,ii,kk,jj,tmp(3),donor,found
    INTEGER, PARAMETER :: DI(6)=(/-1,1,0,0,0,0/)
    INTEGER, PARAMETER :: DK(6)=(/0,0,0,0,-1,1/)
    INTEGER, PARAMETER :: DJ(6)=(/0,0,-1,1,0,0/)
    status=-100_C_INT
    LAST_FAILURE_TARGET=0
    IF (TARGETS_READY) THEN
      status=1_C_INT
      RETURN
    END IF
    coords=0
    n=0
    DO donor=1,QNC_LIVE_GUARD_NDONOR
      ii=DONOR_I(donor); kk=DONOR_K(donor); jj=DONOR_J(donor)
      CALL qnc_add_coord(coords,n,ii,kk,jj)
      DO p=1,6
        CALL qnc_add_coord(coords,n,ii+DI(p),kk+DK(p),jj+DJ(p))
      END DO
    END DO
    DO p=1,8
      CALL qnc_add_coord(coords,n,SEAM_I(p),SEAM_K(p),SEAM_J(p))
    END DO
    IF (n/=QNC_LIVE_GUARD_NTARGET) RETURN

    ! The sorted (i,k,j) order is the pinned PR475 QNC_PREF_I/K/J order.
    DO p=1,n-1
      DO q=p+1,n
        IF (coords(1,q)<coords(1,p) .OR. &
            (coords(1,q)==coords(1,p) .AND. coords(2,q)<coords(2,p)) .OR. &
            (coords(1,q)==coords(1,p) .AND. coords(2,q)==coords(2,p) .AND. &
             coords(3,q)<coords(3,p))) THEN
          tmp=coords(:,p); coords(:,p)=coords(:,q); coords(:,q)=tmp
        END IF
      END DO
    END DO
    TARGET_I=coords(1,1:n)
    TARGET_K=coords(2,1:n)
    TARGET_J=coords(3,1:n)
    DO donor=1,QNC_LIVE_GUARD_NDONOR
      found=0
      DO p=1,n
        IF (TARGET_I(p)==DONOR_I(donor) .AND. TARGET_K(p)==DONOR_K(donor) .AND. &
            TARGET_J(p)==DONOR_J(donor)) THEN
          found=p
          EXIT
        END IF
      END DO
      IF (found==0) RETURN
      DONOR_TARGET(donor)=found
    END DO
    TARGETS_READY=.TRUE.
    status=1_C_INT
  END SUBROUTINE qnc_build_targets

  SUBROUTINE qnc_live_guard_target_coord(index,i,k,j) BIND(C,NAME='qnc_live_guard_target_coord')
    INTEGER(C_INT), VALUE, INTENT(IN) :: index
    INTEGER(C_INT), INTENT(OUT) :: i,k,j
    INTEGER(C_INT) :: status
    i=0_C_INT; k=0_C_INT; j=0_C_INT
    CALL qnc_build_targets(status)
    IF (status/=1_C_INT .OR. index<1 .OR. index>QNC_LIVE_GUARD_NTARGET) RETURN
    i=INT(TARGET_I(index),C_INT)
    k=INT(TARGET_K(index),C_INT)
    j=INT(TARGET_J(index),C_INT)
  END SUBROUTINE qnc_live_guard_target_coord

  LOGICAL FUNCTION qnc_live_guard_is_active()
    qnc_live_guard_is_active=CONTEXT_ACTIVE
  END FUNCTION qnc_live_guard_is_active

  SUBROUTINE qnc_live_guard_clear_context()
    CONTEXT_ACTIVE=.FALSE.
    TARGET_PREDICTED=.FALSE.
    PREDICTED_BITS=0_C_INT32_T
    SOURCE_CONTEXT=0.0_C_FLOAT
    MU_NEW_CONTEXT=0.0_C_FLOAT
  END SUBROUTINE qnc_live_guard_clear_context

  SUBROUTINE qnc_live_guard_set_context(source,mu_new,ims,ime,kms,kme,jms,jme, &
       ids,ide,jds,jde,kds,kde,nranks,nthreads,status)
    INTEGER, INTENT(IN) :: ims,ime,kms,kme,jms,jme,ids,ide,jds,jde,kds,kde
    INTEGER, INTENT(IN) :: nranks,nthreads
    REAL, INTENT(IN) :: source(ims:ime,kms:kme,jms:jme)
    REAL, INTENT(IN) :: mu_new(ims:ime,jms:jme)
    INTEGER(C_INT), INTENT(OUT) :: status
    INTEGER(C_INT) :: coord_status
    INTEGER :: n,i,k,j

    CONTEXT_ACTIVE=.FALSE.
    TARGET_PREDICTED=.FALSE.
    status=0_C_INT
    IF (.NOT.qnc_env_is_one('KDM6AD_QNC_LIVE_GUARD')) RETURN
    IF (.NOT.qnc_env_is_one('OMP_NUM_THREADS') .OR. &
        .NOT.qnc_env_is_one('MKL_NUM_THREADS') .OR. &
        .NOT.qnc_env_is_one('OMP_THREAD_LIMIT') .OR. &
        .NOT.qnc_env_is_one('VECLIB_MAXIMUM_THREADS')) THEN
      status=-1_C_INT
      RETURN
    END IF
    IF (nranks/=1 .OR. nthreads/=1 .OR. STORAGE_SIZE(0.0)/=32) THEN
      status=-2_C_INT
      RETURN
    END IF
    IF (ids/=1 .OR. ide/=235 .OR. jds/=1 .OR. jde/=283 .OR. &
        kds/=1 .OR. kde/=40) THEN
      status=-3_C_INT
      RETURN
    END IF
    CALL qnc_build_targets(coord_status)
    IF (coord_status/=1_C_INT) THEN
      status=-4_C_INT
      RETURN
    END IF
    DO n=1,QNC_LIVE_GUARD_NTARGET
      i=TARGET_I(n); k=TARGET_K(n); j=TARGET_J(n)
      IF (i<ims .OR. i>ime .OR. k<kms .OR. k>kme .OR. j<jms .OR. j>jme) THEN
        status=-5_C_INT
        RETURN
      END IF
      SOURCE_CONTEXT(n)=REAL(source(i,k,j),C_FLOAT)
      MU_NEW_CONTEXT(n)=REAL(mu_new(i,j),C_FLOAT)
    END DO
    CONTEXT_ACTIVE=.TRUE.
    status=1_C_INT
  END SUBROUTINE qnc_live_guard_set_context

  INTEGER FUNCTION qnc_find_target(i,k,j) RESULT(index)
    INTEGER, INTENT(IN) :: i,k,j
    INTEGER :: n
    index=0
    DO n=1,QNC_LIVE_GUARD_NTARGET
      IF (TARGET_I(n)==i .AND. TARGET_K(n)==k .AND. TARGET_J(n)==j) THEN
        index=n
        RETURN
      END IF
    END DO
  END FUNCTION qnc_find_target

  SUBROUTINE qnc_pack_words(index,field_old,c1,c2,mu_old,mu_base,msftx,msfty, &
       rdx,rdy,rdzw,dt,scale,ph_low,flux_out,low_faces,post_faces,words)
    INTEGER, INTENT(IN) :: index
    REAL(C_FLOAT), INTENT(IN) :: field_old,c1,c2,mu_old,mu_base,msftx,msfty
    REAL(C_FLOAT), INTENT(IN) :: rdx,rdy,rdzw,dt,scale,ph_low,flux_out
    REAL(C_FLOAT), INTENT(IN) :: low_faces(6),post_faces(6)
    REAL(C_FLOAT), INTENT(OUT) :: words(26)
    words(1:14)=(/field_old,c1,c2,mu_old,mu_base,dt,msftx,msfty, &
         rdx,rdy,rdzw,ph_low,flux_out,scale/)
    words(15:20)=low_faces
    words(21:26)=post_faces
  END SUBROUTINE qnc_pack_words

  SUBROUTINE qnc_eval(words,mu_new,source,verdict,all_positive,predicted,status)
    REAL(C_FLOAT), INTENT(IN) :: words(26)
    REAL(C_FLOAT), INTENT(IN) :: mu_new,source
    INTEGER(C_INT), INTENT(OUT) :: verdict,all_positive,status
    INTEGER(C_INT32_T), INTENT(OUT) :: predicted(192)
    REAL(C_DOUBLE) :: residual,bound
    CALL qnc_sign_certificate_f32(words,mu_new,source,residual,bound,verdict)
    CALL qnc_live_guard_predict_f32(words,mu_new,source,predicted,all_positive,status)
  END SUBROUTINE qnc_eval

  LOGICAL FUNCTION qnc_local_cell(index,tile_id,ids,ide,jds,jde,kds,kde)
    INTEGER, INTENT(IN) :: index,tile_id,ids,ide,jds,jde,kds,kde
    INTEGER :: jmax
    qnc_local_cell=.FALSE.
    IF (tile_id==1) THEN
      jmax=142
    ELSE
      jmax=jde-1
    END IF
    IF (tile_id==1) THEN
      qnc_local_cell=TARGET_I(index)>=ids .AND. TARGET_I(index)<=ide-1 .AND. &
           TARGET_J(index)>=jds .AND. TARGET_J(index)<=jmax .AND. &
           TARGET_K(index)>=kds .AND. TARGET_K(index)<=kde-1
    ELSE
      qnc_local_cell=TARGET_I(index)>=ids .AND. TARGET_I(index)<=ide-1 .AND. &
           TARGET_J(index)>=143 .AND. TARGET_J(index)<=jmax .AND. &
           TARGET_K(index)>=kds .AND. TARGET_K(index)<=kde-1
    END IF
  END FUNCTION qnc_local_cell

  SUBROUTINE qnc_apply_compact_core(words,pre_faces,pre_seen,scale,hit,source,mu_new, &
       tile_id,candidate_words,selected_scale,nulp,status,donor_count, &
       predicted_bits,predicted_valid)
    REAL(C_FLOAT), INTENT(IN) :: words(26,QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(IN) :: pre_faces(6,QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT), INTENT(IN) :: pre_seen(QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(INOUT) :: scale(QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT), INTENT(IN) :: hit(QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(IN) :: source(QNC_LIVE_GUARD_NTARGET),mu_new(QNC_LIVE_GUARD_NTARGET)
    INTEGER, INTENT(IN) :: tile_id
    REAL(C_FLOAT), INTENT(OUT) :: candidate_words(26,QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(OUT) :: selected_scale(QNC_LIVE_GUARD_NDONOR)
    INTEGER(C_INT), INTENT(OUT) :: nulp(QNC_LIVE_GUARD_NDONOR),status,donor_count
    INTEGER(C_INT32_T), INTENT(OUT) :: predicted_bits(192,QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT), INTENT(OUT) :: predicted_valid(QNC_LIVE_GUARD_NTARGET)

    REAL(C_FLOAT) :: trial_words(26),chosen_words(26),trial_scale,orig_scale,trial_pre
    REAL(C_FLOAT) :: face_value
    INTEGER(C_INT32_T) :: orig_bits,trial_bits,trial_predictions(192),base_predictions(192)
    INTEGER(C_INT) :: base_verdict,base_all_positive,base_status,trial_verdict,trial_all_positive
    INTEGER(C_INT) :: trial_status,cand_verdict,cand_all_positive,cand_status
    INTEGER(C_INT32_T) :: cand_predictions(192)
    INTEGER :: n,donor,didx,neighbor_idx,face,opp,ii,kk,jj,axis,fi,fk,fj,used
    INTEGER :: face_axis(QNC_LIVE_GUARD_MAX_FACE),face_i(QNC_LIVE_GUARD_MAX_FACE)
    INTEGER :: face_k(QNC_LIVE_GUARD_MAX_FACE),face_j(QNC_LIVE_GUARD_MAX_FACE)
    REAL(C_FLOAT) :: face_words(QNC_LIVE_GUARD_MAX_FACE)
    LOGICAL :: local_mask(QNC_LIVE_GUARD_NTARGET),baseline_failed(QNC_LIVE_GUARD_NTARGET)
    LOGICAL :: donor_mask(QNC_LIVE_GUARD_NTARGET),found
    INTEGER, PARAMETER :: OFF_I(6)=(/ -1,1,0,0,0,0 /)
    INTEGER, PARAMETER :: OFF_K(6)=(/ 0,0,0,0,-1,1 /)
    INTEGER, PARAMETER :: OFF_J(6)=(/ 0,0,-1,1,0,0 /)
    INTEGER, PARAMETER :: OPP_FACE(6)=(/ 2,1,4,3,6,5 /)

    status=-100_C_INT
    LAST_FAILURE_TARGET=0
    donor_count=0_C_INT
    nulp=-1_C_INT
    selected_scale=1.0_C_FLOAT
    candidate_words=words
    predicted_bits=0_C_INT32_T
    predicted_valid=0_C_INT
    face_axis=0; face_i=0; face_k=0; face_j=0; face_words=0.0_C_FLOAT
    baseline_failed=.FALSE.; donor_mask=.FALSE.; local_mask=.FALSE.
    IF (tile_id/=1 .AND. tile_id/=2) THEN
      CALL qnc_set_failure(status,-100_C_INT,0)
      RETURN
    END IF

    DO n=1,QNC_LIVE_GUARD_NTARGET
      local_mask(n)=qnc_local_cell(n,tile_id,1,235,1,283,1,40)
      IF (local_mask(n) .NEQV. (pre_seen(n)==1_C_INT)) THEN
        CALL qnc_set_failure(status,-101_C_INT,n)
        RETURN
      END IF
      IF (.NOT.local_mask(n)) CYCLE
      IF (hit(n)/=0_C_INT .AND. hit(n)/=1_C_INT) THEN
        CALL qnc_set_failure(status,-102_C_INT,n)
        RETURN
      END IF
      IF (.NOT.IEEE_IS_FINITE(scale(n)) .OR. .NOT.IEEE_IS_FINITE(source(n)) .OR. &
          .NOT.IEEE_IS_FINITE(mu_new(n))) THEN
        CALL qnc_set_failure(status,-103_C_INT,n)
        RETURN
      END IF
      CALL qnc_eval(words(:,n),mu_new(n),source(n),base_verdict,base_all_positive, &
           base_predictions,base_status)
      IF (base_status/=1_C_INT) THEN
        CALL qnc_set_failure(status,-104_C_INT,n)
        RETURN
      END IF
      baseline_failed(n)=base_verdict/=1_C_INT .OR. base_all_positive/=1_C_INT
      predicted_bits(:,n)=base_predictions
      predicted_valid(n)=1_C_INT
    END DO

    ! Scan all selected donors owned by this tile, each from immutable PRE and
    ! the untouched baseline POST row.  No monotonicity assumption is used.
    DO donor=1,QNC_LIVE_GUARD_NDONOR
      didx=DONOR_TARGET(donor)
      IF (.NOT.local_mask(didx)) CYCLE
      donor_count=donor_count+1_C_INT
      donor_mask(didx)=.TRUE.
      IF (hit(didx)/=1_C_INT) THEN
        WRITE(*,*) 'QNC_LIVE_GUARD_HIT',tile_id,didx,hit(didx), &
             TRANSFER(words(12,didx),0_C_INT32_T), &
             TRANSFER(words(13,didx),0_C_INT32_T), &
             TRANSFER(scale(didx),0_C_INT32_T),pre_seen(didx)
        WRITE(*,'(A,1X,I0,1X,26(Z8.8,1X))') 'QNC_LIVE_GUARD_ROW',didx, &
             TRANSFER(words(:,didx),(/0_C_INT32_T/),26)
        WRITE(*,'(A,1X,2(Z8.8,1X))') 'QNC_LIVE_GUARD_CONTEXT', &
             TRANSFER(source(didx),0_C_INT32_T),TRANSFER(mu_new(didx),0_C_INT32_T)
        CALL qnc_set_failure(status,-105_C_INT,didx)
        RETURN
      END IF
      orig_scale=scale(didx)
      orig_bits=TRANSFER(orig_scale,0_C_INT32_T)
      IF (orig_bits<=0_C_INT32_T .OR. orig_scale>=1.0_C_FLOAT) THEN
        CALL qnc_set_failure(status,-106_C_INT,didx)
        RETURN
      END IF
      found=.FALSE.
      DO n=0,QNC_LIVE_GUARD_MAX_ULP
        trial_bits=orig_bits-INT(n,C_INT32_T)
        IF (trial_bits<=0_C_INT32_T) EXIT
        trial_scale=TRANSFER(trial_bits,0.0_C_FLOAT)
        trial_words=words(:,didx)
        trial_words(14)=trial_scale
        DO face=1,6
          trial_pre=pre_faces(face,didx)
          IF (qnc_face_outgoing(face,trial_pre)) trial_words(20+face)=trial_pre*trial_scale
        END DO
        CALL qnc_eval(trial_words,mu_new(didx),source(didx),trial_verdict,trial_all_positive, &
             trial_predictions,trial_status)
        IF (trial_status/=1_C_INT) CYCLE
        IF (trial_verdict==1_C_INT .AND. trial_all_positive==1_C_INT) THEN
          found=.TRUE.
          nulp(donor)=INT(n,C_INT)
          selected_scale(donor)=trial_scale
          EXIT
        END IF
      END DO
      IF (.NOT.found) THEN
        CALL qnc_set_failure(status,-107_C_INT,didx)
        RETURN
      END IF
    END DO
    IF (donor_count==0_C_INT) THEN
      status=1_C_INT
      RETURN
    END IF

    ! Stage all sign-selected outfaces and their receiver incidences before
    ! validating any final receiver.  The physical face key has one owner.
    used=0
    DO donor=1,QNC_LIVE_GUARD_NDONOR
      didx=DONOR_TARGET(donor)
      IF (.NOT.local_mask(didx)) CYCLE
      trial_scale=selected_scale(donor)
      DO face=1,6
        trial_pre=pre_faces(face,didx)
        IF (.NOT.qnc_face_outgoing(face,trial_pre)) CYCLE
        ii=TARGET_I(didx)+OFF_I(face)
        kk=TARGET_K(didx)+OFF_K(face)
        jj=TARGET_J(didx)+OFF_J(face)
        neighbor_idx=qnc_find_target(ii,kk,jj)
        IF (neighbor_idx==0) THEN
          CALL qnc_set_failure(status,-108_C_INT,didx)
          RETURN
        END IF
        IF (.NOT.local_mask(neighbor_idx)) THEN
          CALL qnc_set_failure(status,-108_C_INT,didx)
          RETURN
        END IF
        opp=OPP_FACE(face)
        IF (TRANSFER(trial_pre,0_C_INT32_T)/= &
            TRANSFER(pre_faces(opp,neighbor_idx),0_C_INT32_T)) THEN
          CALL qnc_set_failure(status,-109_C_INT,didx)
          RETURN
        END IF
        IF (TRANSFER(words(20+face,didx),0_C_INT32_T)/= &
            TRANSFER(words(20+opp,neighbor_idx),0_C_INT32_T)) THEN
          CALL qnc_set_failure(status,-110_C_INT,didx)
          RETURN
        END IF
        face_value=trial_pre*trial_scale
        axis=1; fi=TARGET_I(didx); fk=TARGET_K(didx); fj=TARGET_J(didx)
        IF (face==2) fi=fi+1
        IF (face==3) THEN
          axis=2; fj=fj
        ELSE IF (face==4) THEN
          axis=2; fj=fj+1
        ELSE IF (face==5) THEN
          axis=3; fk=fk
        ELSE IF (face==6) THEN
          axis=3; fk=fk+1
        END IF
        DO n=1,used
          IF (face_axis(n)==axis .AND. face_i(n)==fi .AND. &
              face_k(n)==fk .AND. face_j(n)==fj) THEN
            CALL qnc_set_failure(status,-111_C_INT,didx)
            RETURN
          END IF
        END DO
        used=used+1
        IF (used>QNC_LIVE_GUARD_MAX_FACE) THEN
          CALL qnc_set_failure(status,-112_C_INT,didx)
          RETURN
        END IF
        face_axis(used)=axis; face_i(used)=fi; face_k(used)=fk
        face_j(used)=fj; face_words(used)=face_value
        candidate_words(20+face,didx)=face_value
        candidate_words(20+opp,neighbor_idx)=face_value
      END DO
    END DO

    ! Re-evaluate each affected local cell after the complete local map.  An
    ! existing baseline failure is allowed; a new one is not.  Selected
    ! donors must all pass after combination.
    DO n=1,QNC_LIVE_GUARD_NTARGET
      IF (.NOT.local_mask(n)) CYCLE
      CALL qnc_eval(candidate_words(:,n),mu_new(n),source(n),cand_verdict,cand_all_positive, &
           cand_predictions,cand_status)
      IF (cand_status/=1_C_INT) THEN
        CALL qnc_set_failure(status,-113_C_INT,n)
        RETURN
      END IF
      IF (donor_mask(n)) THEN
        IF (cand_verdict/=1_C_INT .OR. cand_all_positive/=1_C_INT) THEN
          CALL qnc_set_failure(status,-114_C_INT,n)
          RETURN
        END IF
      ELSE IF (cand_verdict/=1_C_INT .OR. cand_all_positive/=1_C_INT) THEN
        IF (qnc_live_guard_receiver_failure_ok(words(:,n),candidate_words(:,n), &
             MERGE(1_C_INT,0_C_INT,baseline_failed(n)),1_C_INT)/=1_C_INT) THEN
          CALL qnc_set_failure(status,-115_C_INT,n)
          RETURN
        END IF
      END IF
      predicted_bits(:,n)=cand_predictions
    END DO
    status=1_C_INT
  END SUBROUTINE qnc_apply_compact_core

  INTEGER(C_INT) FUNCTION qnc_live_guard_receiver_failure_ok(before,after, &
       baseline_failed,candidate_failed) BIND(C,NAME='qnc_live_guard_receiver_failure_ok')
    REAL(C_FLOAT), INTENT(IN) :: before(26),after(26)
    INTEGER(C_INT), VALUE, INTENT(IN) :: baseline_failed,candidate_failed
    INTEGER(C_INT32_T) :: before_bits(26),after_bits(26)
    qnc_live_guard_receiver_failure_ok=0_C_INT
    IF (candidate_failed==0_C_INT) THEN
      qnc_live_guard_receiver_failure_ok=1_C_INT
      RETURN
    END IF
    IF (baseline_failed==0_C_INT) RETURN
    before_bits=TRANSFER(before,before_bits)
    after_bits=TRANSFER(after,after_bits)
    IF (ALL(before_bits==after_bits)) qnc_live_guard_receiver_failure_ok=1_C_INT
  END FUNCTION qnc_live_guard_receiver_failure_ok

  LOGICAL FUNCTION qnc_face_outgoing(face,value)
    INTEGER, INTENT(IN) :: face
    REAL(C_FLOAT), INTENT(IN) :: value
    SELECT CASE(face)
    CASE(1,3)
      qnc_face_outgoing=value<0.0_C_FLOAT
    CASE(2,4,5)
      qnc_face_outgoing=value>0.0_C_FLOAT
    CASE(6)
      qnc_face_outgoing=value<0.0_C_FLOAT
    CASE DEFAULT
      qnc_face_outgoing=.FALSE.
    END SELECT
  END FUNCTION qnc_face_outgoing

  SUBROUTINE qnc_live_guard_apply_compact(words,pre_faces,pre_seen,scale,hit,source,mu_new, &
       tile_id,candidate_words,selected_scale,nulp,status,donor_count) &
       BIND(C,NAME='qnc_live_guard_apply_compact')
    REAL(C_FLOAT), INTENT(IN) :: words(26,QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(IN) :: pre_faces(6,QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT), INTENT(IN) :: pre_seen(QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(INOUT) :: scale(QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT), INTENT(IN) :: hit(QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(IN) :: source(QNC_LIVE_GUARD_NTARGET),mu_new(QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT), VALUE, INTENT(IN) :: tile_id
    REAL(C_FLOAT), INTENT(OUT) :: candidate_words(26,QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT), INTENT(OUT) :: selected_scale(QNC_LIVE_GUARD_NDONOR)
    INTEGER(C_INT), INTENT(OUT) :: nulp(QNC_LIVE_GUARD_NDONOR),status,donor_count
    INTEGER(C_INT32_T) :: ignored_predictions(192,QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT) :: ignored_valid(QNC_LIVE_GUARD_NTARGET)
    CALL qnc_build_targets(status)
    IF (status/=1_C_INT) RETURN
    CALL qnc_apply_compact_core(words,pre_faces,pre_seen,scale,hit,source,mu_new,INT(tile_id), &
         candidate_words,selected_scale,nulp,status,donor_count, &
         ignored_predictions,ignored_valid)
  END SUBROUTINE qnc_live_guard_apply_compact

  SUBROUTINE qnc_live_guard_apply_tile(field_old,c1,c2,mu_old,mu_base,msftx,msfty, &
       rdx,rdy,rdzw,dt,pre_faces,pre_seen,scale,hit,ph_low,flux_out, &
       fqxl,fqyl,fqzl,fqx,fqy,fqz,ids,ide,jds,jde,kds,kde, &
       ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte,status,nulp,local_donors)
    INTEGER, INTENT(IN) :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme
    INTEGER, INTENT(IN) :: its,ite,jts,jte,kts,kte
    REAL, INTENT(IN) :: field_old(ims:ime,kms:kme,jms:jme)
    REAL, INTENT(IN) :: c1(kms:kme),c2(kms:kme),mu_old(ims:ime,jms:jme)
    REAL, INTENT(IN) :: mu_base(ims:ime,jms:jme),msftx(ims:ime,jms:jme),msfty(ims:ime,jms:jme)
    REAL, INTENT(IN) :: rdx,rdy,rdzw(kms:kme),dt
    REAL, INTENT(IN) :: pre_faces(6,QNC_LIVE_GUARD_NTARGET)
    LOGICAL, INTENT(IN) :: pre_seen(QNC_LIVE_GUARD_NTARGET)
    REAL, INTENT(INOUT) :: scale(QNC_LIVE_GUARD_NTARGET)
    INTEGER, INTENT(IN) :: hit(QNC_LIVE_GUARD_NTARGET)
    REAL, INTENT(IN) :: ph_low(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL, INTENT(IN) :: flux_out(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL, INTENT(IN) :: fqxl(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL, INTENT(IN) :: fqyl(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL, INTENT(IN) :: fqzl(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL, INTENT(INOUT) :: fqx(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL, INTENT(INOUT) :: fqy(its-1:ite+2,kts:kte,jts-1:jte+2)
    REAL, INTENT(INOUT) :: fqz(its-1:ite+2,kts:kte,jts-1:jte+2)
    INTEGER(C_INT), INTENT(OUT) :: status
    INTEGER(C_INT), INTENT(OUT) :: nulp(QNC_LIVE_GUARD_NDONOR),local_donors
    REAL(C_FLOAT) :: words(26,QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT) :: candidate_words(26,QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT) :: compact_pre(6,QNC_LIVE_GUARD_NTARGET),compact_scale(QNC_LIVE_GUARD_NTARGET)
    REAL(C_FLOAT) :: chosen(QNC_LIVE_GUARD_NDONOR)
    INTEGER(C_INT) :: compact_seen(QNC_LIVE_GUARD_NTARGET),compact_hit(QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT) :: predicted_valid(QNC_LIVE_GUARD_NTARGET),donor_count
    INTEGER(C_INT32_T) :: predicted(192,QNC_LIVE_GUARD_NTARGET)
    INTEGER(C_INT) :: core_status
    INTEGER :: n,i,k,j,tile_id,face,donor,didx
    INTEGER, PARAMETER :: FI(6)=(/0,1,0,0,0,0/)
    INTEGER, PARAMETER :: FK(6)=(/0,0,0,0,0,1/)
    INTEGER, PARAMETER :: FJ(6)=(/0,0,0,1,0,0/)

    status=0_C_INT; local_donors=0_C_INT; nulp=-1_C_INT
    IF (.NOT.CONTEXT_ACTIVE) RETURN
    IF (jts==1 .AND. jte==142) THEN
      tile_id=1
    ELSE IF (jts==143 .AND. jte==283) THEN
      tile_id=2
    ELSE
      status=-10_C_INT
      LAST_FAILURE_TARGET=0
      CALL qnc_report_reject(0,status)
      RETURN
    END IF
    IF (ids/=1 .OR. ide/=235 .OR. jds/=1 .OR. jde/=283 .OR. &
        kds/=1 .OR. kde/=40 .OR. its/=1 .OR. ite/=235 .OR. kts/=1 .OR. kte/=40) THEN
      status=-11_C_INT
      LAST_FAILURE_TARGET=0
      CALL qnc_report_reject(tile_id,status)
      RETURN
    END IF

    compact_pre=REAL(pre_faces,C_FLOAT)
    compact_scale=REAL(scale,C_FLOAT)
    compact_hit=INT(hit,C_INT)
    compact_seen=0_C_INT
    DO n=1,QNC_LIVE_GUARD_NTARGET
      IF (pre_seen(n)) compact_seen(n)=1_C_INT
      i=TARGET_I(n); k=TARGET_K(n); j=TARGET_J(n)
      IF (qnc_local_cell(n,tile_id,ids,ide,jds,jde,kds,kde)) THEN
        words(1,n)=REAL(field_old(i,k,j),C_FLOAT)
        words(2,n)=REAL(c1(k),C_FLOAT); words(3,n)=REAL(c2(k),C_FLOAT)
        words(4,n)=REAL(mu_old(i,j),C_FLOAT); words(5,n)=REAL(mu_base(i,j),C_FLOAT)
        words(6,n)=REAL(dt,C_FLOAT); words(7,n)=REAL(msftx(i,j),C_FLOAT)
        words(8,n)=REAL(msfty(i,j),C_FLOAT); words(9,n)=REAL(rdx,C_FLOAT)
        words(10,n)=REAL(rdy,C_FLOAT); words(11,n)=REAL(rdzw(k),C_FLOAT)
        words(12,n)=REAL(ph_low(i,k,j),C_FLOAT); words(13,n)=REAL(flux_out(i,k,j),C_FLOAT)
        words(14,n)=compact_scale(n)
        words(15:20,n)=(/REAL(fqxl(i,k,j),C_FLOAT),REAL(fqxl(i+1,k,j),C_FLOAT), &
             REAL(fqyl(i,k,j),C_FLOAT),REAL(fqyl(i,k,j+1),C_FLOAT), &
             REAL(fqzl(i,k,j),C_FLOAT),REAL(fqzl(i,k+1,j),C_FLOAT)/)
        words(21:26,n)=(/REAL(fqx(i,k,j),C_FLOAT),REAL(fqx(i+1,k,j),C_FLOAT), &
             REAL(fqy(i,k,j),C_FLOAT),REAL(fqy(i,k,j+1),C_FLOAT), &
             REAL(fqz(i,k,j),C_FLOAT),REAL(fqz(i,k+1,j),C_FLOAT)/)
      ELSE
        words(:,n)=0.0_C_FLOAT
      END IF
    END DO
    CALL qnc_apply_compact_core(words,compact_pre,compact_seen,compact_scale,compact_hit, &
         SOURCE_CONTEXT,MU_NEW_CONTEXT,tile_id,candidate_words,chosen,nulp,core_status, &
         donor_count,predicted,predicted_valid)
    status=core_status
    local_donors=donor_count
    IF (core_status/=1_C_INT) THEN
      CALL qnc_report_reject(tile_id,core_status)
      RETURN
    END IF
    IF (donor_count==0_C_INT) RETURN

    ! Commit staged local face words only after the whole tile subset passes.
    DO n=1,QNC_LIVE_GUARD_NTARGET
      IF (.NOT.qnc_local_cell(n,tile_id,ids,ide,jds,jde,kds,kde)) CYCLE
      i=TARGET_I(n); k=TARGET_K(n); j=TARGET_J(n)
      fqx(i,k,j)=REAL(candidate_words(21,n))
      fqx(i+1,k,j)=REAL(candidate_words(22,n))
      fqy(i,k,j)=REAL(candidate_words(23,n))
      fqy(i,k,j+1)=REAL(candidate_words(24,n))
      fqz(i,k,j)=REAL(candidate_words(25,n))
      fqz(i,k+1,j)=REAL(candidate_words(26,n))
      PREDICTED_BITS(:,n)=predicted(:,n)
      TARGET_PREDICTED(n)=.TRUE.
    END DO
    DO donor=1,QNC_LIVE_GUARD_NDONOR
      didx=DONOR_TARGET(donor)
      IF (qnc_local_cell(didx,tile_id,ids,ide,jds,jde,kds,kde)) &
           scale(didx)=REAL(chosen(donor))
    END DO
    status=1_C_INT
  END SUBROUTINE qnc_live_guard_apply_tile

  SUBROUTINE qnc_live_guard_check_tile(actual_qnc,ids,ide,jds,jde,kds,kde, &
       ims,ime,jms,jme,kms,kme,its,ite,jts,jte,kts,kte,status)
    INTEGER, INTENT(IN) :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme
    INTEGER, INTENT(IN) :: its,ite,jts,jte,kts,kte
    REAL, INTENT(IN) :: actual_qnc(ims:ime,kms:kme,jms:jme)
    INTEGER(C_INT), INTENT(OUT) :: status
    INTEGER :: tile_id,n,i,k,j
    INTEGER(C_INT32_T) :: word
    status=0_C_INT
    IF (.NOT.CONTEXT_ACTIVE) RETURN
    IF (jts==1 .AND. jte==142) THEN
      tile_id=1
    ELSE IF (jts==143 .AND. jte==283) THEN
      tile_id=2
    ELSE
      status=-20_C_INT
      RETURN
    END IF
    IF (ids/=1 .OR. ide/=235 .OR. jds/=1 .OR. jde/=283 .OR. &
        kds/=1 .OR. kde/=40 .OR. its/=1 .OR. ite/=235 .OR. kts/=1 .OR. kte/=40) THEN
      status=-21_C_INT
      RETURN
    END IF
    DO n=1,QNC_LIVE_GUARD_NTARGET
      IF (.NOT.qnc_local_cell(n,tile_id,ids,ide,jds,jde,kds,kde)) CYCLE
      IF (.NOT.TARGET_PREDICTED(n)) THEN
        status=-22_C_INT
        RETURN
      END IF
      i=TARGET_I(n); k=TARGET_K(n); j=TARGET_J(n)
      word=TRANSFER(REAL(actual_qnc(i,k,j),C_FLOAT),0_C_INT32_T)
      IF (.NOT.ANY(PREDICTED_BITS(:,n)==word)) THEN
        status=-23_C_INT
        RETURN
      END IF
    END DO
    status=1_C_INT
  END SUBROUTINE qnc_live_guard_check_tile
END MODULE qnc_live_guard_tile
