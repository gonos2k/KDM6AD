

 module module_bl_mynn_common















  use ccpp_kind_types,  only : kind_phys




  use module_model_constants, only:         &
    & karman, g, p1000mb,                   &
    & cp, r_d, r_v, rcp, xlv, xlf, xls,     &
    & svp1, svp2, svp3, p608, ep_2, rvovrd, &                                                                         
    & cpv, cliq, cice, svpt0

 implicit none
 save





























 integer, parameter :: sp = selected_real_kind(6, 37)
 integer, parameter :: dp = selected_real_kind(15, 307)

 real(kind_phys),parameter:: zero   = 0.0
 real(kind_phys),parameter:: half   = 0.5
 real(kind_phys),parameter:: one    = 1.0
 real(kind_phys),parameter:: two    = 2.0
 real(kind_phys),parameter:: onethird  = 1./3.
 real(kind_phys),parameter:: twothirds = 2./3.
 real(kind_phys),parameter:: tref  = 300.0   
 real(kind_phys),parameter:: TKmin = 253.0   




 real(kind_phys),parameter:: tice  = 240.0  
 real(kind_phys),parameter:: grav  = g
 real(kind_phys),parameter:: t0c   = svpt0        


 real(kind_phys),parameter:: ep_3   = 1.-ep_2 
 real(kind_phys),parameter:: gtr    = grav/tref
 real(kind_phys),parameter:: rk     = cp/r_d
 real(kind_phys),parameter:: tv0    =  p608*tref
 real(kind_phys),parameter:: tv1    = (1.+p608)*tref
 real(kind_phys),parameter:: xlscp  = (xlv+xlf)/cp
 real(kind_phys),parameter:: xlvcp  = xlv/cp
 real(kind_phys),parameter:: g_inv  = 1./grav












 end module module_bl_mynn_common


