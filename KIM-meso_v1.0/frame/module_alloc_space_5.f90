MODULE module_alloc_space_5
CONTAINS











   SUBROUTINE alloc_space_field_core_5 ( grid,   id, setinitval_in ,  tl_in , inter_domain_in , okay_to_alloc_in, num_bytes_allocated , &
                                  sd31, ed31, sd32, ed32, sd33, ed33, &
                                  sm31 , em31 , sm32 , em32 , sm33 , em33 , &
                                  sp31 , ep31 , sp32 , ep32 , sp33 , ep33 , &
                                  sp31x, ep31x, sp32x, ep32x, sp33x, ep33x, &
                                  sp31y, ep31y, sp32y, ep32y, sp33y, ep33y, &
                                  sm31x, em31x, sm32x, em32x, sm33x, em33x, &
                                  sm31y, em31y, sm32y, em32y, sm33y, em33y )

      USE module_domain_type
      USE module_configure, ONLY : model_config_rec, grid_config_rec_type, in_use_for_config, model_to_grid_config_rec

      USE module_scalar_tables 

      IMPLICIT NONE

      

      TYPE(domain)               , POINTER          :: grid
      INTEGER , INTENT(IN)            :: id
      INTEGER , INTENT(IN)            :: setinitval_in   
      INTEGER , INTENT(IN)            :: sd31, ed31, sd32, ed32, sd33, ed33
      INTEGER , INTENT(IN)            :: sm31, em31, sm32, em32, sm33, em33
      INTEGER , INTENT(IN)            :: sp31, ep31, sp32, ep32, sp33, ep33
      INTEGER , INTENT(IN)            :: sp31x, ep31x, sp32x, ep32x, sp33x, ep33x
      INTEGER , INTENT(IN)            :: sp31y, ep31y, sp32y, ep32y, sp33y, ep33y
      INTEGER , INTENT(IN)            :: sm31x, em31x, sm32x, em32x, sm33x, em33x
      INTEGER , INTENT(IN)            :: sm31y, em31y, sm32y, em32y, sm33y, em33y

      
      
      
      
      INTEGER , INTENT(IN)            :: tl_in
 
      
      
      LOGICAL , INTENT(IN)            :: inter_domain_in, okay_to_alloc_in

      INTEGER(KIND=8) , INTENT(INOUT)         :: num_bytes_allocated


      
      INTEGER idum1, idum2, spec_bdy_width
      REAL    initial_data_value
      CHARACTER (LEN=256) message
      INTEGER tl
      LOGICAL inter_domain, okay_to_alloc
      INTEGER setinitval
      INTEGER sr_x, sr_y

      
      INTEGER ierr

      INTEGER                              :: loop
      INTEGER(KIND=8)                      :: nba 
      CHARACTER(LEN=256)                   :: message_string

   

      TYPE ( grid_config_rec_type ) :: config_flags

      INTEGER                         :: k_start , k_end, its, ite, jts, jte
      INTEGER                         :: ids , ide , jds , jde , kds , kde , &
                                         ims , ime , jms , jme , kms , kme , &
                                         ips , ipe , jps , jpe , kps , kpe

      INTEGER                         :: sids , side , sjds , sjde , skds , skde , &
                                         sims , sime , sjms , sjme , skms , skme , &
                                         sips , sipe , sjps , sjpe , skps , skpe


      INTEGER ::              imsx, imex, jmsx, jmex, kmsx, kmex,    &
                              ipsx, ipex, jpsx, jpex, kpsx, kpex,    &
                              imsy, imey, jmsy, jmey, kmsy, kmey,    &
                              ipsy, ipey, jpsy, jpey, kpsy, kpey

      data_ordering : SELECT CASE ( model_data_order )
         CASE  ( DATA_ORDER_XYZ )
             ids = sd31 ; ide = ed31 ; jds = sd32 ; jde = ed32 ; kds = sd33 ; kde = ed33 ;
             ims = sm31 ; ime = em31 ; jms = sm32 ; jme = em32 ; kms = sm33 ; kme = em33 ;
             ips = sp31 ; ipe = ep31 ; jps = sp32 ; jpe = ep32 ; kps = sp33 ; kpe = ep33 ;
             imsx = sm31x ; imex = em31x ; jmsx = sm32x ; jmex = em32x ; kmsx = sm33x ; kmex = em33x ;
             ipsx = sp31x ; ipex = ep31x ; jpsx = sp32x ; jpex = ep32x ; kpsx = sp33x ; kpex = ep33x ;
             imsy = sm31y ; imey = em31y ; jmsy = sm32y ; jmey = em32y ; kmsy = sm33y ; kmey = em33y ;
             ipsy = sp31y ; ipey = ep31y ; jpsy = sp32y ; jpey = ep32y ; kpsy = sp33y ; kpey = ep33y ;
         CASE  ( DATA_ORDER_YXZ )
             ids = sd32  ; ide = ed32  ; jds = sd31  ; jde = ed31  ; kds = sd33  ; kde = ed33  ;
             ims = sm32  ; ime = em32  ; jms = sm31  ; jme = em31  ; kms = sm33  ; kme = em33  ;
             ips = sp32  ; ipe = ep32  ; jps = sp31  ; jpe = ep31  ; kps = sp33  ; kpe = ep33  ;
             imsx = sm32x  ; imex = em32x  ; jmsx = sm31x  ; jmex = em31x  ; kmsx = sm33x  ; kmex = em33x  ;
             ipsx = sp32x  ; ipex = ep32x  ; jpsx = sp31x  ; jpex = ep31x  ; kpsx = sp33x  ; kpex = ep33x  ;
             imsy = sm32y  ; imey = em32y  ; jmsy = sm31y  ; jmey = em31y  ; kmsy = sm33y  ; kmey = em33y  ;
             ipsy = sp32y  ; ipey = ep32y  ; jpsy = sp31y  ; jpey = ep31y  ; kpsy = sp33y  ; kpey = ep33y  ;
         CASE  ( DATA_ORDER_ZXY )
             ids = sd32  ; ide = ed32  ; jds = sd33  ; jde = ed33  ; kds = sd31  ; kde = ed31  ;
             ims = sm32  ; ime = em32  ; jms = sm33  ; jme = em33  ; kms = sm31  ; kme = em31  ;
             ips = sp32  ; ipe = ep32  ; jps = sp33  ; jpe = ep33  ; kps = sp31  ; kpe = ep31  ;
             imsx = sm32x  ; imex = em32x  ; jmsx = sm33x  ; jmex = em33x  ; kmsx = sm31x  ; kmex = em31x  ;
             ipsx = sp32x  ; ipex = ep32x  ; jpsx = sp33x  ; jpex = ep33x  ; kpsx = sp31x  ; kpex = ep31x  ;
             imsy = sm32y  ; imey = em32y  ; jmsy = sm33y  ; jmey = em33y  ; kmsy = sm31y  ; kmey = em31y  ;
             ipsy = sp32y  ; ipey = ep32y  ; jpsy = sp33y  ; jpey = ep33y  ; kpsy = sp31y  ; kpey = ep31y  ;
         CASE  ( DATA_ORDER_ZYX )
             ids = sd33  ; ide = ed33  ; jds = sd32  ; jde = ed32  ; kds = sd31  ; kde = ed31  ;
             ims = sm33  ; ime = em33  ; jms = sm32  ; jme = em32  ; kms = sm31  ; kme = em31  ;
             ips = sp33  ; ipe = ep33  ; jps = sp32  ; jpe = ep32  ; kps = sp31  ; kpe = ep31  ;
             imsx = sm33x  ; imex = em33x  ; jmsx = sm32x  ; jmex = em32x  ; kmsx = sm31x  ; kmex = em31x  ;
             ipsx = sp33x  ; ipex = ep33x  ; jpsx = sp32x  ; jpex = ep32x  ; kpsx = sp31x  ; kpex = ep31x  ;
             imsy = sm33y  ; imey = em33y  ; jmsy = sm32y  ; jmey = em32y  ; kmsy = sm31y  ; kmey = em31y  ;
             ipsy = sp33y  ; ipey = ep33y  ; jpsy = sp32y  ; jpey = ep32y  ; kpsy = sp31y  ; kpey = ep31y  ;
         CASE  ( DATA_ORDER_XZY )
             ids = sd31  ; ide = ed31  ; jds = sd33  ; jde = ed33  ; kds = sd32  ; kde = ed32  ;
             ims = sm31  ; ime = em31  ; jms = sm33  ; jme = em33  ; kms = sm32  ; kme = em32  ;
             ips = sp31  ; ipe = ep31  ; jps = sp33  ; jpe = ep33  ; kps = sp32  ; kpe = ep32  ;
             imsx = sm31x  ; imex = em31x  ; jmsx = sm33x  ; jmex = em33x  ; kmsx = sm32x  ; kmex = em32x  ;
             ipsx = sp31x  ; ipex = ep31x  ; jpsx = sp33x  ; jpex = ep33x  ; kpsx = sp32x  ; kpex = ep32x  ;
             imsy = sm31y  ; imey = em31y  ; jmsy = sm33y  ; jmey = em33y  ; kmsy = sm32y  ; kmey = em32y  ;
             ipsy = sp31y  ; ipey = ep31y  ; jpsy = sp33y  ; jpey = ep33y  ; kpsy = sp32y  ; kpey = ep32y  ;
         CASE  ( DATA_ORDER_YZX )
             ids = sd33  ; ide = ed33  ; jds = sd31  ; jde = ed31  ; kds = sd32  ; kde = ed32  ;
             ims = sm33  ; ime = em33  ; jms = sm31  ; jme = em31  ; kms = sm32  ; kme = em32  ;
             ips = sp33  ; ipe = ep33  ; jps = sp31  ; jpe = ep31  ; kps = sp32  ; kpe = ep32  ;
             imsx = sm33x  ; imex = em33x  ; jmsx = sm31x  ; jmex = em31x  ; kmsx = sm32x  ; kmex = em32x  ;
             ipsx = sp33x  ; ipex = ep33x  ; jpsx = sp31x  ; jpex = ep31x  ; kpsx = sp32x  ; kpex = ep32x  ;
             imsy = sm33y  ; imey = em33y  ; jmsy = sm31y  ; jmey = em31y  ; kmsy = sm32y  ; kmey = em32y  ;
             ipsy = sp33y  ; ipey = ep33y  ; jpsy = sp31y  ; jpey = ep31y  ; kpsy = sp32y  ; kpey = ep32y  ;
      END SELECT data_ordering

      CALL model_to_grid_config_rec ( id , model_config_rec , config_flags )

      CALL nl_get_sr_x( id , sr_x )
      CALL nl_get_sr_y( id , sr_y )

      tl = tl_in
      inter_domain = inter_domain_in
      okay_to_alloc = okay_to_alloc_in


      CALL get_initial_data_value ( initial_data_value )



      setinitval = setinitval_in


      CALL nl_get_spec_bdy_width( 1, spec_bdy_width )









IF ( setinitval .EQ. 3 ) grid%auxinput8_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput8_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput8_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput8_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput8_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput8_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput8_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput8_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput8=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput8=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput9_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput9=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput9=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput10_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput10=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput10=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput11_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput11=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput11=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput12_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput12=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput12=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput13_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput13=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput13=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput14_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput14=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput14=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput15_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput15=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput15=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput16_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput16=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput16=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput17_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput17=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput17=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput18_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput18=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput18=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput19_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput19=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput19=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput20_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput20=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput20=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput21_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput21=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput21=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput22_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput22=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput22=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput23_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput23=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput23=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_oid=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_interval_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_interval_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_interval_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_interval_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_interval_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_interval=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_begin_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_begin_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_begin_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_begin_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_begin_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_begin=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_end_y=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_end_d=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_end_h=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_end_m=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_end_s=0
IF ( setinitval .EQ. 3 ) grid%auxinput24_end=0
IF ( setinitval .EQ. 3 ) grid%io_form_auxinput24=0
IF ( setinitval .EQ. 3 ) grid%frames_per_auxinput24=0
IF ( setinitval .EQ. 3 ) grid%oid=0
IF ( setinitval .EQ. 3 ) grid%history_interval=0
IF ( setinitval .EQ. 3 ) grid%frames_per_outfile=0
IF ( setinitval .EQ. 3 ) grid%restart=.FALSE.
IF ( setinitval .EQ. 3 ) grid%restart_interval=0
IF ( setinitval .EQ. 3 ) grid%io_form_input=0
IF ( setinitval .EQ. 3 ) grid%io_form_history=0
IF ( setinitval .EQ. 3 ) grid%io_form_restart=0
IF ( setinitval .EQ. 3 ) grid%io_form_boundary=0
IF ( setinitval .EQ. 3 ) grid%debug_level=0
IF ( setinitval .EQ. 3 ) grid%self_test_domain=.FALSE.
IF ( setinitval .EQ. 3 ) grid%use_netcdf_classic=.FALSE.
IF ( setinitval .EQ. 3 ) grid%history_interval_d=0
IF ( setinitval .EQ. 3 ) grid%history_interval_h=0
IF ( setinitval .EQ. 3 ) grid%history_interval_m=0
IF ( setinitval .EQ. 3 ) grid%history_interval_s=0
IF ( setinitval .EQ. 3 ) grid%inputout_interval_d=0
IF ( setinitval .EQ. 3 ) grid%inputout_interval_h=0
IF ( setinitval .EQ. 3 ) grid%inputout_interval_m=0
IF ( setinitval .EQ. 3 ) grid%inputout_interval_s=0
IF ( setinitval .EQ. 3 ) grid%inputout_interval=0
IF ( setinitval .EQ. 3 ) grid%restart_interval_d=0
IF ( setinitval .EQ. 3 ) grid%restart_interval_h=0
IF ( setinitval .EQ. 3 ) grid%restart_interval_m=0
IF ( setinitval .EQ. 3 ) grid%restart_interval_s=0
IF ( setinitval .EQ. 3 ) grid%history_begin_y=0
IF ( setinitval .EQ. 3 ) grid%history_begin_d=0
IF ( setinitval .EQ. 3 ) grid%history_begin_h=0
IF ( setinitval .EQ. 3 ) grid%history_begin_m=0
IF ( setinitval .EQ. 3 ) grid%history_begin_s=0
IF ( setinitval .EQ. 3 ) grid%history_begin=0
IF ( setinitval .EQ. 3 ) grid%inputout_begin_y=0
IF ( setinitval .EQ. 3 ) grid%inputout_begin_d=0
IF ( setinitval .EQ. 3 ) grid%inputout_begin_h=0
IF ( setinitval .EQ. 3 ) grid%inputout_begin_m=0
IF ( setinitval .EQ. 3 ) grid%inputout_begin_s=0
IF ( setinitval .EQ. 3 ) grid%restart_begin_y=0
IF ( setinitval .EQ. 3 ) grid%restart_begin_d=0
IF ( setinitval .EQ. 3 ) grid%restart_begin_h=0
IF ( setinitval .EQ. 3 ) grid%restart_begin_m=0
IF ( setinitval .EQ. 3 ) grid%restart_begin_s=0
IF ( setinitval .EQ. 3 ) grid%restart_begin=0
IF ( setinitval .EQ. 3 ) grid%history_end_y=0
IF ( setinitval .EQ. 3 ) grid%history_end_d=0
IF ( setinitval .EQ. 3 ) grid%history_end_h=0
IF ( setinitval .EQ. 3 ) grid%history_end_m=0
IF ( setinitval .EQ. 3 ) grid%history_end_s=0
IF ( setinitval .EQ. 3 ) grid%history_end=0
IF ( setinitval .EQ. 3 ) grid%inputout_end_y=0
IF ( setinitval .EQ. 3 ) grid%inputout_end_d=0
IF ( setinitval .EQ. 3 ) grid%inputout_end_h=0
IF ( setinitval .EQ. 3 ) grid%inputout_end_m=0
IF ( setinitval .EQ. 3 ) grid%inputout_end_s=0
IF ( setinitval .EQ. 3 ) grid%simulation_start_year=0
IF ( setinitval .EQ. 3 ) grid%simulation_start_month=0
IF ( setinitval .EQ. 3 ) grid%simulation_start_day=0
IF ( setinitval .EQ. 3 ) grid%simulation_start_hour=0
IF ( setinitval .EQ. 3 ) grid%simulation_start_minute=0
IF ( setinitval .EQ. 3 ) grid%simulation_start_second=0
IF ( setinitval .EQ. 3 ) grid%reset_simulation_start=.FALSE.
IF ( setinitval .EQ. 3 ) grid%sr_x=0
IF ( setinitval .EQ. 3 ) grid%sr_y=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_interval_d=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_interval_h=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_interval_m=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_interval_s=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_interval_y=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_interval=0
IF ( setinitval .EQ. 3 ) grid%gfdda_interval_d=0
IF ( setinitval .EQ. 3 ) grid%gfdda_interval_h=0
IF ( setinitval .EQ. 3 ) grid%gfdda_interval_m=0
IF ( setinitval .EQ. 3 ) grid%gfdda_interval_s=0
IF ( setinitval .EQ. 3 ) grid%gfdda_interval_y=0
IF ( setinitval .EQ. 3 ) grid%gfdda_interval=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_begin_y=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_begin_d=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_begin_h=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_begin_m=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_begin_s=0
IF ( setinitval .EQ. 3 ) grid%gfdda_begin_y=0
IF ( setinitval .EQ. 3 ) grid%gfdda_begin_d=0
IF ( setinitval .EQ. 3 ) grid%gfdda_begin_h=0
IF ( setinitval .EQ. 3 ) grid%gfdda_begin_m=0
IF ( setinitval .EQ. 3 ) grid%gfdda_begin_s=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_end_y=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_end_d=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_end_h=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_end_m=0
IF ( setinitval .EQ. 3 ) grid%sgfdda_end_s=0
IF ( setinitval .EQ. 3 ) grid%gfdda_end_y=0
IF ( setinitval .EQ. 3 ) grid%gfdda_end_d=0
IF ( setinitval .EQ. 3 ) grid%gfdda_end_h=0
IF ( setinitval .EQ. 3 ) grid%gfdda_end_m=0
IF ( setinitval .EQ. 3 ) grid%gfdda_end_s=0
IF ( setinitval .EQ. 3 ) grid%io_form_sgfdda=0
IF ( setinitval .EQ. 3 ) grid%io_form_gfdda=0
IF ( setinitval .EQ. 3 ) grid%ignore_iofields_warning=.FALSE.
IF ( setinitval .EQ. 3 ) grid%ncd_nofill=.FALSE.
IF ( setinitval .EQ. 3 ) grid%adios2_compression_enable=.FALSE.
IF ( setinitval .EQ. 3 ) grid%adios2_numaggregators=0
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_hist').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_hist((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",623,&
    'frame/module_domain.f: Failed to allocate grid%lfn_hist((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_hist=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_hist'
  grid%tail_statevars%DataName = 'LFN_HIST'
  grid%tail_statevars%Description = 'level function history'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_hist
  grid%tail_statevars%streams(1) = 234881025 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_hist(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",673,&
    'frame/module_domain.f: Failed to allocate grid%lfn_hist(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_time').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((1)-(1)+1))) * 4
  nba = &
((((1)-(1)+1))) * 4

  ALLOCATE(grid%lfn_time(1:1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",685,&
    'frame/module_domain.f: Failed to allocate grid%lfn_time(1:1). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_time=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_time'
  grid%tail_statevars%DataName = 'LFN_TIME'
  grid%tail_statevars%Description = 'level function history time'
  grid%tail_statevars%Units = 's'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'Z'
  grid%tail_statevars%Stagger      = ''
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 1
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_1d => grid%lfn_time
  grid%tail_statevars%streams(1) = 234881025 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = 1
  grid%tail_statevars%ed1 = 1
  grid%tail_statevars%sd2 = 1
  grid%tail_statevars%ed2 = 1
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = 1
  grid%tail_statevars%em1 = 1
  grid%tail_statevars%sm2 = 1
  grid%tail_statevars%em2 = 1
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = 1
  grid%tail_statevars%ep1 = 1
  grid%tail_statevars%sp2 = 1
  grid%tail_statevars%ep2 = 1
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%dimname1 = 'i_lfn_history'
  grid%tail_statevars%dimname2 = ''
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_time(1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",733,&
    'frame/module_domain.f: Failed to allocate grid%lfn_time(1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'nfuel_cat').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%nfuel_cat((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",745,&
    'frame/module_domain.f: Failed to allocate grid%nfuel_cat((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%nfuel_cat=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'nfuel_cat'
  grid%tail_statevars%DataName = 'NFUEL_CAT'
  grid%tail_statevars%Description = 'fuel data'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%nfuel_cat
  grid%tail_statevars%streams(1) = 234881025 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%nfuel_cat(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",795,&
    'frame/module_domain.f: Failed to allocate grid%nfuel_cat(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'zsf').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%zsf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",807,&
    'frame/module_domain.f: Failed to allocate grid%zsf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%zsf=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'zsf'
  grid%tail_statevars%DataName = 'ZSF'
  grid%tail_statevars%Description = 'height of surface above sea level'
  grid%tail_statevars%Units = 'm'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%zsf
  grid%tail_statevars%streams(1) = 234881025 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%zsf(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",857,&
    'frame/module_domain.f: Failed to allocate grid%zsf(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'dzdxf').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%dzdxf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",869,&
    'frame/module_domain.f: Failed to allocate grid%dzdxf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%dzdxf=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'dzdxf'
  grid%tail_statevars%DataName = 'DZDXF'
  grid%tail_statevars%Description = 'surface gradient x'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%dzdxf
  grid%tail_statevars%streams(1) = 234881025 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%dzdxf(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",919,&
    'frame/module_domain.f: Failed to allocate grid%dzdxf(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'dzdyf').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%dzdyf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",931,&
    'frame/module_domain.f: Failed to allocate grid%dzdyf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%dzdyf=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'dzdyf'
  grid%tail_statevars%DataName = 'DZDYF'
  grid%tail_statevars%Description = 'surface gradient y'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%dzdyf
  grid%tail_statevars%streams(1) = 234881025 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%dzdyf(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",981,&
    'frame/module_domain.f: Failed to allocate grid%dzdyf(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'tign_g').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%tign_g((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",993,&
    'frame/module_domain.f: Failed to allocate grid%tign_g((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%tign_g=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'tign_g'
  grid%tail_statevars%DataName = 'TIGN_G'
  grid%tail_statevars%Description = 'ignition time on ground'
  grid%tail_statevars%Units = 's'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%tign_g
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%tign_g(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1043,&
    'frame/module_domain.f: Failed to allocate grid%tign_g(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'rthfrten').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em32)-(sm32)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em32)-(sm32)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%rthfrten(sm31:em31,sm32:em32,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1055,&
    'frame/module_domain.f: Failed to allocate grid%rthfrten(sm31:em31,sm32:em32,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%rthfrten=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'rthfrten'
  grid%tail_statevars%DataName = 'RTHFRTEN'
  grid%tail_statevars%Description = 'temperature tendency'
  grid%tail_statevars%Units = 'K/s'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XZY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 3
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_3d => grid%rthfrten
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = kds
  grid%tail_statevars%ed2 = kde
  grid%tail_statevars%sd3 = jds
  grid%tail_statevars%ed3 = (jde-1)
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = kms
  grid%tail_statevars%em2 = kme
  grid%tail_statevars%sm3 = jms
  grid%tail_statevars%em3 = jme
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = kps
  grid%tail_statevars%ep2 = MIN( kde, kpe )
  grid%tail_statevars%sp3 = jps
  grid%tail_statevars%ep3 = MIN( (jde-1), jpe )
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'bottom_top_stag'
  grid%tail_statevars%dimname3 = 'south_north'
  ENDIF
ELSE
  ALLOCATE(grid%rthfrten(1,1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1105,&
    'frame/module_domain.f: Failed to allocate grid%rthfrten(1,1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'rqvfrten').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em32)-(sm32)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em32)-(sm32)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%rqvfrten(sm31:em31,sm32:em32,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1117,&
    'frame/module_domain.f: Failed to allocate grid%rqvfrten(sm31:em31,sm32:em32,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%rqvfrten=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'rqvfrten'
  grid%tail_statevars%DataName = 'RQVFRTEN'
  grid%tail_statevars%Description = 'humidity tendency'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XZY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 3
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_3d => grid%rqvfrten
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = kds
  grid%tail_statevars%ed2 = kde
  grid%tail_statevars%sd3 = jds
  grid%tail_statevars%ed3 = (jde-1)
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = kms
  grid%tail_statevars%em2 = kme
  grid%tail_statevars%sm3 = jms
  grid%tail_statevars%em3 = jme
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = kps
  grid%tail_statevars%ep2 = MIN( kde, kpe )
  grid%tail_statevars%sp3 = jps
  grid%tail_statevars%ep3 = MIN( (jde-1), jpe )
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'bottom_top_stag'
  grid%tail_statevars%dimname3 = 'south_north'
  ENDIF
ELSE
  ALLOCATE(grid%rqvfrten(1,1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1167,&
    'frame/module_domain.f: Failed to allocate grid%rqvfrten(1,1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'avg_fuel_frac').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%avg_fuel_frac(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1179,&
    'frame/module_domain.f: Failed to allocate grid%avg_fuel_frac(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%avg_fuel_frac=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'avg_fuel_frac'
  grid%tail_statevars%DataName = 'AVG_FUEL_FRAC'
  grid%tail_statevars%Description = 'fuel remaining averaged to atmospheric grid'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%avg_fuel_frac
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%avg_fuel_frac(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1229,&
    'frame/module_domain.f: Failed to allocate grid%avg_fuel_frac(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'grnhfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%grnhfx(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1241,&
    'frame/module_domain.f: Failed to allocate grid%grnhfx(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%grnhfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'grnhfx'
  grid%tail_statevars%DataName = 'GRNHFX'
  grid%tail_statevars%Description = 'heat flux from ground fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%grnhfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%grnhfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1291,&
    'frame/module_domain.f: Failed to allocate grid%grnhfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'grnqfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%grnqfx(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1303,&
    'frame/module_domain.f: Failed to allocate grid%grnqfx(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%grnqfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'grnqfx'
  grid%tail_statevars%DataName = 'GRNQFX'
  grid%tail_statevars%Description = 'moisture flux from ground fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%grnqfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%grnqfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1353,&
    'frame/module_domain.f: Failed to allocate grid%grnqfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'canhfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%canhfx(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1365,&
    'frame/module_domain.f: Failed to allocate grid%canhfx(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%canhfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'canhfx'
  grid%tail_statevars%DataName = 'CANHFX'
  grid%tail_statevars%Description = 'heat flux from crown fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%canhfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%canhfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1415,&
    'frame/module_domain.f: Failed to allocate grid%canhfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'canqfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%canqfx(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1427,&
    'frame/module_domain.f: Failed to allocate grid%canqfx(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%canqfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'canqfx'
  grid%tail_statevars%DataName = 'CANQFX'
  grid%tail_statevars%Description = 'moisture flux from crown fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%canqfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%canqfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1477,&
    'frame/module_domain.f: Failed to allocate grid%canqfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'uah').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%uah(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1489,&
    'frame/module_domain.f: Failed to allocate grid%uah(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%uah=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'uah'
  grid%tail_statevars%DataName = 'UAH'
  grid%tail_statevars%Description = 'wind at fire_wind_height'
  grid%tail_statevars%Units = 'm/s'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'X'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%uah
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = ide
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( ide, ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east_stag'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%uah(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1539,&
    'frame/module_domain.f: Failed to allocate grid%uah(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'vah').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%vah(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1551,&
    'frame/module_domain.f: Failed to allocate grid%vah(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%vah=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'vah'
  grid%tail_statevars%DataName = 'VAH'
  grid%tail_statevars%Description = 'wind at fire_wind_height'
  grid%tail_statevars%Units = 'm/s'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Y'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%vah
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = jde
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( jde, jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north_stag'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%vah(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1601,&
    'frame/module_domain.f: Failed to allocate grid%vah(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'grnhfx_fu').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%grnhfx_fu(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1613,&
    'frame/module_domain.f: Failed to allocate grid%grnhfx_fu(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%grnhfx_fu=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'grnhfx_fu'
  grid%tail_statevars%DataName = 'GRNHFX_FU'
  grid%tail_statevars%Description = 'heat flux from ground fire (feedback unsensitive)'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%grnhfx_fu
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%grnhfx_fu(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1663,&
    'frame/module_domain.f: Failed to allocate grid%grnhfx_fu(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'grnqfx_fu').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%grnqfx_fu(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1675,&
    'frame/module_domain.f: Failed to allocate grid%grnqfx_fu(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%grnqfx_fu=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'grnqfx_fu'
  grid%tail_statevars%DataName = 'GRNQFX_FU'
  grid%tail_statevars%Description = 'moisture flux from ground fire (feedback unsensitive)'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%grnqfx_fu
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%grnqfx_fu(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1725,&
    'frame/module_domain.f: Failed to allocate grid%grnqfx_fu(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1737,&
    'frame/module_domain.f: Failed to allocate grid%lfn((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn'
  grid%tail_statevars%DataName = 'LFN'
  grid%tail_statevars%Description = 'level function'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1787,&
    'frame/module_domain.f: Failed to allocate grid%lfn(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_0').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1799,&
    'frame/module_domain.f: Failed to allocate grid%lfn_0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_0=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_0'
  grid%tail_statevars%DataName = 'LFN_0'
  grid%tail_statevars%Description = 'level function for time integration, step 0'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_0
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_0(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1849,&
    'frame/module_domain.f: Failed to allocate grid%lfn_0(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_1').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_1((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1861,&
    'frame/module_domain.f: Failed to allocate grid%lfn_1((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_1=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_1'
  grid%tail_statevars%DataName = 'LFN_1'
  grid%tail_statevars%Description = 'level function for time integration, step 1'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_1
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_1(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1911,&
    'frame/module_domain.f: Failed to allocate grid%lfn_1(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_2').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_2((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1923,&
    'frame/module_domain.f: Failed to allocate grid%lfn_2((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_2=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_2'
  grid%tail_statevars%DataName = 'LFN_2'
  grid%tail_statevars%Description = 'level function for time integration, step 2'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_2
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_2(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1973,&
    'frame/module_domain.f: Failed to allocate grid%lfn_2(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_s0').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_s0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",1985,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_s0=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_s0'
  grid%tail_statevars%DataName = 'LFN_S0'
  grid%tail_statevars%Description = 'level set sign function from LSM integration'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_s0
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_s0(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2035,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s0(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_s1').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_s1((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2047,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s1((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_s1=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_s1'
  grid%tail_statevars%DataName = 'LFN_S1'
  grid%tail_statevars%Description = 'level set function for reinitialization integration'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_s1
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_s1(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2097,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s1(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_s2').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_s2((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2109,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s2((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_s2=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_s2'
  grid%tail_statevars%DataName = 'LFN_S2'
  grid%tail_statevars%Description = 'level set function for reinitialization integration'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_s2
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_s2(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2159,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s2(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'lfn_s3').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%lfn_s3((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2171,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s3((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%lfn_s3=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'lfn_s3'
  grid%tail_statevars%DataName = 'LFN_S3'
  grid%tail_statevars%Description = 'level set function for reinitialization integration'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%lfn_s3
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%lfn_s3(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2221,&
    'frame/module_domain.f: Failed to allocate grid%lfn_s3(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fuel_frac').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fuel_frac((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2233,&
    'frame/module_domain.f: Failed to allocate grid%fuel_frac((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fuel_frac=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fuel_frac'
  grid%tail_statevars%DataName = 'FUEL_FRAC'
  grid%tail_statevars%Description = 'fuel remaining'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fuel_frac
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fuel_frac(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2283,&
    'frame/module_domain.f: Failed to allocate grid%fuel_frac(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fire_area').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fire_area((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2295,&
    'frame/module_domain.f: Failed to allocate grid%fire_area((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fire_area=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fire_area'
  grid%tail_statevars%DataName = 'FIRE_AREA'
  grid%tail_statevars%Description = 'fraction of cell area on fire'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fire_area
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fire_area(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2345,&
    'frame/module_domain.f: Failed to allocate grid%fire_area(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'uf').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%uf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2357,&
    'frame/module_domain.f: Failed to allocate grid%uf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%uf=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'uf'
  grid%tail_statevars%DataName = 'UF'
  grid%tail_statevars%Description = 'fire wind'
  grid%tail_statevars%Units = 'm/s'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%uf
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%uf(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2407,&
    'frame/module_domain.f: Failed to allocate grid%uf(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'vf').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%vf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2419,&
    'frame/module_domain.f: Failed to allocate grid%vf((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%vf=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'vf'
  grid%tail_statevars%DataName = 'VF'
  grid%tail_statevars%Description = 'fire wind'
  grid%tail_statevars%Units = 'm/s'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%vf
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%vf(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2469,&
    'frame/module_domain.f: Failed to allocate grid%vf(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fgrnhfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fgrnhfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2481,&
    'frame/module_domain.f: Failed to allocate grid%fgrnhfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fgrnhfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fgrnhfx'
  grid%tail_statevars%DataName = 'FGRNHFX'
  grid%tail_statevars%Description = 'heat flux from ground fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fgrnhfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fgrnhfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2531,&
    'frame/module_domain.f: Failed to allocate grid%fgrnhfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fgrnqfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fgrnqfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2543,&
    'frame/module_domain.f: Failed to allocate grid%fgrnqfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fgrnqfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fgrnqfx'
  grid%tail_statevars%DataName = 'FGRNQFX'
  grid%tail_statevars%Description = 'moisture flux from ground fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fgrnqfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fgrnqfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2593,&
    'frame/module_domain.f: Failed to allocate grid%fgrnqfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fcanhfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fcanhfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2605,&
    'frame/module_domain.f: Failed to allocate grid%fcanhfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fcanhfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fcanhfx'
  grid%tail_statevars%DataName = 'FCANHFX'
  grid%tail_statevars%Description = 'heat flux from crown fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fcanhfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fcanhfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2655,&
    'frame/module_domain.f: Failed to allocate grid%fcanhfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fcanqfx').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fcanqfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2667,&
    'frame/module_domain.f: Failed to allocate grid%fcanqfx((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fcanqfx=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fcanqfx'
  grid%tail_statevars%DataName = 'FCANQFX'
  grid%tail_statevars%Description = 'moisture flux from crown fire'
  grid%tail_statevars%Units = 'W/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fcanqfx
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fcanqfx(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2717,&
    'frame/module_domain.f: Failed to allocate grid%fcanqfx(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'ros').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%ros((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2729,&
    'frame/module_domain.f: Failed to allocate grid%ros((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%ros=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'ros'
  grid%tail_statevars%DataName = 'ROS'
  grid%tail_statevars%Description = 'rate of spread'
  grid%tail_statevars%Units = 'm/s'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%ros
  grid%tail_statevars%streams(1) = 0 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%ros(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2779,&
    'frame/module_domain.f: Failed to allocate grid%ros(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'burnt_area_dt').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%burnt_area_dt((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2791,&
    'frame/module_domain.f: Failed to allocate grid%burnt_area_dt((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%burnt_area_dt=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'burnt_area_dt'
  grid%tail_statevars%DataName = 'BURNT_AREA_DT'
  grid%tail_statevars%Description = 'fraction of cell area burnt on current dt'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%burnt_area_dt
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%burnt_area_dt(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2841,&
    'frame/module_domain.f: Failed to allocate grid%burnt_area_dt(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'flame_length').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%flame_length((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2853,&
    'frame/module_domain.f: Failed to allocate grid%flame_length((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%flame_length=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'flame_length'
  grid%tail_statevars%DataName = 'FLAME_LENGTH'
  grid%tail_statevars%Description = 'fire flame length'
  grid%tail_statevars%Units = 'm'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%flame_length
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%flame_length(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2903,&
    'frame/module_domain.f: Failed to allocate grid%flame_length(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'ros_front').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%ros_front((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2915,&
    'frame/module_domain.f: Failed to allocate grid%ros_front((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%ros_front=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'ros_front'
  grid%tail_statevars%DataName = 'ROS_FRONT'
  grid%tail_statevars%Description = 'rate of spread at fire front'
  grid%tail_statevars%Units = 'm/s'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%ros_front
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%ros_front(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2965,&
    'frame/module_domain.f: Failed to allocate grid%ros_front(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fmc_g').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fmc_g((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",2977,&
    'frame/module_domain.f: Failed to allocate grid%fmc_g((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fmc_g=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fmc_g'
  grid%tail_statevars%DataName = 'FMC_G'
  grid%tail_statevars%Description = 'ground fuel moisture contents'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fmc_g
  grid%tail_statevars%streams(1) = 234881025 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fmc_g(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3027,&
    'frame/module_domain.f: Failed to allocate grid%fmc_g(1,1).  ')
  endif
ENDIF
IF ( setinitval .EQ. 3 ) grid%nfmc=0
IF(okay_to_alloc.AND.in_use_for_config(id,'fmc_gc').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((model_config_rec%nfmc)-(1)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((model_config_rec%nfmc)-(1)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%fmc_gc(sm31:em31,1:model_config_rec%nfmc,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3040,&
    'frame/module_domain.f: Failed to allocate grid%fmc_gc(sm31:em31,1:model_config_rec%nfmc,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fmc_gc=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fmc_gc'
  grid%tail_statevars%DataName = 'FMC_GC'
  grid%tail_statevars%Description = 'fuel moisture contents by class'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XZY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 3
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_3d => grid%fmc_gc
  grid%tail_statevars%streams(1) = 33554433 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = 1
  grid%tail_statevars%ed2 = config_flags%nfmc
  grid%tail_statevars%sd3 = jds
  grid%tail_statevars%ed3 = (jde-1)
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = 1
  grid%tail_statevars%em2 = config_flags%nfmc
  grid%tail_statevars%sm3 = jms
  grid%tail_statevars%em3 = jme
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = 1
  grid%tail_statevars%ep2 = config_flags%nfmc
  grid%tail_statevars%sp3 = jps
  grid%tail_statevars%ep3 = MIN( (jde-1), jpe )
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'fuel_moisture_classes_stag'
  grid%tail_statevars%dimname3 = 'south_north'
  ENDIF
ELSE
  ALLOCATE(grid%fmc_gc(1,1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3090,&
    'frame/module_domain.f: Failed to allocate grid%fmc_gc(1,1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fmep').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((2)-(1)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((2)-(1)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%fmep(sm31:em31,1:2,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3102,&
    'frame/module_domain.f: Failed to allocate grid%fmep(sm31:em31,1:2,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fmep=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fmep'
  grid%tail_statevars%DataName = 'FMEP'
  grid%tail_statevars%Description = 'fuel moisture extended model parameters'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XZY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 3
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_3d => grid%fmep
  grid%tail_statevars%streams(1) = 33554433 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = 1
  grid%tail_statevars%ed2 = 2
  grid%tail_statevars%sd3 = jds
  grid%tail_statevars%ed3 = (jde-1)
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = 1
  grid%tail_statevars%em2 = 2
  grid%tail_statevars%sm3 = jms
  grid%tail_statevars%em3 = jme
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = 1
  grid%tail_statevars%ep2 = 2
  grid%tail_statevars%sp3 = jps
  grid%tail_statevars%ep3 = MIN( (jde-1), jpe )
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'fuel_moisture_extended_parameters_stag'
  grid%tail_statevars%dimname3 = 'south_north'
  ENDIF
ELSE
  ALLOCATE(grid%fmep(1,1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3152,&
    'frame/module_domain.f: Failed to allocate grid%fmep(1,1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fmc_equi').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((model_config_rec%nfmc)-(1)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((model_config_rec%nfmc)-(1)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%fmc_equi(sm31:em31,1:model_config_rec%nfmc,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3164,&
    'frame/module_domain.f: Failed to allocate grid%fmc_equi(sm31:em31,1:model_config_rec%nfmc,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fmc_equi=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fmc_equi'
  grid%tail_statevars%DataName = 'FMC_EQUI'
  grid%tail_statevars%Description = 'fuel moisture contents by class equilibrium (diagnostics only)'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XZY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 3
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_3d => grid%fmc_equi
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = 1
  grid%tail_statevars%ed2 = config_flags%nfmc
  grid%tail_statevars%sd3 = jds
  grid%tail_statevars%ed3 = (jde-1)
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = 1
  grid%tail_statevars%em2 = config_flags%nfmc
  grid%tail_statevars%sm3 = jms
  grid%tail_statevars%em3 = jme
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = 1
  grid%tail_statevars%ep2 = config_flags%nfmc
  grid%tail_statevars%sp3 = jps
  grid%tail_statevars%ep3 = MIN( (jde-1), jpe )
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'fuel_moisture_classes_stag'
  grid%tail_statevars%dimname3 = 'south_north'
  ENDIF
ELSE
  ALLOCATE(grid%fmc_equi(1,1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3214,&
    'frame/module_domain.f: Failed to allocate grid%fmc_equi(1,1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fmc_lag').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((model_config_rec%nfmc)-(1)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((model_config_rec%nfmc)-(1)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%fmc_lag(sm31:em31,1:model_config_rec%nfmc,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3226,&
    'frame/module_domain.f: Failed to allocate grid%fmc_lag(sm31:em31,1:model_config_rec%nfmc,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fmc_lag=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fmc_lag'
  grid%tail_statevars%DataName = 'FMC_TEND'
  grid%tail_statevars%Description = 'fuel moisture contents by class time lag (diagnostics only)'
  grid%tail_statevars%Units = 'h'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XZY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 3
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_3d => grid%fmc_lag
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = 1
  grid%tail_statevars%ed2 = config_flags%nfmc
  grid%tail_statevars%sd3 = jds
  grid%tail_statevars%ed3 = (jde-1)
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = 1
  grid%tail_statevars%em2 = config_flags%nfmc
  grid%tail_statevars%sm3 = jms
  grid%tail_statevars%em3 = jme
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = 1
  grid%tail_statevars%ep2 = config_flags%nfmc
  grid%tail_statevars%sp3 = jps
  grid%tail_statevars%ep3 = MIN( (jde-1), jpe )
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'fuel_moisture_classes_stag'
  grid%tail_statevars%dimname3 = 'south_north'
  ENDIF
ELSE
  ALLOCATE(grid%fmc_lag(1,1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3276,&
    'frame/module_domain.f: Failed to allocate grid%fmc_lag(1,1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'rain_old').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%rain_old(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3288,&
    'frame/module_domain.f: Failed to allocate grid%rain_old(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%rain_old=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'rain_old'
  grid%tail_statevars%DataName = 'RAIN_OLD'
  grid%tail_statevars%Description = 'previous value of accumulated rain'
  grid%tail_statevars%Units = 'mm'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%rain_old
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%rain_old(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3338,&
    'frame/module_domain.f: Failed to allocate grid%rain_old(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'t2_old').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%t2_old(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3350,&
    'frame/module_domain.f: Failed to allocate grid%t2_old(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%t2_old=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 't2_old'
  grid%tail_statevars%DataName = 'T2_OLD'
  grid%tail_statevars%Description = 'previous value of air temperature at 2m'
  grid%tail_statevars%Units = 'K'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%t2_old
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%t2_old(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3400,&
    'frame/module_domain.f: Failed to allocate grid%t2_old(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'q2_old').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%q2_old(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3412,&
    'frame/module_domain.f: Failed to allocate grid%q2_old(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%q2_old=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'q2_old'
  grid%tail_statevars%DataName = 'Q2_OLD'
  grid%tail_statevars%Description = 'previous value of 2m specific humidity'
  grid%tail_statevars%Units = 'kg/kg'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%q2_old
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%q2_old(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3462,&
    'frame/module_domain.f: Failed to allocate grid%q2_old(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'psfc_old').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%psfc_old(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3474,&
    'frame/module_domain.f: Failed to allocate grid%psfc_old(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%psfc_old=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'psfc_old'
  grid%tail_statevars%DataName = 'PSFC_OLD'
  grid%tail_statevars%Description = 'previous value of surface pressure'
  grid%tail_statevars%Units = 'Pa'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%psfc_old
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%psfc_old(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3524,&
    'frame/module_domain.f: Failed to allocate grid%psfc_old(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'rh_fire').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4
  nba = &
((((em31)-(sm31)+1))*(((em33)-(sm33)+1))) * 4

  ALLOCATE(grid%rh_fire(sm31:em31,sm33:em33),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3536,&
    'frame/module_domain.f: Failed to allocate grid%rh_fire(sm31:em31,sm33:em33). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%rh_fire=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'rh_fire'
  grid%tail_statevars%DataName = 'RH_FIRE'
  grid%tail_statevars%Description = 'relative humidity at the surface'
  grid%tail_statevars%Units = '1'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%rh_fire
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = (ide-1)
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = (jde-1)
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = ims
  grid%tail_statevars%em1 = ime
  grid%tail_statevars%sm2 = jms
  grid%tail_statevars%em2 = jme
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = ips
  grid%tail_statevars%ep1 = MIN( (ide-1), ipe )
  grid%tail_statevars%sp2 = jps
  grid%tail_statevars%ep2 = MIN( (jde-1), jpe )
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .FALSE.
  grid%tail_statevars%subgrid_y = .FALSE.
  grid%tail_statevars%dimname1 = 'west_east'
  grid%tail_statevars%dimname2 = 'south_north'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%rh_fire(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3586,&
    'frame/module_domain.f: Failed to allocate grid%rh_fire(1,1).  ')
  endif
ENDIF
  IF (.NOT.grid%is_intermediate) THEN
   ALLOCATE( grid%tail_statevars%next )
   grid%tail_statevars => grid%tail_statevars%next
   NULLIFY( grid%tail_statevars%next )
   grid%tail_statevars%ProcOrient    = '  '
   grid%tail_statevars%VarName = 'fmoist_lasttime'
   grid%tail_statevars%DataName = 'FMOIST_LASTTIME'
   grid%tail_statevars%Description = 'last time the moisture model was run'
   grid%tail_statevars%Units = 's'
   grid%tail_statevars%Type    = 'r'
   grid%tail_statevars%Ntl = 0
   grid%tail_statevars%Restart  = .TRUE.
   grid%tail_statevars%Ndim    = 0
   grid%tail_statevars%scalar_array  = .FALSE. 
   grid%tail_statevars%rfield_0d => grid%fmoist_lasttime
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  ENDIF
IF ( setinitval .EQ. 3 ) grid%fmoist_lasttime=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
   ALLOCATE( grid%tail_statevars%next )
   grid%tail_statevars => grid%tail_statevars%next
   NULLIFY( grid%tail_statevars%next )
   grid%tail_statevars%ProcOrient    = '  '
   grid%tail_statevars%VarName = 'fmoist_nexttime'
   grid%tail_statevars%DataName = 'FMOIST_NEXTTIME'
   grid%tail_statevars%Description = 'next time the moisture model will run'
   grid%tail_statevars%Units = 's'
   grid%tail_statevars%Type    = 'r'
   grid%tail_statevars%Ntl = 0
   grid%tail_statevars%Restart  = .TRUE.
   grid%tail_statevars%Ndim    = 0
   grid%tail_statevars%scalar_array  = .FALSE. 
   grid%tail_statevars%rfield_0d => grid%fmoist_nexttime
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  ENDIF
IF ( setinitval .EQ. 3 ) grid%fmoist_nexttime=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fmoist_run=.FALSE.
IF ( setinitval .EQ. 3 ) grid%fmoist_interp=.FALSE.
IF ( setinitval .EQ. 3 ) grid%fmoisti_run=0
IF ( setinitval .EQ. 3 ) grid%fmoisti_interp=0
IF ( setinitval .EQ. 3 ) grid%fmoist_only=.FALSE.
IF ( setinitval .EQ. 3 ) grid%fmoist_freq=0
IF ( setinitval .EQ. 3 ) grid%fmoist_dt=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fmep_decay_tlag=initial_data_value
IF(okay_to_alloc.AND.in_use_for_config(id,'fxlong').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fxlong((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3644,&
    'frame/module_domain.f: Failed to allocate grid%fxlong((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fxlong=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fxlong'
  grid%tail_statevars%DataName = 'FXLONG'
  grid%tail_statevars%Description = 'longitude of midpoints of fire cells'
  grid%tail_statevars%Units = 'degrees'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fxlong
  grid%tail_statevars%streams(1) = 33554433 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fxlong(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3694,&
    'frame/module_domain.f: Failed to allocate grid%fxlong(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fxlat').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fxlat((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3706,&
    'frame/module_domain.f: Failed to allocate grid%fxlat((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fxlat=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fxlat'
  grid%tail_statevars%DataName = 'FXLAT'
  grid%tail_statevars%Description = 'latitude of midpoints of fire cells'
  grid%tail_statevars%Units = 'degrees'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fxlat
  grid%tail_statevars%streams(1) = 33554433 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fxlat(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3756,&
    'frame/module_domain.f: Failed to allocate grid%fxlat(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fuel_time').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fuel_time((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3768,&
    'frame/module_domain.f: Failed to allocate grid%fuel_time((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fuel_time=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fuel_time'
  grid%tail_statevars%DataName = 'FUEL_TIME'
  grid%tail_statevars%Description = 'fuel'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fuel_time
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fuel_time(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3818,&
    'frame/module_domain.f: Failed to allocate grid%fuel_time(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'bbb').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%bbb((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3830,&
    'frame/module_domain.f: Failed to allocate grid%bbb((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%bbb=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'bbb'
  grid%tail_statevars%DataName = 'BBB'
  grid%tail_statevars%Description = 'fuel'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%bbb
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%bbb(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3880,&
    'frame/module_domain.f: Failed to allocate grid%bbb(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'betafl').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%betafl((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3892,&
    'frame/module_domain.f: Failed to allocate grid%betafl((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%betafl=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'betafl'
  grid%tail_statevars%DataName = 'BETAFL'
  grid%tail_statevars%Description = 'fuel'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%betafl
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%betafl(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3942,&
    'frame/module_domain.f: Failed to allocate grid%betafl(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'phiwc').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%phiwc((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",3954,&
    'frame/module_domain.f: Failed to allocate grid%phiwc((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%phiwc=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'phiwc'
  grid%tail_statevars%DataName = 'PHIWC'
  grid%tail_statevars%Description = 'fuel'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%phiwc
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%phiwc(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4004,&
    'frame/module_domain.f: Failed to allocate grid%phiwc(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'r_0').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%r_0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4016,&
    'frame/module_domain.f: Failed to allocate grid%r_0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%r_0=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'r_0'
  grid%tail_statevars%DataName = 'R_0'
  grid%tail_statevars%Description = 'fuel'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%r_0
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%r_0(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4066,&
    'frame/module_domain.f: Failed to allocate grid%r_0(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fgip').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fgip((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4078,&
    'frame/module_domain.f: Failed to allocate grid%fgip((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fgip=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fgip'
  grid%tail_statevars%DataName = 'FGIP'
  grid%tail_statevars%Description = 'fuel'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fgip
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fgip(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4128,&
    'frame/module_domain.f: Failed to allocate grid%fgip(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'ischap').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%ischap((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4140,&
    'frame/module_domain.f: Failed to allocate grid%ischap((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%ischap=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'ischap'
  grid%tail_statevars%DataName = 'ISCHAP'
  grid%tail_statevars%Description = 'fuel'
  grid%tail_statevars%Units = '-'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%ischap
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%ischap(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4190,&
    'frame/module_domain.f: Failed to allocate grid%ischap(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'fz0').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%fz0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4202,&
    'frame/module_domain.f: Failed to allocate grid%fz0((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%fz0=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'fz0'
  grid%tail_statevars%DataName = 'FZ0'
  grid%tail_statevars%Description = 'roughness length of fire cells'
  grid%tail_statevars%Units = 'm'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%fz0
  grid%tail_statevars%streams(1) = 33554433 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%fz0(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4252,&
    'frame/module_domain.f: Failed to allocate grid%fz0(1,1).  ')
  endif
ENDIF
IF(okay_to_alloc.AND.in_use_for_config(id,'iboros').AND.(.NOT.grid%is_intermediate))THEN
  num_bytes_allocated = num_bytes_allocated + &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4
  nba = &
((((em31*sr_x)-((sm31-1)*sr_x+1)+1))*(((em33*sr_y)-((sm33-1)*sr_y+1)+1))) * 4

  ALLOCATE(grid%iboros((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4264,&
    'frame/module_domain.f: Failed to allocate grid%iboros((sm31-1)*sr_x+1:em31*sr_x,(sm33-1)*sr_y+1:em33*sr_y). ')
  endif
  IF ( setinitval .EQ. 1 .OR. setinitval .EQ. 3 ) grid%iboros=initial_data_value
  IF (.NOT.grid%is_intermediate) THEN
  ALLOCATE( grid%tail_statevars%next )
  grid%tail_statevars => grid%tail_statevars%next
  NULLIFY( grid%tail_statevars%next )
  grid%tail_statevars%VarName = 'iboros'
  grid%tail_statevars%DataName = 'IBOROS'
  grid%tail_statevars%Description = 'fire intensity over rate of spread'
  grid%tail_statevars%Units = 'kJ/m^2'
  grid%tail_statevars%Type    = 'r'
  grid%tail_statevars%ProcOrient    = ' '
  grid%tail_statevars%MemoryOrder  = 'XY'
  grid%tail_statevars%Stagger      = 'Z'
  grid%tail_statevars%Ntl     = 0
  grid%tail_statevars%Ndim    = 2
  grid%tail_statevars%Restart  = .TRUE.
  grid%tail_statevars%scalar_array = .FALSE.
  grid%tail_statevars%rfield_2d => grid%iboros
  grid%tail_statevars%streams(1) = 1 
  grid%tail_statevars%streams(2) = 2097152 
  grid%tail_statevars%sd1 = ids
  grid%tail_statevars%ed1 = MAX(1,ide * sr_x) 
  grid%tail_statevars%sd2 = jds
  grid%tail_statevars%ed2 = MAX(1,jde * sr_y) 
  grid%tail_statevars%sd3 = 1
  grid%tail_statevars%ed3 = 1
  grid%tail_statevars%sm1 = (ims-1)*sr_x+1
  grid%tail_statevars%em1 = MAX(1,ime*sr_x)
  grid%tail_statevars%sm2 = (jms-1)*sr_y+1
  grid%tail_statevars%em2 = MAX(1,jme*sr_y)
  grid%tail_statevars%sm3 = 1
  grid%tail_statevars%em3 = 1
  grid%tail_statevars%sp1 = (ips-1)*sr_x+1
  grid%tail_statevars%ep1 = MAX(1,ipe*sr_x)
  grid%tail_statevars%sp2 = (jps-1)*sr_y+1
  grid%tail_statevars%ep2 = MAX(1,jpe*sr_y)
  grid%tail_statevars%sp3 = 1
  grid%tail_statevars%ep3 = 1
  grid%tail_statevars%subgrid_x = .TRUE.
  grid%tail_statevars%subgrid_y = .TRUE.
  grid%tail_statevars%dimname1 = 'west_east_subgrid'
  grid%tail_statevars%dimname2 = 'south_north_subgrid'
  grid%tail_statevars%dimname3 = ''
  ENDIF
ELSE
  ALLOCATE(grid%iboros(1,1),STAT=ierr)
  if (ierr.ne.0) then
    CALL wrf_error_fatal3("<stdin>",4314,&
    'frame/module_domain.f: Failed to allocate grid%iboros(1,1).  ')
  endif
ENDIF
IF ( setinitval .EQ. 3 ) grid%ifire=0
IF ( setinitval .EQ. 3 ) grid%fire_boundary_guard=0
IF ( setinitval .EQ. 3 ) grid%fire_num_ignitions=0
IF ( setinitval .EQ. 3 ) grid%fire_ignition_ros1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lon1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lat1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lon1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lat1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_radius1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_time1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_time1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_ros2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lon2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lat2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lon2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lat2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_radius2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_time2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_time2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_ros3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lon3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lat3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lon3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lat3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_radius3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_time3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_time3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_ros4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lon4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lat4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lon4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lat4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_radius4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_time4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_time4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_ros5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lon5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_lat5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lon5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_lat5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_radius5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_time5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_time5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_x1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_y1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_x1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_y1=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_x2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_y2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_x2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_y2=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_x3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_y3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_x3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_y3=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_x4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_y4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_x4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_y4=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_x5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_start_y5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_x5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ignition_end_y5=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_lat_init=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_lon_init=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ign_time=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_shape=0
IF ( setinitval .EQ. 3 ) grid%fire_sprd_mdl=0
IF ( setinitval .EQ. 3 ) grid%fire_crwn_hgt=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ext_grnd=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_ext_crwn=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_sfc_flx=0
IF ( setinitval .EQ. 3 ) grid%fire_heat_peak=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_tg_ub=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_smk_scheme=0
IF ( setinitval .EQ. 3 ) grid%fire_smk_peak=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_smk_ext=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_wind_height=initial_data_value
IF ( setinitval .EQ. 3 ) grid%fire_fuel_read=0
IF ( setinitval .EQ. 3 ) grid%fire_fuel_cat=0
IF ( setinitval .EQ. 3 ) grid%fire_fmc_read=0
IF ( setinitval .EQ. 3 ) grid%fire_print_msg=0
IF ( setinitval .EQ. 3 ) grid%fire_print_file=0
IF ( setinitval .EQ. 3 ) grid%fire_fuel_left_method=0
IF ( setinitval .EQ. 3 ) grid%fire_fuel_left_irl=0
IF ( setinitval .EQ. 3 ) grid%fire_fuel_left_jrl=0
IF ( setinitval .EQ. 3 ) grid%fire_grows_only=0
IF ( setinitval .EQ. 3 ) grid%fire_upwinding=0
IF ( setinitval .EQ. 3 ) grid%fire_upwind_split=0
IF ( setinitval .EQ. 3 ) grid%fire_viscosity=initial_data_value




   END SUBROUTINE alloc_space_field_core_5


END MODULE module_alloc_space_5



