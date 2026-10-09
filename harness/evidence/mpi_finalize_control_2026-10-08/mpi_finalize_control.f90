program mpi_finalize_control
  use, intrinsic :: iso_c_binding, only: c_int
  use, intrinsic :: iso_fortran_env, only: error_unit
  use mpi, only: MPI_COMM_WORLD, MPI_Init, MPI_Comm_rank, MPI_Finalize
  implicit none

  interface
    integer(c_int) function getpid() bind(C, name="getpid")
      import :: c_int
    end function getpid
    subroutine c_exit(status) bind(C, name="_Exit")
      import :: c_int
      integer(c_int), value :: status
    end subroutine c_exit
  end interface

  integer :: ierr, rank
  integer(c_int) :: pid

  pid = getpid()
  write(error_unit, '(a,i0,a)') 'MPI_CONTROL pid=', pid, ' event=mpi_init_enter rank=unavailable'
  flush(error_unit)

  call MPI_Init(ierr)
  if (ierr /= 0) error stop 11
  call MPI_Comm_rank(MPI_COMM_WORLD, rank, ierr)
  if (ierr /= 0) error stop 12

  write(error_unit, '(a,i0,a,i0,a,i0)') 'MPI_CONTROL pid=', pid, ' event=mpi_init_return rank=', rank, ' ierr=', ierr
  flush(error_unit)
  write(error_unit, '(a,i0,a,i0)') 'MPI_CONTROL pid=', pid, ' event=mpi_finalize_enter rank=', rank
  flush(error_unit)

  call MPI_Finalize(ierr)

  write(error_unit, '(a,i0,a,i0,a,i0)') 'MPI_CONTROL pid=', pid, ' event=mpi_finalize_return rank=', rank, ' ierr=', ierr
  flush(error_unit)
  if (ierr /= 0) error stop 13
  call c_exit(0)
end program mpi_finalize_control
