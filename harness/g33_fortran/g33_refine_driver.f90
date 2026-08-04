! Timestep-refinement leg: the SAME total 300 s reached in N kernel calls.
!
! Owner review §9. The open question after the `cpm`/`xl` finding is not parity
! but which discrete operator converges: the reference computes the thermodynamic
! coefficients once per kernel call and holds them across its internal subcycles,
! the port recomputes them each subcycle, and "recomputes more often" is not by
! itself an argument that the answer is better.
!
! The refinement is EXTERNAL — N calls of dt = 300/N — and that choice is what
! makes the experiment mean anything. Refining internally (one call, more
! subcycles) leaves the reference's coefficients pinned at the kernel-entry state
! for the whole 300 s, so its lag error cannot shrink and the comparison is
! rigged. Re-entering the kernel N times puts BOTH policies through F:893 N times,
! so both refresh, both approach the variable-coefficient limit, and the thing
! being measured is the RATE at which each does — which is the discriminating
! quantity. It is also the boundary §9 asks for: kdm62D directly, so the wrapper's
! preprocessing does not run N times and contaminate the sequence.
!
! N is a runtime argument. One build serves the whole sweep, so no member of it
! can differ by a compiler invocation.
!
! Deliberately a SEPARATE file from g33_fortran_driver.f90, which it otherwise
! duplicates. That driver's source hash is anchored in the four-leg bundle
! manifests, so adding a subroutine to it would invalidate the evidence this
! experiment is supposed to sit beside. The duplication is the cost of leaving
! the decision producer untouched.
!
! Emits one G33R STATE line per field/cell plus the three precipitation
! accumulators, in the same top-first convention as the decision driver.
#if defined(KDM6_G33_F64) && defined(KDM6_G33_NUMBER_DUMP)
! The LAST of three guards on the same wrong-number path (owner priority-2). The
! G33F number records write `'f32', transfer(<real>, 0)`; under -fdefault-real-8
! that takes four bytes of an eight-byte value into an int32 mold and labels the
! result f32, so a reader parses a valid-looking f32 bit pattern that is not the
! number. The Python producer and the build script both refuse the combination;
! this one catches a hand-rolled compile that reaches neither, and it fails at
! COMPILE time rather than producing a binary whose output is quietly wrong.
#error "KDM6_G33_F64 with KDM6_G33_NUMBER_DUMP: no f64 number record family exists"
#endif
module g33_refine
  use, intrinsic :: iso_fortran_env, only: int32, real32
  use module_model_constants, only: g, cp, cpv, r_d, r_v, svpt0, ep_1, ep_2, &
                                    xls, xlv, xlf, rhoair0, rhowater,        &
                                    rhosnow, cliq, cice, psat
  use g33_fixture_v1, only: FIX_B => B, FIX_K => K, FIX_ID => FIXTURE_ID, &
       TH_BITS, QV_BITS, QC_BITS, QR_BITS, QI_BITS, QS_BITS, QG_BITS, &
       NCCN_BITS, NC_BITS, NI_BITS, NR_BITS, BG_BITS, RHO_BITS, PII_BITS, &
       P_BITS, DELZ_BITS, XLAND_BITS, DT_BITS, NCMIN_LAND_BITS, &
       NCMIN_SEA_BITS, QMIN_BITS, CCN0_BITS, SCALE_H_BITS
#ifdef KDM6_CONS
  use module_mp_kdm6_cons, only: kdm62D
#else
  use module_mp_kdm6, only: kdm62D
#endif
  implicit none
#ifdef KDM6_CONS
  character(len=*), parameter :: ALGOTAG = 'conservative'
#else
  character(len=*), parameter :: ALGOTAG = 'legacy'
#endif
  integer, parameter :: G33_B = FIX_B, G33_K = FIX_K, NFLD_ST = 12
  character(len=4), dimension(NFLD_ST), parameter :: FLDNAME = &
       [character(len=4) :: 'th  ','qv  ','qc  ','qr  ','qi  ','qs  ', &
                            'qg  ','nccn','nc  ','ni  ','nr  ','bg  ']
  ! Density-profile control for the falsification matrix (owner priority-5).
  ! 0 = the fixture's own profile, so every existing invocation is unchanged.
  integer :: rho_mode = 0

contains

  pure real function f32(bits) result(value)
    integer(int32), intent(in) :: bits
    ! KIND-EXPLICIT. `transfer(bits, value)` reinterprets the 4-byte pattern as
    ! whatever the default real is, which under the -fdefault-real-8 precision
    ! probe is 8 bytes -- so every fixture constant became garbage and the run
    ! produced NaN. The pattern is an f32 word by definition; widen afterwards.
    real(real32) :: word
    word = transfer(bits, word)
    value = real(word, kind(value))
  end function f32

  subroutine run_refined(im, km, nsplit, tiles, ntile, carry_aux, outF, precF, &
                         denO, delzO, piiO, inF)
    ! `tiles(1:ntile)` are the COLUMN COUNTS of consecutive kdm62D calls, the way a
    ! tile or MPI decomposition splits a domain. A column-local operator must give
    ! the same answer for every partition; the pinned reference is not column-local
    ! (`ncmin` is a scalar overwritten inside the column loop), so this measures
    ! what that costs. Explicit counts rather than an even split, so every
    ! composition of the domain can be tested, not just the even ones.
    integer, intent(in)  :: im, km, nsplit, ntile
    integer, intent(in)  :: tiles(ntile)
    logical, intent(in)  :: carry_aux
    real,    intent(out) :: outF(im, km, NFLD_ST), precF(3, im)
    ! The kernel does not modify den/delz, but a rho*dz column budget needs them
    ! paired with the state in the SAME k convention, and re-deriving them in the
    ! analyzer from the fixture would be a second source that could drift.
    real,    intent(out) :: denO(im, km), delzO(im, km), piiO(im, km)
    ! t=0 state, for the enthalpy ledger. Emitted rather than re-read from
    ! the fixture so the ledger's endpoints come from ONE source.
    real,    intent(out) :: inF(im, km, NFLD_ST)
    real, dimension(1:im,1:km) :: den, pii, p, delz
    real, dimension(1:im,1:1)  :: xland, rainF, rainncv, snowF, snowncv
    real, dimension(1:im,1:1)  :: srF, graupelF, graupelncv
    real, dimension(1:im,1:km)   :: tk, qk, brsk, rhoxk, cmgk
    real, dimension(1:im,1:km,3) :: qcik, qrsk, ncik, nrsk
    real, dimension(1:im,1:km)   :: n0so2d, n0go2d
    real :: dt_total, delt, ccn0, ncmin_land, ncmin_sea, qmin
    integer :: i, k, kt, s, tl, i0, i1
    real :: rho_mean

    if (im /= G33_B .or. km /= G33_K) error stop 'shared fixture dimensions differ'
    dt_total = f32(DT_BITS)
    ! Exact in f32 for every N in the sweep (300/1,2,3,6,12 = 300,150,100,50,25),
    ! so no member of the sequence carries a division rounding the others do not.
    delt = dt_total / real(nsplit)
    ccn0 = f32(CCN0_BITS)
    ncmin_land = f32(NCMIN_LAND_BITS); ncmin_sea = f32(NCMIN_SEA_BITS)
    qmin = f32(QMIN_BITS)

    ! Same top-first permutation as the decision driver.
    do i = 1, im
      do k = 1, km
        kt = km - k + 1
        pii(i,k) = f32(PII_BITS(i,kt))
        tk(i,k)  = f32(TH_BITS(i,kt)) * pii(i,k)
        qk(i,k)  = f32(QV_BITS(i,kt))
        qcik(i,k,1) = f32(QC_BITS(i,kt)); qcik(i,k,2) = f32(QI_BITS(i,kt))
        qcik(i,k,3) = 0.0
        qrsk(i,k,1) = f32(QR_BITS(i,kt)); qrsk(i,k,2) = f32(QS_BITS(i,kt))
        qrsk(i,k,3) = f32(QG_BITS(i,kt))
        ncik(i,k,1) = f32(NC_BITS(i,kt)); ncik(i,k,2) = f32(NI_BITS(i,kt))
        ncik(i,k,3) = f32(NCCN_BITS(i,kt))
        nrsk(i,k,1) = f32(NR_BITS(i,kt)); nrsk(i,k,2) = 0.0; nrsk(i,k,3) = 0.0
        brsk(i,k) = f32(BG_BITS(i,kt))
        den(i,k)  = f32(RHO_BITS(i,kt))
        p(i,k)    = f32(P_BITS(i,kt)); delz(i,k) = f32(DELZ_BITS(i,kt))
      end do
      ! DENSITY-PROFILE CONTROL (owner priority-5). The number-creation
      ! prediction is (den_below - den_above)*delz_above*dn, so its density
      ! dependence is the falsifiable part: uniform must give zero, inverted must
      ! flip the sign, doubling the contrast must roughly double it. The forcing
      ! is the controlled variable and the DRIVER builds it, so neither the
      ! kernel nor the fixture is touched. Applied as a post-pass over the filled
      ! column so the mean is the column's own.
      if (rho_mode /= 0) then
        rho_mean = sum(den(i,1:km)) / real(km)
        do k = 1, km
          select case (rho_mode)
          case (1); den(i,k) = rho_mean
          case (2); den(i,k) = 2.0*rho_mean - den(i,k)
          case (3); den(i,k) = rho_mean + 2.0*(den(i,k) - rho_mean)
          end select
        end do
      end if
      xland(i,1) = f32(XLAND_BITS(i))
      ! Zeroed ONCE. rainF and the ncv accumulators are cumulative across the
      ! 300 s; re-zeroing per call would make the reported precipitation that of
      ! the final sub-step only, and the sequence would then compare different
      ! quantities at different N.
      rainF(i,1) = 0.0; rainncv(i,1) = 0.0; snowF(i,1) = 0.0; snowncv(i,1) = 0.0
      srF(i,1) = 0.0; graupelF(i,1) = 0.0; graupelncv(i,1) = 0.0
    end do
    rhoxk = 0.0; cmgk = 0.0; n0so2d = 0.0; n0go2d = 0.0

    do i = 1, im
      do k = 1, km
        inF(i,k,1)  = tk(i,k)/pii(i,k); inF(i,k,2)  = qk(i,k)
        inF(i,k,3)  = qcik(i,k,1);      inF(i,k,5)  = qcik(i,k,2)
        inF(i,k,4)  = qrsk(i,k,1);      inF(i,k,6)  = qrsk(i,k,2)
        inF(i,k,7)  = qrsk(i,k,3);      inF(i,k,8)  = ncik(i,k,3)
        inF(i,k,9)  = ncik(i,k,1);      inF(i,k,10) = ncik(i,k,2)
        inF(i,k,11) = nrsk(i,k,1);      inF(i,k,12) = brsk(i,k)
      end do
    end do

    do s = 1, nsplit
      ! The four kdm62D auxiliaries carry no intent in -- established by the
      ! sentinel matrix. `carry_aux` re-tests that across CALLS rather than within
      ! one: with .false. they are re-zeroed every call, with .true. whatever the
      ! kernel wrote survives. Identical output is the control; a difference means
      ! the no-intent-in finding does not extend to a multi-call sequence, and the
      ! whole refinement result would have to be read differently.
      if (.not. carry_aux) then
        rhoxk = 0.0; cmgk = 0.0; n0so2d = 0.0; n0go2d = 0.0
      end if
      i1 = 0
      do tl = 1, ntile
        i0 = i1 + 1
        i1 = i0 + tiles(tl) - 1
#ifdef KDM6_G33_NUMBER_DUMP
        ! The kernel cannot know which EXTERNAL call it is in: its own `loop`
        ! resets to 1 every call, so a reader keying on it collapses every call
        ! onto the last. The driver brackets each call, which also makes a
        ! truncated stream or a changed call count detectable instead of
        ! silently re-attributed (owner P0-4).
        ! GLOBAL call id (owner P0-2): `s` alone repeats once per tile, so a
        ! two-tile run emitted 1,1,2,2 and the parser -- which reads the first
        ! field as a contiguous id -- refused a legitimate run. split and tile
        ! are kept alongside, since a tile boundary is a physical input here.
        write(*,'(A,6(1X,I0),1X,Z8.8)') 'G33N CALL_BEGIN', &
              (s - 1) * ntile + tl, s, tl, i0, i1, KM, transfer(delt, 0)
#endif
        call kdm62D(tk(i0:i1,:), qk(i0:i1,:), qcik(i0:i1,:,:), qrsk(i0:i1,:,:)      &
                   ,ncik(i0:i1,:,:), nrsk(i0:i1,:,:), brsk(i0:i1,:)                 &
                   ,rhoxk(i0:i1,:), cmgk(i0:i1,:)                                   &
                   ,den(i0:i1,:), p(i0:i1,:), delz(i0:i1,:)                         &
                   ,delt, g, cp, cpv, ccn0, r_d, r_v, svpt0                          &
                   ,ep_1, ep_2, qmin                                                 &
                   ,xls, xlv, xlf, rhoair0, rhowater                                 &
                   ,cliq, cice, psat                                                 &
                   ,1                                                                &
                   ,xland(i0:i1,1)                                                   &
                   ,ncmin_land, ncmin_sea                                            &
                   ,rainF(i0:i1,1), rainncv(i0:i1,1)                                 &
                   ,srF(i0:i1,1)                                                     &
                   ,i0,i1, 1,1, 1,km                                                 &
                   ,i0,i1, 1,1, 1,km                                                 &
                   ,i0,i1, 1,1, 1,km, n0so2d(i0:i1,:), n0go2d(i0:i1,:)              &
                   ,snowF(i0:i1,1), snowncv(i0:i1,1)                                 &
                   ,graupelF(i0:i1,1), graupelncv(i0:i1,1)                           &
                    )
#ifdef KDM6_G33_NUMBER_DUMP
        write(*,'(A,3(1X,I0))') 'G33N CALL_END', (s - 1) * ntile + tl, s, tl
#endif
      end do
    end do

    do i = 1, im
      do k = 1, km
        outF(i,k,1)  = tk(i,k) / pii(i,k)          ! back to theta, as the wrapper
        outF(i,k,2)  = qk(i,k)
        outF(i,k,3)  = qcik(i,k,1); outF(i,k,5) = qcik(i,k,2)
        outF(i,k,4)  = qrsk(i,k,1); outF(i,k,6) = qrsk(i,k,2)
        outF(i,k,7)  = qrsk(i,k,3); outF(i,k,8) = ncik(i,k,3)
        outF(i,k,9)  = ncik(i,k,1); outF(i,k,10) = ncik(i,k,2)
        outF(i,k,11) = nrsk(i,k,1); outF(i,k,12) = brsk(i,k)
      end do
    end do
    ! The CUMULATIVE arrays, not the ncv ones. kdm62D zeroes rainncv/snowncv/
    ! graupelncv at every kernel entry (F:914-917) and accumulates into rain/snow/
    ! graupel (F:1466-1467), so `ncv` after N calls is the last sub-call's
    ! precipitation alone. Reading it here would have compared 300 s of
    ! precipitation at N=1 against 25 s of it at N=12 -- a difference in call
    ! structure reported as a difference in the operator. The decision driver reads
    ! ncv correctly because it makes exactly one call.
    precF(1,:) = rainF(:,1); precF(2,:) = snowF(:,1); precF(3,:) = graupelF(:,1)
    denO = den; delzO = delz; piiO = pii
  end subroutine run_refined

  ! An f64 build must NOT write the G33R stream. `transfer(real8, int32)` takes
  ! the first FOUR BYTES of an eight-byte storage sequence, and the standard
  ! analyzer would read that as a valid f32 bit pattern -- a wrong number that
  ! parses (owner P0-4). Under promotion only G33P is emitted.
  subroutine emit_fld(name, i, k, v)
    character(len=*), intent(in) :: name
    integer, intent(in) :: i, k
    real,    intent(in) :: v
    integer(int32) :: b
#ifndef KDM6_G33_F64
    b = transfer(v, b)
    write(*,'(A,1X,A,1X,I0,1X,I0,1X,Z8.8)') 'G33R STATE', trim(name), i, k, b
#endif
  end subroutine emit_fld

end module g33_refine


program g33_refine_driver
  use module_model_constants, only: cliq, cpv, rhoair0, rhowater, rhosnow
#ifdef KDM6_CONS
  use module_mp_kdm6_cons, only: kdm6init => kdm6init_cons
#else
  use module_mp_kdm6, only: kdm6init
#endif
  use g33_refine
  use, intrinsic :: iso_fortran_env, only: int32, real32
  implicit none
  integer, parameter :: IM = G33_B, KM = G33_K
  real :: outF(IM,KM,NFLD_ST), precF(3,IM), denO(IM,KM), delzO(IM,KM), piiO(IM,KM)
  real :: inF(IM,KM,NFLD_ST)
  character(len=32) :: arg
  character(len=128) :: tilestr
  character(len=16) :: tilebuf
  integer :: nsplit, ntile, i, k, f, ios, loops_used, pos, nxt, tl
  integer :: tiles(IM)
  integer(int32) :: b
  logical :: carry_aux
  real :: delt_used, dtcld_used

  if (command_argument_count() < 1) &
      error stop 'usage: g33_refine_driver NSPLIT [carry|rezero] [TILE,SIZES]'
  call get_command_argument(1, arg)
  read(arg, *, iostat=ios) nsplit
  if (ios /= 0 .or. nsplit < 1) error stop 'NSPLIT must be a positive integer'
  carry_aux = .false.
  if (command_argument_count() >= 2) then
    call get_command_argument(2, arg)
    ! Exact match or stop. `carry_aux = (arg == 'carry')` silently treats a typo
    ! as 'rezero', so a run intended as the carry arm would be recorded, analysed
    ! and reported as the control it was supposed to be compared against.
    select case (trim(arg))
    case ('carry');  carry_aux = .true.
    case ('rezero'); carry_aux = .false.
    case default;    error stop 'second argument must be exactly carry or rezero'
    end select
  end if

  ! Fourth argument: the density-profile control. Default 0 leaves the fixture's
  ! own profile, so every existing invocation is unchanged.
  if (command_argument_count() >= 4) then
    call get_command_argument(4, arg)
    select case (trim(arg))
    case ('as-is');    rho_mode = 0
    case ('uniform');  rho_mode = 1
    case ('inverted'); rho_mode = 2
    case ('x2');       rho_mode = 3
    case default; error stop 'rho mode must be as-is|uniform|inverted|x2'
    end select
  end if

  delt_used = f32(DT_BITS) / real(nsplit)
  ! Third argument: comma-separated tile column-counts, e.g. "2,1". Default: one
  ! tile covering the domain.
  ntile = 1
  tiles(1) = IM
  if (command_argument_count() >= 3) then
    call get_command_argument(3, arg)
    ntile = 0
    pos = 1
    do while (pos <= len_trim(arg))
      nxt = index(arg(pos:), ',')
      if (nxt == 0) nxt = len_trim(arg) - pos + 2
      ntile = ntile + 1
      if (ntile > IM) error stop 'more tiles than columns'
      read(arg(pos:pos+nxt-2), *, iostat=ios) tiles(ntile)
      if (ios /= 0 .or. tiles(ntile) < 1) error stop 'tile sizes must be >= 1'
      pos = pos + nxt
    end do
    if (sum(tiles(1:ntile)) /= IM) error stop 'tile sizes must sum to B'
  end if

#ifdef KDM6_G33_NUMBER_DUMP
  ! What this stream INTENDS to be. Without it a run truncated at a closed call
  ! boundary is indistinguishable from a shorter run that completed (owner P0-1).
  ! The header declares the FEATURES this stream carries, so a reader knows which
  ! extension records to require rather than ignoring the ones it does not know.
  ! schema 3 makes that declaration BINDING in both directions: a declared
  ! feature whose records are missing is an error, and a record whose feature was
  ! not declared is refused rather than parsed anyway. The extension families
  ! also carry an exact (sub-step, level) universe -- CAPIN over k=1..K-1 and
  ! TOPOUT at k=0 -- so an incomplete or displaced group cannot pass.
  write(*,'(A,4(1X,I0),3(1X,A))') 'G33N STREAM_BEGIN', 3, nsplit, ntile, &
        nsplit * ntile, ALGOTAG, trim(merge('carry ', 'rezero', carry_aux)), &
        'mstep,mstepi,nflux,xfer,capin,topout' 
#endif
  call kdm6init(rhoair0, rhowater, rhosnow, cliq, cpv, f32(CCN0_BITS), 0, .true.)
  call run_refined(IM, KM, nsplit, tiles(1:ntile), ntile, carry_aux, outF, &
                   precF, denO, delzO, piiO, inF)

  ! delt/loops/dtcld as the KERNEL computed them (F:930-932), not as the caller
  ! intended: the sweep must refine dtcld, and a reader should be able to check
  ! that from the stream rather than re-deriving it.
  loops_used = max(nint(delt_used/120.0), 1)
  dtcld_used = delt_used / real(loops_used)
  if (delt_used <= 120.0) dtcld_used = delt_used
#ifndef KDM6_G33_F64
  write(*,'(A,1X,I0,1X,A,1X,A,1X,A,1X,F0.6,1X,A,1X,I0,1X,A,1X,F0.6)') &
       'G33R BEGIN nsplit', nsplit, trim(merge('carry ', 'rezero', carry_aux)), &
       ALGOTAG, 'delt', delt_used, 'loops', loops_used, 'dtcld', dtcld_used
  do f = 1, NFLD_ST
    do k = 1, KM
      do i = 1, IM
        call emit_fld(FLDNAME(f), i, KM-k, outF(i,k,f))
      end do
    end do
  end do
  do f = 1, NFLD_ST
    do k = 1, KM
      do i = 1, IM
        b = transfer(inF(i,k,f), b)
        write(*,'(A,1X,A,1X,I0,1X,I0,1X,Z8.8)') 'G33R INITIAL', FLDNAME(f), i, KM-k, b
      end do
    end do
  end do
  do k = 1, KM
    do i = 1, IM
      b = transfer(denO(i,k), b)
      write(*,'(A,1X,A,1X,I0,1X,I0,1X,Z8.8)') 'G33R FORCING', 'rho', i, KM-k, b
      b = transfer(delzO(i,k), b)
      write(*,'(A,1X,A,1X,I0,1X,I0,1X,Z8.8)') 'G33R FORCING', 'delz', i, KM-k, b
      b = transfer(piiO(i,k), b)
      write(*,'(A,1X,A,1X,I0,1X,I0,1X,Z8.8)') 'G33R FORCING', 'pii', i, KM-k, b
    end do
  end do
  do f = 1, 3
    do i = 1, IM
      b = transfer(precF(f,i), b)
      write(*,'(A,1X,I0,1X,I0,1X,Z8.8)') 'G33R PREC', f, i, b
    end do
  end do
  write(*,'(A)') 'G33R END'
#endif
#ifdef KDM6_G33_NUMBER_DUMP
  write(*,'(A)') 'G33N STREAM_END'
#endif
#ifdef KDM6_G33_PRECISION_PROBE
  ! The TILE VECTOR, not just its length (owner §8.1). `ntile` alone cannot tell
  ! (2,1) from (1,2), and `ncmin` is a scalar overwritten in the column loop, so
  ! two decompositions of the same domain can give different answers. Comparing
  ! them as a `variant` difference would attribute a DECOMPOSITION effect to the
  ! algorithm.
  tilestr = ''
  do tl = 1, ntile
    write(tilebuf, '(I0)') tiles(tl)
    tilestr = trim(tilestr) // trim(tilebuf)
    if (tl < ntile) tilestr = trim(tilestr) // ','
  end do

  ! The probe stream declares its own precision. Without it an f64 stream and an
  ! f32 one are the same text with different numbers, and nothing structurally
  ! stops a reader mixing them (owner P0-4 / priority 2). `source_precision` is
  ! the precision of the REFERENCE this arm instruments, which is always f32.
#ifdef KDM6_G33_F64
  ! 1 A + 1 I0 + 12 A + 3 I0 + 2 F + 2 I0 -- counted against the argument list,
  ! because a Fortran format/argument mismatch is a RUNTIME abort, not a compile
  ! error: the build succeeds and the failure appears only as missing output.
  write(*,'(A,1X,I0,12(1X,A),3(1X,I0),2(1X,F0.6),2(1X,I0))') &
        'G33P BEGIN', 3, 'precision', 'f64', 'source_precision', 'f32', &
        'fixture', KDM6_G33_FIXTURE, 'algorithm', ALGOTAG, 'mode', &
        trim(merge('carry ', 'rezero', carry_aux)), 'tiles', trim(tilestr), &
        nsplit, loops_used, ntile, delt_used, dtcld_used, IM, KM
#else
  write(*,'(A,1X,I0,12(1X,A),3(1X,I0),2(1X,F0.6),2(1X,I0))') &
        'G33P BEGIN', 3, 'precision', 'f32', 'source_precision', 'f32', &
        'fixture', KDM6_G33_FIXTURE, 'algorithm', ALGOTAG, 'mode', &
        trim(merge('carry ', 'rezero', carry_aux)), 'tiles', trim(tilestr), &
        nsplit, loops_used, ntile, delt_used, dtcld_used, IM, KM
#endif
  ! A SEPARATE record family, in decimal at full precision. The G33R stream is
  ! f32 hex by contract; the question here is whether the fine-step turnover
  ! MOVES when the kernel is promoted to f64, and that cannot be asked through a
  ! 4-byte word. Kept out of G33R so the strict parser and the decision protocol
  ! see nothing new.
  do f = 1, NFLD_ST
    do k = 1, KM
      do i = 1, IM
        write(*,'(A,1X,A,2(1X,I0),1X,ES26.16E3)') 'G33P STATE', &
              trim(FLDNAME(f)), i, KM-k, outF(i,k,f)
      end do
    end do
  end do
  ! Forcing too: without rho and delz the probe stream cannot form a rho*dz
  ! column budget, and the per-column question is exactly what the f64 arm is
  ! for -- it removes the roundoff confound so the sub-step schedule can be
  ! looked at on its own. `pii` and the INITIAL state follow for the same reason:
  ! the moist-enthalpy ledger needs both, and it is the next diagnostic whose
  ! residual might be precision drift rather than physics.
  do k = 1, KM
    do i = 1, IM
      write(*,'(A,1X,A,2(1X,I0),1X,ES26.16E3)') 'G33P FORCING', 'rho', &
            i, KM-k, denO(i,k)
      write(*,'(A,1X,A,2(1X,I0),1X,ES26.16E3)') 'G33P FORCING', 'delz', &
            i, KM-k, delzO(i,k)
      write(*,'(A,1X,A,2(1X,I0),1X,ES26.16E3)') 'G33P FORCING', 'pii', &
            i, KM-k, piiO(i,k)
    end do
  end do
  do f = 1, NFLD_ST
    do k = 1, KM
      do i = 1, IM
        write(*,'(A,1X,A,2(1X,I0),1X,ES26.16E3)') 'G33P INITIAL', &
              trim(FLDNAME(f)), i, KM-k, inF(i,k,f)
      end do
    end do
  end do
  do f = 1, 3
    do i = 1, IM
      write(*,'(A,2(1X,I0),1X,ES26.16E3)') 'G33P PREC', f, i, precF(f,i)
    end do
  end do
  write(*,'(A)') 'G33P END'
#endif
end program g33_refine_driver
