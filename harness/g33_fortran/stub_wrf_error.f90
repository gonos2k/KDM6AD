! Minimal stand-in for the WRF frame module_wrf_error. module_mp_radar USEs it
! (wrf_debug / wrf_message / wrf_error_fatal); the G3.3-M standalone Fortran
! build needs it but pulls in no other WRF frame. Diagnostics only, no numerics.
module module_wrf_error
  implicit none
contains
  subroutine wrf_debug(level, msg)
    integer, intent(in) :: level
    character(len=*), intent(in) :: msg
    if (.false.) print *, level, msg   ! silent
  end subroutine wrf_debug
  subroutine wrf_message(msg)
    character(len=*), intent(in) :: msg
    print *, trim(msg)
  end subroutine wrf_message
  subroutine wrf_error_fatal(msg)
    character(len=*), intent(in) :: msg
    print *, 'FATAL: ', trim(msg)
    stop 1
  end subroutine wrf_error_fatal
end module module_wrf_error
