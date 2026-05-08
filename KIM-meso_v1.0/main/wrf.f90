


PROGRAM wrf

   USE module_wrf_top, only : wrf_init, wrf_dfi, wrf_run, wrf_finalize












   IMPLICIT NONE

   INTERFACE
      SUBROUTINE kdm6ad_exit_success() BIND(C, name="kdm6ad_exit_success")
      END SUBROUTINE kdm6ad_exit_success
   END INTERFACE



  
  CALL wrf_init

  
  CALL wrf_dfi



  

  CALL wrf_run



  
  CALL wrf_finalize

  CALL kdm6ad_exit_success

END PROGRAM wrf




