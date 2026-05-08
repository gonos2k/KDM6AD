


PROGRAM ideal

   USE module_domain , ONLY : domain
   USE module_initialize_ideal
   USE module_configure , ONLY : grid_config_rec_type
   USE module_check_a_mundo

   USE module_timing
   USE module_wrf_error


   IMPLICIT NONE


   REAL    :: time

   INTEGER :: loop , &
              levels_to_process


   TYPE(domain) , POINTER :: keep_grid, grid_ptr, null_domain, grid
   TYPE(domain)           :: dummy
   TYPE (grid_config_rec_type)              :: config_flags
   TYPE (WRFU_Time) startTime, stopTime, currentTime
   TYPE (WRFU_TimeInterval) stepTime

   INTEGER :: max_dom , domain_id , fid , oid , idum1 , idum2 , ierr
   INTEGER :: debug_level, rc
   LOGICAL :: input_from_file

   INTERFACE
     SUBROUTINE med_initialdata_output ( grid , config_flags )
       USE module_domain , ONLY : domain
       USE module_configure , ONLY : grid_config_rec_type
       TYPE (domain) , POINTER :: grid
       TYPE (grid_config_rec_type) , INTENT(IN)   :: config_flags
     END SUBROUTINE med_initialdata_output 
   END INTERFACE


   CHARACTER (LEN=*), PARAMETER :: release_version = 'V4.6.0'

    CHARACTER (LEN=*), PARAMETER :: commit_version = 'No git found or not a git repository, git commit version not available.'




   INTEGER                 :: nbytes
   INTEGER, PARAMETER      :: configbuflen = 4* 65536
   INTEGER                 :: configbuf( configbuflen )
   LOGICAL , EXTERNAL      :: wrf_dm_on_monitor


   CHARACTER (LEN=80)     :: message

   

   program_name = "IDEAL " // TRIM(release_version) // " PREPROCESSOR"

   

   CALL init_modules(1)   

   CALL WRFU_Initialize( defaultCalKind=WRFU_CAL_GREGORIAN, rc=rc )

   CALL init_modules(2)   


   IF ( wrf_dm_on_monitor() ) THEN
     CALL initial_config
   ENDIF
   CALL get_config_as_buffer( configbuf, configbuflen, nbytes )
   CALL wrf_dm_bcast_bytes( configbuf, nbytes )
   CALL set_config_as_buffer( configbuf, configbuflen )
   CALL wrf_dm_initialize

   CALL nl_get_debug_level ( 1, debug_level )
   CALL set_wrf_debug_level ( debug_level )

   CALL  wrf_message ( program_name )
   CALL  wrf_message ( commit_version )
   CALL  set_physics_rconfigs
   CALL  check_nml_consistency


   

   NULLIFY( null_domain )

   CALL alloc_and_configure_domain ( domain_id  = 1 ,                  &
                                     grid       = head_grid ,          &
                                     parent     = null_domain ,        &
                                     kid        = -1                   )

   grid => head_grid
   
   
   
   
   CALL WRFU_TimeSet(startTime, YY=1, MM=1, DD=1, H=0, M=0, S=0, rc=rc)
   stopTime = startTime
   currentTime = startTime
   
   CALL WRFU_TimeIntervalSet(stepTime, S=180, rc=rc)
   grid%domain_clock = WRFU_ClockCreate( TimeStep= stepTime,  &
                                         StartTime=startTime, &
                                         StopTime= stopTime,  &
                                         rc=rc )
   CALL wrf_check_error( WRFU_SUCCESS, rc, &
                         'grid%domain_clock = WRFU_ClockCreate() FAILED', &
                         "ideal_em.G" , &
                         129  )
   CALL       wrf_debug ( 100 , 'wrf: calling model_to_grid_config_rec ' )
   CALL model_to_grid_config_rec ( head_grid%id , model_config_rec , config_flags )
   CALL       wrf_debug ( 100 , 'wrf: calling set_scalar_indices_from_config ' )
   CALL set_scalar_indices_from_config ( head_grid%id , idum1, idum2 )


   WRITE ( current_date , FMT = '(I4.4,"-",I2.2,"-",I2.2,"_",I2.2,":",I2.2,":",I2.2,".0000")' ) &
           config_flags%start_year, &
           config_flags%start_month, &
           config_flags%start_day, &
           config_flags%start_hour, &
           config_flags%start_minute, &
           config_flags%start_second 

   CALL domain_clockprint ( 150, grid, &
          'DEBUG assemble_output:  clock before 1st currTime set,' )
   WRITE (wrf_err_message,*) &
        'DEBUG assemble_output:  before 1st currTime set, current_date = ',TRIM(current_date)
   CALL wrf_debug ( 150 , wrf_err_message )
   CALL domain_clock_set( grid, current_timestr=current_date(1:19) )
   CALL domain_clockprint ( 150, grid, &
          'DEBUG assemble_output:  clock after 1st currTime set,' )

   CALL       wrf_debug ( 100 , 'wrf: calling init_wrfio' )
   CALL init_wrfio


   CALL get_config_as_buffer( configbuf, configbuflen, nbytes )
   CALL wrf_dm_bcast_bytes( configbuf, nbytes )
   CALL set_config_as_buffer( configbuf, configbuflen )

      


   grid%this_is_an_ideal_run = .TRUE.
   CALL med_initialdata_output( head_grid , config_flags )

   CALL       wrf_debug (   0 , 'wrf: SUCCESS COMPLETE IDEAL INIT' )
   CALL med_shutdown_io ( head_grid , config_flags )
   CALL wrf_shutdown

   CALL WRFU_Finalize( rc=rc )

END PROGRAM ideal

SUBROUTINE med_initialdata_output ( grid , config_flags )
  
   USE module_domain
   USE module_io_domain
   USE module_initialize_ideal
  
   USE module_configure

   IMPLICIT NONE

  
   TYPE(domain)  , POINTER                    :: grid
   TYPE (grid_config_rec_type) , INTENT(IN)   :: config_flags
  
   INTEGER                :: time_step_begin_restart
   INTEGER                :: fid , ierr , id
   CHARACTER (LEN=80)      :: rstname
   CHARACTER (LEN=80)      :: message
   CHARACTER (LEN=80)      :: inpname , bdyname

   

   grid%input_from_file = .false.
   CALL init_domain (  grid )
   CALL calc_current_date ( grid%id, 0.)

   CALL construct_filename1 ( inpname , 'wrfinput' , grid%id , 2 )
   CALL open_w_dataset ( id, TRIM(inpname) , grid , config_flags , output_input , "DATASET=INPUT", ierr )
   IF ( ierr .NE. 0 ) THEN
     WRITE (wrf_err_message,*)'ideal: error opening wrfinput for writing ',ierr
     CALL wrf_error_fatal3("<stdin>",191,&
wrf_err_message )
   ENDIF
   CALL output_input ( id, grid , config_flags , ierr )
   CALL close_dataset ( id , config_flags, "DATASET=INPUT" )


   IF ( config_flags%specified ) THEN
 
     CALL construct_filename1 ( bdyname , 'wrfbdy' , grid%id , 2 )
     CALL open_w_dataset ( id, TRIM(bdyname) , grid , config_flags , output_boundary , "DATASET=BOUNDARY", ierr )
     IF ( ierr .NE. 0 ) THEN
       WRITE (wrf_err_message,*)'ideal: error opening wrfbdy for writing ',ierr
       CALL wrf_error_fatal3("<stdin>",204,&
wrf_err_message )
     ENDIF
     CALL output_boundary ( id, grid , config_flags , ierr )
     CALL close_dataset ( id , config_flags , "DATASET=BOUNDARY" )
 
   ENDIF

   RETURN
END SUBROUTINE med_initialdata_output



