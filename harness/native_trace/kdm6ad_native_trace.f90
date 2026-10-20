module kdm6ad_native_trace
  ! Diagnostic-only append writer; use with one MPI rank and one thread.
  use, intrinsic :: iso_fortran_env, only: real32, int32
  implicit none
  private

  integer, parameter, public :: trace_real_kind = real32
  logical, save, public :: trace_enabled = .false.
  integer, save, public :: trace_target_i = 156
  integer, save, public :: trace_target_j = 21
  integer, save, public :: trace_current_step = -1
  integer, save :: trace_unit = 0
  logical, save :: trace_initialized = .false.
  character(len=4096), save :: trace_filename = ''

  public :: trace_set_step, trace_record

contains

  subroutine trace_initialize()
    character(len=4096) :: value
    integer :: status, value_length, ios

    if (trace_initialized) return
    trace_initialized = .true.

    value = ''
    call get_environment_variable('KDM6AD_NATIVE_TRACE_FILE', value, &
                                  length=value_length, status=status)
    if (status == 1 .or. len_trim(value) == 0) return
    if (status /= 0 .or. value_length > len(value)) then
      error stop 'KDM6AD native trace: invalid or overlong trace filename'
    end if

    trace_filename = trim(value)
    call trace_read_index('KDM6AD_NATIVE_TRACE_I', trace_target_i)
    call trace_read_index('KDM6AD_NATIVE_TRACE_J', trace_target_j)

    open(newunit=trace_unit, file=trim(trace_filename), status='unknown', &
         position='append', action='write', form='formatted', iostat=ios)
    if (ios /= 0) error stop 'KDM6AD native trace: cannot open trace output'
    write(trace_unit, '(A)', iostat=ios) &
      '# KDM6AD_NATIVE_TRACE_V1 kind step i k j count values_ieee754_binary32_hex'
    if (ios /= 0) error stop 'KDM6AD native trace: cannot write trace header'
    write(trace_unit, '(A)') '# MP_INPUT: dt,TH,Q,QC,QR,QI,QS,QG,NN,NC,NI,NR,BG,DEN,PII,P,DELZ'
    write(trace_unit, '(A)') '# MP_OUTPUT: dt,TH,Q,QC,QR,QI,QS,QG,NN,NC,NI,NR,BG,RHOG'
    write(trace_unit, '(A)') &
      '# FINISH_PRE: dt,H_PRE,QV_PRE,TH_PLUS,QV_PLUS,QVTEN,MP_RAW,MP_CLIPPED,T_NEW_PRE,T0,ALPHA,MP_TEND_LIM'
    write(trace_unit, '(A)') '# FINISH_POST: dt,T_NEW_AFTER,T0,H_RATE,QV_RATE,QC_RATE,TH_PHY_M_T0'
    flush(trace_unit)
    trace_enabled = .true.
  end subroutine trace_initialize

  subroutine trace_read_index(name, result)
    character(len=*), intent(in) :: name
    integer, intent(inout) :: result
    character(len=128) :: value
    integer :: status, value_length, ios

    value = ''
    call get_environment_variable(name, value, length=value_length, status=status)
    if (status == 1 .or. len_trim(value) == 0) return
    if (status /= 0 .or. value_length > len(value)) then
      error stop 'KDM6AD native trace: invalid target index environment value'
    end if
    read(value, *, iostat=ios) result
    if (ios /= 0 .or. result < 1) then
      error stop 'KDM6AD native trace: target I/J must be positive integers'
    end if
  end subroutine trace_read_index

  subroutine trace_set_step(itimestep)
    integer, intent(in) :: itimestep

    call trace_initialize()
    if (trace_enabled) trace_current_step = itimestep
  end subroutine trace_set_step

  subroutine trace_record(kind, step, i, k, j, values32)
    character(len=*), intent(in) :: kind
    integer, intent(in) :: step, i, k, j
    real(real32), intent(in) :: values32(:)
    integer(int32) :: bits(size(values32))
    integer :: n, ios

    if (.not. trace_enabled) return
    if (i /= trace_target_i .or. j /= trace_target_j) return
    if (step /= trace_current_step) then
      error stop 'KDM6AD native trace: record step differs from current wrapper step'
    end if

    do n = 1, size(values32)
      bits(n) = transfer(values32(n), 0_int32)
    end do
    write(trace_unit, '(A,1X,I0,1X,I0,1X,I0,1X,I0,1X,I0,*(1X,Z8.8))', &
         iostat=ios) trim(kind), step, i, k, j, size(values32), &
                     (bits(n), n=1,size(values32))
    if (ios /= 0) error stop 'KDM6AD native trace: write failed'
    flush(trace_unit)
  end subroutine trace_record

end module kdm6ad_native_trace
