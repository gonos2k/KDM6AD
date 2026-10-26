! Private opt-in REAL4 host moments trace. It does not modify physics values.
! One MPI rank and one thread are required by the live experimental host.
module kdm6ad_moment_trace_v2
  use, intrinsic :: iso_c_binding, only: c_double, c_float, c_int, c_int32_t, c_int64_t
  implicit none
  private

  integer, parameter :: target_count = 3
  integer, parameter :: target_i(target_count) = (/ 155, 221, 91 /)
  integer, parameter :: target_j(target_count) = (/ 25, 63, 94 /)
  integer, save :: next_call_id = 0
  integer, save :: owner_call_id(target_count) = 0
  integer, save :: owner_step(target_count) = 0
  integer, save :: owner_kts(target_count) = 0
  integer, save :: owner_kte(target_count) = 0
  integer, save :: host_unit = 0
  logical, save :: initialized = .false.
  logical, save :: active = .false.
  character(len=4096), save :: trace_directory = ''

  public :: moment_trace_begin_call
  public :: moment_trace_enabled
  public :: moment_trace_buffer_values
  public :: moment_trace_host_values
  public :: moment_trace_finish_values

  interface
    subroutine kdm6_moment_trace_context_c(call_id, step, its, ite, kts, kte, jts, jte) &
        bind(C, name='kdm6_moment_trace_context_c')
      import :: c_int
      integer(c_int), value :: call_id, step, its, ite, kts, kte, jts, jte
    end subroutine kdm6_moment_trace_context_c
  end interface

contains

  subroutine trace_initialize()
    character(len=4096) :: value
    character(len=8192) :: path
    integer :: status, value_length, ios

    if (initialized) return
    initialized = .true.
    value = ''
    call get_environment_variable('KDM6AD_MOMENT_TRACE_V2_DIR', value=value, &
                                  length=value_length, status=status)
    if (status == 1 .or. value_length == 0) return
    if (status /= 0 .or. value_length > len(value)) then
      error stop 'KDM6AD moment trace V2: invalid/overlong trace directory'
    end if
    trace_directory = trim(value)
    path = trim(trace_directory)//'/host.hex'
    open(newunit=host_unit, file=trim(path), status='new', action='write', &
         form='formatted', iostat=ios)
    if (ios /= 0) error stop 'KDM6AD moment trace V2: host.hex must be new and writable'
    write(host_unit, '(A)', iostat=ios) '# KDM6AD_MOMENT_TRACE_V2'
    if (ios /= 0) error stop 'KDM6AD moment trace V2: cannot write host header'
    flush(host_unit)
    active = .true.
  end subroutine trace_initialize

  logical function moment_trace_enabled()
    call trace_initialize()
    moment_trace_enabled = active
  end function moment_trace_enabled

  function moment_trace_begin_call(step, its, ite, kts, kte, jts, jte, im, km, jm, &
                                   dt_c, ncmin_land_c, ncmin_sea_c) result(call_id)
    integer, intent(in) :: step, its, ite, kts, kte, jts, jte, im, km, jm
    real(c_double), intent(in) :: dt_c, ncmin_land_c, ncmin_sea_c
    integer :: call_id
    integer(c_int64_t) :: dt_bits, land_bits, sea_bits
    integer :: t, ios

    call trace_initialize()
    call_id = 0
    if (.not. active) return
    if (im /= ite - its + 1 .or. km /= kte - kts + 1 .or. jm /= jte - jts + 1) then
      error stop 'KDM6AD moment trace V2: declared CABI shape differs from wrapper bounds'
    end if
    next_call_id = next_call_id + 1
    call_id = next_call_id
    dt_bits = transfer(dt_c, 0_c_int64_t)
    land_bits = transfer(ncmin_land_c, 0_c_int64_t)
    sea_bits = transfer(ncmin_sea_c, 0_c_int64_t)
    write(host_unit, '(A,11(1X,I0),3(1X,Z16.16))', iostat=ios) 'CALL', &
        call_id, step, its, ite, kts, kte, jts, jte, im, km, jm, dt_bits, land_bits, sea_bits
    if (ios /= 0) error stop 'KDM6AD moment trace V2: host CALL record write failed'
    flush(host_unit)
    do t = 1, target_count
      if (target_i(t) >= its .and. target_i(t) <= ite .and. &
          target_j(t) >= jts .and. target_j(t) <= jte) then
        owner_call_id(t) = call_id
        owner_step(t) = step
        owner_kts(t) = kts
        owner_kte(t) = kte
      end if
    end do
    call kdm6_moment_trace_context_c(int(call_id,c_int), int(step,c_int), int(its,c_int), int(ite,c_int), &
                                     int(kts,c_int), int(kte,c_int), int(jts,c_int), int(jte,c_int))
  end function moment_trace_begin_call

  subroutine write_f32(stage, call_id, i, k, j, field, value)
    character(len=*), intent(in) :: stage, field
    integer, intent(in) :: call_id, i, k, j
    real(c_float), intent(in) :: value
    integer(c_int32_t) :: raw
    integer :: ios

    if (.not. active .or. call_id <= 0) return
    raw = transfer(value, 0_c_int32_t)
    write(host_unit, '(A,1X,I0,1X,A,1X,I0,1X,I0,1X,I0,1X,A,1X,A,1X,Z8.8)', &
          iostat=ios) 'VAL', call_id, trim(stage), i, k, j, 'f32', trim(field), raw
    if (ios /= 0) error stop 'KDM6AD moment trace V2: host VAL record write failed'
    flush(host_unit)
  end subroutine write_f32

  subroutine moment_trace_buffer_values(stage, call_id, its, ite, kts, kte, jts, jte, &
                                        im, km, jm, qc, nc)
    character(len=*), intent(in) :: stage
    integer, intent(in) :: call_id, its, ite, kts, kte, jts, jte, im, km, jm
    real(c_float), intent(in) :: qc(im, km, jm), nc(im, km, jm)
    integer :: t, k, ii, jj

    if (.not. active .or. call_id <= 0) return
    do t = 1, target_count
      if (target_i(t) < its .or. target_i(t) > ite .or. &
          target_j(t) < jts .or. target_j(t) > jte) cycle
      ii = target_i(t) - its + 1
      jj = target_j(t) - jts + 1
      do k = kts, kte
        call write_f32(stage, call_id, target_i(t), k, target_j(t), 'QC', qc(ii, k-kts+1, jj))
        call write_f32(stage, call_id, target_i(t), k, target_j(t), 'NC', nc(ii, k-kts+1, jj))
      end do
    end do
  end subroutine moment_trace_buffer_values

  subroutine moment_trace_host_values(stage, call_id, ims, ime, kms, kme, jms, jme, &
                                      its, ite, kts, kte, jts, jte, qc, nc)
    character(len=*), intent(in) :: stage
    integer, intent(in) :: call_id, ims, ime, kms, kme, jms, jme
    integer, intent(in) :: its, ite, kts, kte, jts, jte
    real(c_float), intent(in) :: qc(ims:ime, kms:kme, jms:jme)
    real(c_float), intent(in) :: nc(ims:ime, kms:kme, jms:jme)
    integer :: t, i, j, k

    if (.not. active .or. call_id <= 0_c_int) return
    do t = 1, target_count
      i = target_i(t)
      j = target_j(t)
      if (i < its .or. i > ite .or. j < jts .or. j > jte) cycle
      do k = kts, kte
        call write_f32(stage, call_id, i, k, j, 'QC', qc(i, k, j))
        call write_f32(stage, call_id, i, k, j, 'NC', nc(i, k, j))
      end do
    end do
  end subroutine moment_trace_host_values

  subroutine moment_trace_finish_values(stage, step, ims, ime, kms, kme, jms, jme, &
                                        its, ite, kts, kte, jts, jte, qc, nc)
    character(len=*), intent(in) :: stage
    integer, intent(in) :: step, ims, ime, kms, kme, jms, jme
    integer, intent(in) :: its, ite, kts, kte, jts, jte
    real(c_float), intent(in) :: qc(ims:ime, kms:kme, jms:jme)
    real(c_float), intent(in) :: nc(ims:ime, kms:kme, jms:jme)
    integer :: t, i, j, k, first_k, last_k
    integer :: call_id

    if (.not. active) return
    do t = 1, target_count
      call_id = owner_call_id(t)
      i = target_i(t)
      j = target_j(t)
      if (call_id <= 0 .or. owner_step(t) /= step) cycle
      if (i < its .or. i > ite .or. j < jts .or. j > jte) cycle
      first_k = max(kts, owner_kts(t))
      last_k = min(kte, owner_kte(t))
      if (first_k > last_k) cycle
      do k = first_k, last_k
        call write_f32(stage, call_id, i, k, j, 'QC', qc(i, k, j))
        call write_f32(stage, call_id, i, k, j, 'NC', nc(i, k, j))
      end do
    end do
  end subroutine moment_trace_finish_values

end module kdm6ad_moment_trace_v2
