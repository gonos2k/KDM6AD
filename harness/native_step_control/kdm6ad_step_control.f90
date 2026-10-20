! Opt-in, single-process transport for sparse H_DIABATIC boundary updates.
! This module has no WRF/KIM-meso dependencies; the host overlay owns the call.
module kdm6ad_step_control
  use, intrinsic :: iso_fortran_env, only: int32, int64, real32
  use, intrinsic :: iso_c_binding, only: c_char, c_int, c_null_char
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  private

  integer, parameter, public :: step_control_real_kind = real32
  integer, parameter, public :: step_control_ok = 0
  integer, parameter, public :: step_control_disabled = 1

  public :: await_step_command
  public :: prepare_h_diabatic_updates
  public :: write_applied_ack
  public :: await_analysis_command
  public :: prepare_analysis_updates
  public :: write_analysis_ack

  interface
    function c_link(old_path, new_path) bind(C, name="link") result(rc)
      import :: c_char, c_int
      character(kind=c_char), intent(in) :: old_path(*)
      character(kind=c_char), intent(in) :: new_path(*)
      integer(c_int) :: rc
    end function c_link

    function c_unlink(path) bind(C, name="unlink") result(rc)
      import :: c_char, c_int
      character(kind=c_char), intent(in) :: path(*)
      integer(c_int) :: rc
    end function c_unlink

    function c_usleep(usec) bind(C, name="usleep") result(rc)
      import :: c_int
      integer(c_int), value :: usec
      integer(c_int) :: rc
    end function c_usleep
  end interface

contains

  subroutine await_step_command(step, domain, timestamp, bounds, timeout_seconds, &
                                enabled, ierr, ii, kk, jj, delta, message)
    integer, intent(in) :: step, domain, bounds(6), timeout_seconds
    character(len=*), intent(in) :: timestamp
    logical, intent(out) :: enabled
    integer, intent(out) :: ierr
    integer, allocatable, intent(out) :: ii(:), kk(:), jj(:)
    real(real32), allocatable, intent(out) :: delta(:)
    character(len=*), intent(out) :: message

    character(len=4096) :: root
    character(len=4096) :: ready_path, command_path, ack_path, temp_path
    character(len=256) :: line
    character(len=:), allocatable :: packet
    character(len=10) :: suffix
    logical :: root_set, exists
    integer :: env_status, env_length, ios, count, row, row_start, i_value, k_value, j_value
    integer :: step_value
    integer(int64) :: count64, nx64, nk64, nj64, total64
    integer(int64) :: start_tick, now_tick, tick_rate
    integer(int32) :: bits
    integer(c_int) :: sleep_rc
    integer, allocatable :: field_seen(:,:,:)
    integer :: alloc_status

    enabled = .false.
    ierr = step_control_ok
    message = ""
    call allocate_empty_outputs(ii, kk, jj, delta, alloc_status)
    if (alloc_status /= 0) then
      ierr = 10
      message = "cannot allocate empty step-control outputs"
      return
    end if

    call read_control_root(root, root_set, ierr, message)
    if (ierr /= step_control_ok) return
    if (.not. root_set) then
      ierr = step_control_disabled
      return
    end if
    enabled = .true.

    if (step < 0 .or. domain < 1 .or. timeout_seconds <= 0) then
      ierr = 11
      message = "step, domain, and timeout must be valid positive control values"
      return
    end if
    if (len_trim(timestamp) /= 19 .or. .not. valid_timestamp(timestamp)) then
      ierr = 12
      message = "timestamp must be YYYY-MM-DD_HH:MM:SS"
      return
    end if
    if (.not. valid_bounds(bounds)) then
      ierr = 13
      message = "physical-domain bounds are invalid"
      return
    end if

    call make_step_paths(root, step, ready_path, command_path, ack_path, temp_path, ierr, message)
    if (ierr /= step_control_ok) return
    inquire(file=ready_path, exist=exists)
    if (exists) then
      ierr = 14
      message = "ready receipt already exists for this step"
      return
    end if
    inquire(file=command_path, exist=exists)
    if (exists) then
      ierr = 14
      message = "command file already exists before ready publication"
      return
    end if
    inquire(file=ack_path, exist=exists)
    if (exists) then
      ierr = 14
      message = "applied receipt already exists for this step"
      return
    end if

    call publish_ready(ready_path, temp_path, step, domain, timestamp, bounds, ierr, message)
    if (ierr /= step_control_ok) return

    call system_clock(count=start_tick, count_rate=tick_rate)
    if (tick_rate <= 0_int64) then
      ierr = 15
      message = "system clock is unavailable for bounded command wait"
      return
    end if
    do
      inquire(file=command_path, exist=exists)
      if (exists) exit
      call system_clock(count=now_tick)
      if (now_tick - start_tick >= int(timeout_seconds, int64) * tick_rate) then
        ierr = 16
        message = "timed out waiting for step command"
        return
      end if
      sleep_rc = c_usleep(100000_c_int)
    end do

    call read_exact_command(command_path, step, count64, packet, ierr, message)
    if (ierr /= step_control_ok) return
    nx64 = int(bounds(2),int64)-int(bounds(1),int64)+1_int64
    nk64 = int(bounds(4),int64)-int(bounds(3),int64)+1_int64
    nj64 = int(bounds(6),int64)-int(bounds(5),int64)+1_int64
    if (nx64 > huge(total64)/nk64) then
      ierr = 18
      message = "physical-domain size overflows validation range"
      return
    end if
    total64 = nx64 * nk64
    if (total64 > huge(total64)/nj64) then
      ierr = 18
      message = "physical-domain size overflows validation range"
      return
    end if
    total64 = total64 * nj64
    if (count64 > total64 .or. count64 > int(huge(count),int64)) then
      ierr = 19
      message = "command count exceeds the physical-domain update capacity"
      return
    end if
    count = int(count64)
    deallocate(ii, kk, jj, delta)
    allocate(ii(count), kk(count), jj(count), delta(count), stat=alloc_status)
    if (alloc_status /= 0) then
      ierr = 20
      message = "cannot allocate command update arrays"
      return
    end if

    if (count > 0) then
      allocate(field_seen(bounds(1):bounds(2),bounds(3):bounds(4), &
                          bounds(5):bounds(6)), stat=alloc_status)
      if (alloc_status /= 0) then
        ierr = 20
        message = "cannot allocate duplicate-update validator"
        return
      end if
      field_seen = 0
    end if

    do row = 1, count
      row_start = 38 + (row - 1) * 53
      line = packet(row_start:row_start+51)
      if (len_trim(line) /= 52 .or. line(1:10) /= "H_DIABATIC" .or. &
          line(11:11) /= " " .or. line(22:22) /= " " .or. &
          line(33:33) /= " " .or. line(44:44) /= " " .or. &
          .not. all_digits(line(12:21)) .or. .not. all_digits(line(23:32)) .or. &
          .not. all_digits(line(34:43)) .or. .not. all_hex(line(45:52))) then
        ierr = 22
        message = "step command row has invalid fixed-width syntax"
        return
      end if
      read(line(12:21), '(I10)', iostat=ios) i_value
      if (ios == 0) read(line(23:32), '(I10)', iostat=ios) k_value
      if (ios == 0) read(line(34:43), '(I10)', iostat=ios) j_value
      if (ios == 0) read(line(45:52), '(Z8)', iostat=ios) bits
      if (ios /= 0) then
        ierr = 23
        message = "step command row cannot be decoded"
        return
      end if
      if (i_value < bounds(1) .or. i_value > bounds(2) .or. &
          k_value < bounds(3) .or. k_value > bounds(4) .or. &
          j_value < bounds(5) .or. j_value > bounds(6)) then
        ierr = 24
        message = "step command index is outside physical-domain bounds"
        return
      end if
      if (field_seen(i_value,k_value,j_value) /= 0) then
        ierr = 25
        message = "step command contains duplicate H_DIABATIC indices"
        return
      end if
      delta(row) = transfer(bits, 0.0_real32)
      if (.not. ieee_is_finite(delta(row))) then
        ierr = 26
        message = "step command delta must be finite binary32"
        return
      end if
      if (delta(row) == 0.0_real32) then
        ierr = 27
        message = "nonempty step commands cannot contain plus or minus zero deltas"
        return
      end if
      field_seen(i_value,k_value,j_value) = 1
      ii(row) = i_value
      kk(row) = k_value
      jj(row) = j_value
    end do
    if (allocated(field_seen)) deallocate(field_seen)

  end subroutine await_step_command

  subroutine prepare_h_diabatic_updates(old_h, delta, new_h, ierr, message)
    real(real32), intent(in) :: old_h(:), delta(:)
    real(real32), allocatable, intent(out) :: new_h(:)
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: n, alloc_status
    integer(int32) :: old_bits, new_bits

    ierr = step_control_ok
    message = ""
    if (size(old_h) /= size(delta)) then
      ierr = 30
      message = "old H_DIABATIC and delta lengths differ"
      return
    end if
    allocate(new_h(size(delta)), stat=alloc_status)
    if (alloc_status /= 0) then
      ierr = 31
      message = "cannot allocate prepared H_DIABATIC values"
      return
    end if
    do n = 1, size(delta)
      if (.not. ieee_is_finite(old_h(n)) .or. .not. ieee_is_finite(delta(n)) .or. &
          delta(n) == 0.0_real32) then
        ierr = 32
        message = "H_DIABATIC update has nonfinite data or a zero delta"
        return
      end if
      new_h(n) = old_h(n) + delta(n)
      if (.not. ieee_is_finite(new_h(n))) then
        ierr = 33
        message = "H_DIABATIC update would produce a nonfinite value"
        return
      end if
      old_bits = transfer(old_h(n), 0_int32)
      new_bits = transfer(new_h(n), 0_int32)
      if (old_bits == new_bits) then
        ierr = 34
        message = "H_DIABATIC delta rounds to an identity update"
        return
      end if
    end do
  end subroutine prepare_h_diabatic_updates

  subroutine write_applied_ack(step, domain, ii, kk, jj, old_h, delta, new_h, ierr, message)
    integer, intent(in) :: step, domain, ii(:), kk(:), jj(:)
    real(real32), intent(in) :: old_h(:), delta(:), new_h(:)
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    character(len=4096) :: root, ack_path, temp_path, ready_path, command_path
    character(len=10) :: suffix
    integer :: n, unit, ios, write_status, close_status
    integer(int32) :: old_bits, delta_bits, new_bits
    logical :: root_set, exists

    ierr = step_control_ok
    message = ""
    call read_control_root(root, root_set, ierr, message)
    if (ierr /= step_control_ok) return
    if (.not. root_set) then
      ierr = 40
      message = "cannot publish applied receipt while step control is disabled"
      return
    end if
    n = size(ii)
    if (size(kk) /= n .or. size(jj) /= n .or. size(old_h) /= n .or. &
        size(delta) /= n .or. size(new_h) /= n) then
      ierr = 41
      message = "applied receipt arrays have inconsistent lengths"
      return
    end if
    if (step < 0 .or. domain < 1) then
      ierr = 42
      message = "applied receipt step/domain is invalid"
      return
    end if
    call make_step_paths(root, step, ready_path, command_path, ack_path, temp_path, ierr, message)
    if (ierr /= step_control_ok) return
    inquire(file=ack_path, exist=exists)
    if (exists) then
      ierr = 43
      message = "applied receipt already exists for this step"
      return
    end if
    call temp_name(ack_path, temp_path, ierr, message)
    if (ierr /= step_control_ok) return
    open(newunit=unit, file=trim(temp_path), status="new", action="write", &
         form="formatted", iostat=ios)
    if (ios /= 0) then
      ierr = 44
      message = "cannot create temporary applied receipt"
      return
    end if
    write(unit, '(A)', iostat=ios) "KDM6AD_APPLIED_V1"
    if (ios == 0) write(unit, '(I10.10,1X,I10.10)', iostat=ios) step, n
    do n = 1, size(ii)
      if (ios /= 0) exit
      old_bits = transfer(old_h(n), 0_int32)
      delta_bits = transfer(delta(n), 0_int32)
      new_bits = transfer(new_h(n), 0_int32)
      write(unit, '(A,1X,I10.10,1X,I10.10,1X,I10.10,1X,Z8.8,1X,Z8.8,1X,Z8.8)', &
            iostat=ios) "H_DIABATIC", ii(n), kk(n), jj(n), old_bits, delta_bits, new_bits
    end do
    write_status = ios
    close(unit, iostat=close_status)
    if (write_status /= 0 .or. close_status /= 0) then
      ierr = 45
      message = "cannot finish temporary applied receipt"
      call remove_file(temp_path)
      return
    end if
    call atomic_publish(temp_path, ack_path, ierr, message)
  end subroutine write_applied_ack

  subroutine allocate_empty_outputs(ii, kk, jj, delta, ierr)
    integer, allocatable, intent(out) :: ii(:), kk(:), jj(:)
    real(real32), allocatable, intent(out) :: delta(:)
    integer, intent(out) :: ierr
    integer :: stat
    allocate(ii(0), kk(0), jj(0), delta(0), stat=stat)
    ierr = stat
  end subroutine allocate_empty_outputs

  subroutine read_control_root(root, enabled, ierr, message)
    character(len=*), intent(out) :: root
    logical, intent(out) :: enabled
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: status, length

    root = ""
    enabled = .false.
    ierr = step_control_ok
    message = ""
    call get_environment_variable("KDM6AD_STEP_CONTROL_ROOT", value=root, &
                                  length=length, status=status)
    if (status == 1 .or. length == 0) return
    if (status /= 0 .or. length > len(root)) then
      ierr = 50
      message = "step-control root environment value is invalid or too long"
      return
    end if
    if (index(root(1:length), achar(10)) /= 0 .or. index(root(1:length), achar(13)) /= 0) then
      ierr = 50
      message = "step-control root contains a line break"
      return
    end if
    enabled = .true.
  end subroutine read_control_root

  subroutine make_step_paths(root, step, ready_path, command_path, ack_path, temp_path, ierr, message)
    character(len=*), intent(in) :: root
    integer, intent(in) :: step
    character(len=*), intent(out) :: ready_path, command_path, ack_path, temp_path
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    character(len=10) :: suffix
    character(len=4096) :: directory
    integer :: n

    ierr = step_control_ok
    message = ""
    ready_path = ""
    command_path = ""
    ack_path = ""
    temp_path = ""
    if (step < 0) then
      ierr = 51
      message = "step index must be nonnegative"
      return
    end if
    write(suffix, '(I10.10)') step
    directory = trim(root)
    n = len_trim(directory)
    if (n == 0 .or. n + 32 >= len(directory)) then
      ierr = 52
      message = "step-control root path is empty or too long"
      return
    end if
    if (directory(n:n) /= "/") directory = trim(directory)//"/"
    ready_path = trim(directory)//"ready_"//suffix//".txt"
    command_path = trim(directory)//"command_"//suffix//".txt"
    ack_path = trim(directory)//"applied_"//suffix//".txt"
    temp_path = ""
  end subroutine make_step_paths

  subroutine temp_name(final_path, temporary_path, ierr, message)
    character(len=*), intent(in) :: final_path
    character(len=*), intent(out) :: temporary_path
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer(int64) :: tick
    ierr = step_control_ok
    message = ""
    call system_clock(count=tick)
    write(temporary_path, '(A,".tmp.",Z16.16)') trim(final_path), tick
    if (len_trim(temporary_path) >= len(temporary_path)) then
      ierr = 53
      message = "temporary receipt path is too long"
    end if
  end subroutine temp_name

  subroutine publish_ready(ready_path, temp_path, step, domain, timestamp, bounds, ierr, message)
    character(len=*), intent(in) :: ready_path, temp_path, timestamp
    integer, intent(in) :: step, domain, bounds(6)
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: unit, ios, write_status, close_status
    character(len=4096) :: temporary

    call temp_name(ready_path, temporary, ierr, message)
    if (ierr /= step_control_ok) return
    open(newunit=unit, file=trim(temporary), status="new", action="write", &
         form="formatted", iostat=ios)
    if (ios /= 0) then
      ierr = 54
      message = "cannot create temporary ready receipt"
      return
    end if
    write(unit, '(A)', iostat=ios) "KDM6AD_READY_V1"
    if (ios == 0) write(unit, '(I10.10,1X,I10.10)', iostat=ios) step, domain
    if (ios == 0) write(unit, '(A)', iostat=ios) timestamp
    if (ios == 0) write(unit, '(I10.10,1X,I10.10,1X,I10.10,1X,I10.10,1X,I10.10,1X,I10.10)', &
                         iostat=ios) bounds
    write_status = ios
    close(unit, iostat=close_status)
    if (write_status /= 0 .or. close_status /= 0) then
      ierr = 55
      message = "cannot finish temporary ready receipt"
      call remove_file(temporary)
      return
    end if
    call atomic_publish(temporary, ready_path, ierr, message)
  end subroutine publish_ready

  subroutine read_exact_command(path, expected_step, count, packet, ierr, message)
    character(len=*), intent(in) :: path
    integer, intent(in) :: expected_step
    integer(int64), intent(out) :: count
    character(len=:), allocatable, intent(out) :: packet
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: unit, ios, packet_size, parsed_step, pos, expected_size, alloc_status

    ierr = step_control_ok
    count = 0_int64
    message = ""
    packet_size = 0
    inquire(file=trim(path), size=packet_size, iostat=ios)
    if (ios /= 0 .or. packet_size < 37 .or. packet_size > 53000037) then
      ierr = 60
      message = "step command byte length is invalid"
      return
    end if
    allocate(character(len=packet_size) :: packet, stat=alloc_status)
    if (alloc_status /= 0) then
      ierr = 60
      message = "cannot allocate exact step command packet"
      return
    end if
    open(newunit=unit, file=trim(path), status="old", action="read", &
         access="stream", form="unformatted", iostat=ios)
    if (ios /= 0) then
      ierr = 60
      message = "cannot open step command byte stream"
      return
    end if
    read(unit, pos=1, iostat=ios) packet
    close(unit)
    if (ios /= 0) then
      ierr = 60
      message = "cannot read complete step command byte stream"
      return
    end if
    if (packet(1:14) /= "KDM6AD_STEP_V1" .or. iachar(packet(15:15)) /= 10 .or. &
        .not. all_digits(packet(16:25)) .or. packet(26:26) /= " " .or. &
        .not. all_digits(packet(27:36)) .or. iachar(packet(37:37)) /= 10) then
      ierr = 61
      message = "step command header has invalid exact byte syntax"
      return
    end if
    do pos = 1, packet_size
      if (iachar(packet(pos:pos)) == 0 .or. iachar(packet(pos:pos)) == 13) then
        ierr = 61
        message = "step command contains NUL or CR bytes"
        return
      end if
      if (iachar(packet(pos:pos)) == 10 .and. pos /= 15 .and. pos /= 37) then
        if (pos < 37 .or. mod(pos-37,53) /= 0) then
          ierr = 61
          message = "step command has a misplaced LF byte"
          return
        end if
      end if
    end do
    read(packet(16:25), '(I10)', iostat=ios) parsed_step
    if (ios == 0) read(packet(27:36), '(I10)', iostat=ios) count
    if (ios /= 0 .or. parsed_step /= expected_step .or. count < 0_int64 .or. &
        count > 1000000_int64) then
      ierr = 62
      message = "step command step/count is invalid or exceeds the one-million-row cap"
      return
    end if
    expected_size = 37 + 53 * int(count)
    if (packet_size /= expected_size) then
      ierr = 63
      message = "step command byte length differs from declared row count"
      return
    end if
    do pos = 1, int(count)
      if (iachar(packet(37 + 53*pos:37 + 53*pos)) /= 10) then
        ierr = 64
        message = "step command row is missing its exact LF terminator"
        return
      end if
    end do
  end subroutine read_exact_command

  logical function valid_bounds(bounds)
    integer, intent(in) :: bounds(6)
    valid_bounds = bounds(1) >= 1 .and. bounds(2) >= bounds(1) .and. &
                   bounds(3) >= 1 .and. bounds(4) >= bounds(3) .and. &
                   bounds(5) >= 1 .and. bounds(6) >= bounds(5)
  end function valid_bounds

  logical function valid_timestamp(value)
    character(len=*), intent(in) :: value
    integer :: ios, year, month, day, hour, minute, second, month_days
    logical :: leap_year
    valid_timestamp = .false.
    if (len(value) /= 19) return
    if (.not. all_digits(value(1:4)) .or. value(5:5) /= "-" .or. &
        .not. all_digits(value(6:7)) .or. value(8:8) /= "-" .or. &
        .not. all_digits(value(9:10)) .or. value(11:11) /= "_" .or. &
        .not. all_digits(value(12:13)) .or. value(14:14) /= ":" .or. &
        .not. all_digits(value(15:16)) .or. value(17:17) /= ":" .or. &
        .not. all_digits(value(18:19))) return
    read(value(1:4), '(I4)', iostat=ios) year
    if (ios /= 0) return
    read(value(6:7), '(I2)', iostat=ios) month
    if (ios /= 0) return
    read(value(9:10), '(I2)', iostat=ios) day
    if (ios /= 0) return
    read(value(12:13), '(I2)', iostat=ios) hour
    if (ios /= 0) return
    read(value(15:16), '(I2)', iostat=ios) minute
    if (ios /= 0) return
    read(value(18:19), '(I2)', iostat=ios) second
    if (ios /= 0) return
    if (year < 1 .or. month < 1 .or. month > 12 .or. hour > 23 .or. &
        minute > 59 .or. second > 59) return
    leap_year = mod(year,4) == 0 .and. (mod(year,100) /= 0 .or. mod(year,400) == 0)
    month_days = 31
    if (month == 4 .or. month == 6 .or. month == 9 .or. month == 11) month_days = 30
    if (month == 2) then
      month_days = 28
      if (leap_year) month_days = 29
    end if
    if (day < 1 .or. day > month_days) return
    valid_timestamp = .true.
  end function valid_timestamp

  logical function all_digits(value)
    character(len=*), intent(in) :: value
    integer :: n, code
    all_digits = .false.
    if (len(value) == 0) return
    do n = 1, len(value)
      code = iachar(value(n:n))
      if (code < iachar("0") .or. code > iachar("9")) return
    end do
    all_digits = .true.
  end function all_digits

  logical function all_hex(value)
    character(len=*), intent(in) :: value
    integer :: n, code
    all_hex = .false.
    if (len(value) == 0) return
    do n = 1, len(value)
      code = iachar(value(n:n))
      if (.not. ((code >= iachar("0") .and. code <= iachar("9")) .or. &
                 (code >= iachar("A") .and. code <= iachar("F")))) return
    end do
    all_hex = .true.
  end function all_hex

  subroutine atomic_publish(temporary, final_path, ierr, message)
    character(len=*), intent(in) :: temporary, final_path
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    character(kind=c_char), allocatable :: c_temporary(:), c_final(:)
    integer(c_int) :: rc

    ierr = step_control_ok
    message = ""
    call make_c_string(trim(temporary), c_temporary)
    call make_c_string(trim(final_path), c_final)
    if (.not. allocated(c_temporary) .or. .not. allocated(c_final)) then
      ierr = 69
      message = "cannot allocate C path for atomic receipt publication"
      return
    end if
    rc = c_link(c_temporary, c_final)
    if (rc /= 0_c_int) then
      ierr = 70
      message = "atomic receipt publication failed; destination may already exist"
      call remove_file(temporary)
      return
    end if
    rc = c_unlink(c_temporary)
  end subroutine atomic_publish

  subroutine make_c_string(value, result)
    character(len=*), intent(in) :: value
    character(kind=c_char), allocatable, intent(out) :: result(:)
    integer :: n, ios
    n = len_trim(value)
    allocate(result(n+1), stat=ios)
    if (ios /= 0) return
    do ios = 1, n
      result(ios) = value(ios:ios)
    end do
    result(n+1) = c_null_char
  end subroutine make_c_string

  subroutine remove_file(path)
    character(len=*), intent(in) :: path
    character(kind=c_char), allocatable :: c_path(:)
    integer(c_int) :: rc
    call make_c_string(trim(path), c_path)
    if (.not. allocated(c_path)) return
    rc = c_unlink(c_path)
  end subroutine remove_file

  subroutine await_analysis_command(step, domain, timestamp, bounds, timeout_seconds, &
                                    enabled, ierr, ii, kk, jj, delta_t2, delta_qv, message)
    integer, intent(in) :: step, domain, bounds(6), timeout_seconds
    character(len=*), intent(in) :: timestamp
    logical, intent(out) :: enabled
    integer, intent(out) :: ierr
    integer, allocatable, intent(out) :: ii(:), kk(:), jj(:)
    real(real32), allocatable, intent(out) :: delta_t2(:), delta_qv(:)
    character(len=*), intent(out) :: message

    character(len=4096) :: root, ready_path, command_path, ack_path, temp_path
    character(len=61) :: line
    character(len=:), allocatable :: packet
    logical :: root_set, exists
    integer :: env_status, env_length, ios, count, row, row_start
    integer :: i_value, k_value, j_value, parsed_step, alloc_status
    integer(int64) :: count64, nx64, nk64, nj64, total64
    integer(int64) :: start_tick, now_tick, tick_rate
    integer(int32) :: t2_bits, qv_bits
    integer(c_int) :: sleep_rc
    integer, allocatable :: field_seen(:,:,:)

    enabled = .false.
    ierr = step_control_ok
    message = ""
    allocate(ii(0), kk(0), jj(0), delta_t2(0), delta_qv(0), stat=alloc_status)
    if (alloc_status /= 0) then
      ierr = 110
      message = "cannot allocate empty analysis-control outputs"
      return
    end if

    call read_control_root(root, root_set, ierr, message)
    if (ierr /= step_control_ok) return
    if (.not. root_set) then
      ierr = step_control_disabled
      return
    end if
    enabled = .true.
    if (step < 0 .or. domain < 1 .or. timeout_seconds <= 0) then
      ierr = 111
      message = "analysis step, domain, and timeout must be valid"
      return
    end if
    if (len_trim(timestamp) /= 19 .or. .not. valid_timestamp(timestamp)) then
      ierr = 112
      message = "timestamp must be YYYY-MM-DD_HH:MM:SS"
      return
    end if
    if (.not. valid_bounds(bounds)) then
      ierr = 113
      message = "physical-domain bounds are invalid"
      return
    end if

    call make_step_paths(root, step, ready_path, command_path, ack_path, temp_path, ierr, message)
    if (ierr /= step_control_ok) return
    inquire(file=ready_path, exist=exists)
    if (exists) then
      ierr = 114
      message = "ready receipt already exists for this analysis step"
      return
    end if
    inquire(file=command_path, exist=exists)
    if (exists) then
      ierr = 114
      message = "analysis command exists before ready publication"
      return
    end if
    inquire(file=ack_path, exist=exists)
    if (exists) then
      ierr = 114
      message = "analysis acknowledgement already exists for this step"
      return
    end if
    call publish_ready(ready_path, temp_path, step, domain, timestamp, bounds, ierr, message)
    if (ierr /= step_control_ok) return

    call system_clock(count=start_tick, count_rate=tick_rate)
    if (tick_rate <= 0_int64) then
      ierr = 115
      message = "system clock is unavailable for bounded analysis-command wait"
      return
    end if
    do
      inquire(file=command_path, exist=exists)
      if (exists) exit
      call system_clock(count=now_tick)
      if (now_tick - start_tick >= int(timeout_seconds, int64) * tick_rate) then
        ierr = 116
        message = "timed out waiting for analysis command"
        return
      end if
      sleep_rc = c_usleep(100000_c_int)
    end do

    call read_exact_analysis_command(command_path, step, count64, packet, ierr, message)
    if (ierr /= step_control_ok) return
    nx64 = int(bounds(2),int64)-int(bounds(1),int64)+1_int64
    nk64 = int(bounds(4),int64)-int(bounds(3),int64)+1_int64
    nj64 = int(bounds(6),int64)-int(bounds(5),int64)+1_int64
    if (nx64 > huge(total64)/nk64) then
      ierr = 118
      message = "analysis physical-domain size overflows validation range"
      return
    end if
    total64 = nx64 * nk64
    if (total64 > huge(total64)/nj64) then
      ierr = 118
      message = "analysis physical-domain size overflows validation range"
      return
    end if
    total64 = total64 * nj64
    if (count64 > total64 .or. count64 > 3000000_int64) then
      ierr = 119
      message = "analysis command count exceeds domain capacity or three-million-row cap"
      return
    end if
    count = int(count64)
    deallocate(ii, kk, jj, delta_t2, delta_qv)
    allocate(ii(count), kk(count), jj(count), delta_t2(count), delta_qv(count), stat=alloc_status)
    if (alloc_status /= 0) then
      ierr = 120
      message = "cannot allocate analysis-command update arrays"
      return
    end if
    if (count > 0) then
      allocate(field_seen(bounds(1):bounds(2),bounds(3):bounds(4), &
                          bounds(5):bounds(6)), stat=alloc_status)
      if (alloc_status /= 0) then
        ierr = 120
        message = "cannot allocate analysis duplicate-update validator"
        return
      end if
      field_seen = 0
    end if

    do row = 1, count
      row_start = 36 + (row - 1) * 62
      line = packet(row_start:row_start+60)
      if (line(1:10) /= "THETA_M_QV" .or. line(11:11) /= " " .or. &
          line(22:22) /= " " .or. line(33:33) /= " " .or. &
          line(44:44) /= " " .or. line(53:53) /= " " .or. &
          .not. all_digits(line(12:21)) .or. .not. all_digits(line(23:32)) .or. &
          .not. all_digits(line(34:43)) .or. .not. all_hex(line(45:52)) .or. &
          .not. all_hex(line(54:61))) then
        ierr = 122
        message = "analysis command row has invalid fixed-width syntax"
        return
      end if
      read(line(12:21), '(I10)', iostat=ios) i_value
      if (ios == 0) read(line(23:32), '(I10)', iostat=ios) k_value
      if (ios == 0) read(line(34:43), '(I10)', iostat=ios) j_value
      if (ios == 0) read(line(45:52), '(Z8)', iostat=ios) t2_bits
      if (ios == 0) read(line(54:61), '(Z8)', iostat=ios) qv_bits
      if (ios /= 0) then
        ierr = 123
        message = "analysis command row cannot be decoded"
        return
      end if
      if (i_value < bounds(1) .or. i_value > bounds(2) .or. &
          k_value < bounds(3) .or. k_value > bounds(4) .or. &
          j_value < bounds(5) .or. j_value > bounds(6)) then
        ierr = 124
        message = "analysis command index is outside physical-domain bounds"
        return
      end if
      if (field_seen(i_value,k_value,j_value) /= 0) then
        ierr = 125
        message = "analysis command contains duplicate THETA_M_QV coordinates"
        return
      end if
      delta_t2(row) = transfer(t2_bits, 0.0_real32)
      delta_qv(row) = transfer(qv_bits, 0.0_real32)
      if (.not. ieee_is_finite(delta_t2(row)) .or. .not. ieee_is_finite(delta_qv(row))) then
        ierr = 126
        message = "analysis command deltas must be finite binary32 values"
        return
      end if
      if (delta_t2(row) == 0.0_real32 .and. delta_qv(row) == 0.0_real32) then
        ierr = 127
        message = "nonempty analysis rows cannot contain a zero delta pair"
        return
      end if
      field_seen(i_value,k_value,j_value) = 1
      ii(row) = i_value
      kk(row) = k_value
      jj(row) = j_value
    end do
    if (allocated(field_seen)) deallocate(field_seen)
  end subroutine await_analysis_command

  subroutine prepare_analysis_updates(old_t2, old_qv, delta_t2, delta_qv, &
                                      new_t2, new_qv, ierr, message)
    real(real32), intent(in) :: old_t2(:), old_qv(:), delta_t2(:), delta_qv(:)
    real(real32), allocatable, intent(out) :: new_t2(:), new_qv(:)
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: n, alloc_status
    integer(int32) :: old_t_bits, old_q_bits, new_t_bits, new_q_bits

    ierr = step_control_ok
    message = ""
    if (size(old_t2) /= size(old_qv) .or. size(old_t2) /= size(delta_t2) .or. &
        size(old_t2) /= size(delta_qv)) then
      ierr = 130
      message = "analysis old-state and delta lengths differ"
      return
    end if
    allocate(new_t2(size(old_t2)), new_qv(size(old_qv)), stat=alloc_status)
    if (alloc_status /= 0) then
      ierr = 131
      message = "cannot allocate prepared analysis-state values"
      return
    end if
    do n = 1, size(old_t2)
      if (.not. ieee_is_finite(old_t2(n)) .or. .not. ieee_is_finite(old_qv(n)) .or. &
          .not. ieee_is_finite(delta_t2(n)) .or. .not. ieee_is_finite(delta_qv(n)) .or. &
          (delta_t2(n) == 0.0_real32 .and. delta_qv(n) == 0.0_real32)) then
        ierr = 132
        message = "analysis update has nonfinite data or a zero delta pair"
        return
      end if
      new_t2(n) = old_t2(n)
      new_qv(n) = old_qv(n)
      if (delta_t2(n) /= 0.0_real32) new_t2(n) = old_t2(n) + delta_t2(n)
      if (delta_qv(n) /= 0.0_real32) new_qv(n) = old_qv(n) + delta_qv(n)
      if (.not. ieee_is_finite(new_t2(n)) .or. .not. ieee_is_finite(new_qv(n))) then
        ierr = 133
        message = "analysis update would produce a nonfinite T_2 or QV"
        return
      end if
      if (.not. ieee_is_finite(new_t2(n) + 300.0_real32) .or. &
          new_t2(n) + 300.0_real32 <= 0.0_real32) then
        ierr = 134
        message = "analysis T_2 would produce nonpositive total moist potential temperature"
        return
      end if
      if (new_qv(n) < 0.0_real32) then
        ierr = 135
        message = "analysis QV would be negative"
        return
      end if
      old_t_bits = transfer(old_t2(n), 0_int32)
      old_q_bits = transfer(old_qv(n), 0_int32)
      new_t_bits = transfer(new_t2(n), 0_int32)
      new_q_bits = transfer(new_qv(n), 0_int32)
      if (old_t_bits == new_t_bits .and. old_q_bits == new_q_bits) then
        ierr = 136
        message = "analysis row rounds to an identity update in both native fields"
        return
      end if
    end do
  end subroutine prepare_analysis_updates

  subroutine write_analysis_ack(step, domain, ii, kk, jj, old_t2, old_qv, &
                                delta_t2, delta_qv, new_t2, new_qv, ierr, message)
    integer, intent(in) :: step, domain, ii(:), kk(:), jj(:)
    real(real32), intent(in) :: old_t2(:), old_qv(:), delta_t2(:), delta_qv(:), new_t2(:), new_qv(:)
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    character(len=4096) :: root, ack_path, temp_path, ready_path, command_path
    integer :: n, unit, ios, write_status, close_status
    integer(int32) :: bits(6)
    logical :: root_set, exists

    ierr = step_control_ok
    message = ""
    call read_control_root(root, root_set, ierr, message)
    if (ierr /= step_control_ok) return
    if (.not. root_set) then
      ierr = 140
      message = "cannot publish analysis acknowledgement while control is disabled"
      return
    end if
    n = size(ii)
    if (size(kk) /= n .or. size(jj) /= n .or. size(old_t2) /= n .or. &
        size(old_qv) /= n .or. size(delta_t2) /= n .or. size(delta_qv) /= n .or. &
        size(new_t2) /= n .or. size(new_qv) /= n) then
      ierr = 141
      message = "analysis acknowledgement arrays have inconsistent lengths"
      return
    end if
    if (step < 0 .or. domain < 1) then
      ierr = 142
      message = "analysis acknowledgement step/domain is invalid"
      return
    end if
    call make_step_paths(root, step, ready_path, command_path, ack_path, temp_path, ierr, message)
    if (ierr /= step_control_ok) return
    inquire(file=ack_path, exist=exists)
    if (exists) then
      ierr = 143
      message = "analysis acknowledgement already exists for this step"
      return
    end if
    call temp_name(ack_path, temp_path, ierr, message)
    if (ierr /= step_control_ok) return
    open(newunit=unit, file=trim(temp_path), status="new", action="write", &
         form="formatted", iostat=ios)
    if (ios /= 0) then
      ierr = 144
      message = "cannot create temporary analysis acknowledgement"
      return
    end if
    write(unit, '(A)', iostat=ios) "KDM6AD_TQ_APPLIED_V1"
    if (ios == 0) write(unit, '(I10.10,1X,I10.10)', iostat=ios) step, n
    do n = 1, size(ii)
      if (ios /= 0) exit
      if (.not. all(ieee_is_finite([old_t2(n), old_qv(n), delta_t2(n), &
                                   delta_qv(n), new_t2(n), new_qv(n)]))) then
        ios = 1
        exit
      end if
      bits = [transfer(old_t2(n),0_int32), transfer(old_qv(n),0_int32), &
              transfer(delta_t2(n),0_int32), transfer(delta_qv(n),0_int32), &
              transfer(new_t2(n),0_int32), transfer(new_qv(n),0_int32)]
      write(unit, '(A,1X,I10.10,1X,I10.10,1X,I10.10,1X,Z8.8,1X,Z8.8,1X,Z8.8,1X,Z8.8,1X,Z8.8,1X,Z8.8)', &
            iostat=ios) "THETA_M_QV", ii(n), kk(n), jj(n), bits
    end do
    write_status = ios
    close(unit, iostat=close_status)
    if (write_status /= 0 .or. close_status /= 0) then
      ierr = 145
      message = "cannot finish temporary analysis acknowledgement"
      call remove_file(temp_path)
      return
    end if
    call atomic_publish(temp_path, ack_path, ierr, message)
  end subroutine write_analysis_ack

  subroutine read_exact_analysis_command(path, expected_step, count, packet, ierr, message)
    character(len=*), intent(in) :: path
    integer, intent(in) :: expected_step
    integer(int64), intent(out) :: count
    character(len=:), allocatable, intent(out) :: packet
    integer, intent(out) :: ierr
    character(len=*), intent(out) :: message
    integer :: unit, ios, packet_size, parsed_step, pos, expected_size, alloc_status

    ierr = step_control_ok
    count = 0_int64
    message = ""
    packet_size = 0
    inquire(file=trim(path), size=packet_size, iostat=ios)
    if (ios /= 0 .or. packet_size < 35 .or. packet_size > 186000035) then
      ierr = 160
      message = "analysis command byte length is invalid"
      return
    end if
    allocate(character(len=packet_size) :: packet, stat=alloc_status)
    if (alloc_status /= 0) then
      ierr = 160
      message = "cannot allocate exact analysis command packet"
      return
    end if
    open(newunit=unit, file=trim(path), status="old", action="read", &
         access="stream", form="unformatted", iostat=ios)
    if (ios /= 0) then
      ierr = 160
      message = "cannot open analysis command byte stream"
      return
    end if
    read(unit, pos=1, iostat=ios) packet
    close(unit)
    if (ios /= 0) then
      ierr = 160
      message = "cannot read complete analysis command byte stream"
      return
    end if
    if (packet(1:12) /= "KDM6AD_TQ_V1" .or. iachar(packet(13:13)) /= 10 .or. &
        .not. all_digits(packet(14:23)) .or. packet(24:24) /= " " .or. &
        .not. all_digits(packet(25:34)) .or. iachar(packet(35:35)) /= 10) then
      ierr = 161
      message = "analysis command header has invalid exact byte syntax"
      return
    end if
    do pos = 1, packet_size
      if (iachar(packet(pos:pos)) == 0 .or. iachar(packet(pos:pos)) == 13) then
        ierr = 161
        message = "analysis command contains NUL or CR bytes"
        return
      end if
      if (iachar(packet(pos:pos)) == 10 .and. pos /= 13 .and. pos /= 35) then
        if (pos < 35 .or. mod(pos-35,62) /= 0) then
          ierr = 161
          message = "analysis command has a misplaced LF byte"
          return
        end if
      end if
    end do
    read(packet(14:23), '(I10)', iostat=ios) parsed_step
    if (ios == 0) read(packet(25:34), '(I10)', iostat=ios) count
    if (ios /= 0 .or. parsed_step /= expected_step .or. count < 0_int64 .or. &
        count > 3000000_int64) then
      ierr = 162
      message = "analysis command step/count is invalid or exceeds three-million-row cap"
      return
    end if
    expected_size = 35 + 62 * int(count)
    if (packet_size /= expected_size) then
      ierr = 163
      message = "analysis command byte length differs from declared row count"
      return
    end if
    do pos = 1, int(count)
      if (iachar(packet(35 + 62*pos:35 + 62*pos)) /= 10) then
        ierr = 164
        message = "analysis command row is missing its exact LF terminator"
        return
      end if
    end do
  end subroutine read_exact_analysis_command

end module kdm6ad_step_control
