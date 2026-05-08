



module module_fr_fire_atm

use module_model_constants, only: cp,xlv
use module_fr_fire_util
use module_state_description, only: num_tracer 
use module_state_description, only: p_fire_smoke

contains


subroutine add_fire_tracer_emissions(    &
       tracer_opt,dt,dx,dy,              &
       ifms,ifme,jfms,jfme,              &
       ifts,ifte,jtfs,jfte,              &
       ids,ide,kds,kde,jds,jde,          &
       ims,ime,kms,kme,jms,jme,          &
       its,ite,kts,kte,jts,jte,          &
       rho,dz8w,                         &
       burnt_area_dt,fgip,               &
       tracer,fire_tracer_smoke,         &
       fire_smk_scheme,fire_smk_peak,fire_smk_ext,fire_tg_ub,zs,z_at_w  & 
)

implicit none

integer,intent(in)::tracer_opt
real,intent(in)::fire_tracer_smoke
real,intent(in)::dt,dx,dy
integer,intent(in)::ifms,ifme,jfms,jfme,ifts,ifte,jtfs,jfte,ids,ide,kds,kde,jds,jde,ims,ime,kms,kme,jms,jme,its,ite,kts,kte,jts,jte
real,intent(in)::rho(ims:ime,kms:kme,jms:jme),dz8w(ims:ime,kms:kme,jms:jme)
real,intent(in),dimension(ifms:ifme,jfms:jfme)::burnt_area_dt,fgip
real,intent(inout)::tracer(ims:ime,kms:kme,jms:jme,num_tracer)

integer, intent(in) :: fire_smk_scheme 
real, intent(in) :: fire_smk_peak 
real, intent(in) :: fire_smk_ext  
real, intent(in) :: fire_tg_ub    
real, intent(in), dimension( ims:ime,kms:kme,jms:jme ) :: z_at_w 
real, intent(in), dimension( ims:ime,jms:jme ) :: zs  


integer::isz1,jsz1,isz2,jsz2,ir,jr
integer::i,j,ibase,jbase,i_f,ioff,j_f,joff
real::avgw,emis,conv
integer :: i_st,i_en,j_st,j_en


integer :: k,k_st,k_en
real, dimension(its:ite,kts:kte,jts:jte) :: prop_smk

isz1 = ite-its+1
jsz1 = jte-jts+1
isz2 = ifte-ifts+1
jsz2 = jfte-jtfs+1
ir=isz2/isz1
jr=jsz2/jsz1
avgw = 1.0/(ir*jr)


i_st = MAX(its,ids+1)
i_en = MIN(ite,ide-2)
j_st = MAX(jts,jds+1)
j_en = MIN(jte,jde-2)


if (fire_smk_scheme .eq. 1) then
   k_st = kts
   k_en = MIN(kte,kde-1)
   call tg_dist(ims,ime, kms,kme, jms,jme, &
                i_st,i_en, j_st,j_en, k_st,k_en, dz8w, &
                fire_smk_peak,fire_tg_ub,fire_smk_ext,z_at_w,zs, &
                prop_smk)
end if

do j=j_st,j_en
    jbase=jtfs+jr*(j-jts)
    do i=i_st,i_st
       ibase=ifts+ir*(i-its)
       do joff=0,jr-1
           j_f=joff+jbase
           do ioff=0,ir-1
               i_f=ioff+ibase
               if (num_tracer > 0)then
                  if (fire_smk_scheme .eq. 0)then
                     emis=avgw*fire_tracer_smoke*burnt_area_dt(i_f,j_f)*fgip(i_f,j_f)*1000/(rho(i,kts,j)*dz8w(i,kts,j)) 
                     tracer(i,kts,j,p_fire_smoke)=tracer(i,kts,j,p_fire_smoke)+emis
                  
                  else if (fire_smk_scheme .eq. 1)then
                     do k = k_st,k_en
                        emis=prop_smk(i,k,j)*avgw*fire_tracer_smoke*burnt_area_dt(i_f,j_f)*fgip(i_f,j_f)*1000/(rho(i,k,j)*dz8w(i,k,j)) 
                        tracer(i,k,j,p_fire_smoke)=tracer(i,k,j,p_fire_smoke)+emis
                     end do
                  else
                     call wrf_error_fatal3("<stdin>",98,&
'Invalid fire smoke release option: check fire_smk_scheme namelist option')
                  end if
               end if
           enddo
       enddo
    enddo
enddo

end subroutine add_fire_tracer_emissions





SUBROUTINE fire_tendency( &
    ids,ide, kds,kde, jds,jde,   & 
    ims,ime, kms,kme, jms,jme,   &
    its,ite, kts,kte, jts,jte,   &
    grnhfx,grnqfx,canhfx,canqfx, & 
    alfg,alfc,z1can,             & 
    fire_sfc_flx,fire_heat_peak,fire_tg_ub,  & 
    zs,z_at_w,dz8w,mu,c1h,c2h,rho, &
    rthfrten,rqvfrten)             








   IMPLICIT NONE



   INTEGER , INTENT(in) :: ids,ide, kds,kde, jds,jde, &
                           ims,ime, kms,kme, jms,jme, &
                           its,ite, kts,kte, jts,jte

   REAL, INTENT(in), DIMENSION( ims:ime,jms:jme ) :: grnhfx,grnqfx  
   REAL, INTENT(in), DIMENSION( ims:ime,jms:jme ) :: canhfx,canqfx  
   REAL, INTENT(in), DIMENSION( ims:ime,jms:jme ) :: zs  
   REAL, INTENT(in), DIMENSION( ims:ime,jms:jme ) :: mu  
   REAL, INTENT(in), DIMENSION( kms:kme         ) :: c1h, c2h 

   REAL, INTENT(in), DIMENSION( ims:ime,kms:kme,jms:jme ) :: z_at_w 
   REAL, INTENT(in), DIMENSION( ims:ime,kms:kme,jms:jme ) :: dz8w   
   REAL, INTENT(in), DIMENSION( ims:ime,kms:kme,jms:jme ) :: rho    

   REAL, INTENT(in) :: alfg 
   REAL, INTENT(in) :: alfc 
   REAL, INTENT(in) :: z1can    
   INTEGER, INTENT(in) :: fire_sfc_flx  
   REAL, INTENT(in) :: fire_heat_peak   
   REAL, INTENT(in) :: fire_tg_ub       



   REAL, INTENT(out), DIMENSION( ims:ime,kms:kme,jms:jme ) ::   &
       rthfrten, & 
       rqvfrten    


   INTEGER :: i,j,k
   INTEGER :: i_st,i_en, j_st,j_en, k_st,k_en

   REAL :: cp_i
   REAL :: rho_i
   REAL :: xlv_i
   REAL :: z_w
   REAL :: fact_g, fact_c
   REAL :: alfg_i, alfc_i

   REAL, DIMENSION( its:ite,kts:kte,jts:jte ) :: prop_heat 

   REAL, DIMENSION( its:ite,kts:kte,jts:jte ) :: hfx,qfx
   


        do j=jts,jte
            do k=kts,min(kte+1,kde)
               do i=its,ite
                   rthfrten(i,k,j)=0.
                   rqvfrten(i,k,j)=0.
               enddo
            enddo
        enddo



   

   cp_i = 1./cp     
   xlv_i = 1./xlv   
   alfg_i = 1./alfg
   alfc_i = 1./alfc




   call print_2d_stats(its,ite,jts,jte,ims,ime,jms,jme,grnhfx,'fire_tendency:grnhfx')
   call print_2d_stats(its,ite,jts,jte,ims,ime,jms,jme,grnqfx,'fire_tendency:grnqfx')



   i_st = MAX(its,ids+1)
   i_en = MIN(ite,ide-1)
   k_st = kts
   k_en = MIN(kte,kde-1)
   j_st = MAX(jts,jds+1)
   j_en = MIN(jte,jde-1)


   if (fire_sfc_flx .eq. 1) then 
      call tg_dist(ims,ime, kms,kme, jms,jme, &
                   i_st,i_en, j_st,j_en, k_st,k_en, dz8w, &
                   fire_heat_peak,fire_tg_ub,alfg,z_at_w,zs, &
                   prop_heat)
   end if


   DO j = j_st,j_en
      DO k = k_st,k_en
         DO i = i_st,i_en
            if (fire_sfc_flx .eq. 0) then
                
                z_w = z_at_w(i,k,j) - zs(i,j) 

                
                fact_g = cp_i * EXP( - alfg_i * z_w )
                IF ( z_w < z1can ) THEN
                   fact_c = cp_i
                ELSE
                   fact_c = cp_i * EXP( - alfc_i * (z_w - z1can) )
                END IF
                hfx(i,k,j) = fact_g * grnhfx(i,j) + fact_c * canhfx(i,j)





                

                fact_g = xlv_i * EXP( - alfg_i * z_w )
                IF (z_w < z1can) THEN
                   fact_c = xlv_i
                ELSE
                   fact_c = xlv_i * EXP( - alfc_i * (z_w - z1can) )
                END IF
                qfx(i,k,j) = fact_g * grnqfx(i,j) + fact_c * canqfx(i,j)
            





            else if (fire_sfc_flx .eq. 1) then 
               
               fact_g = prop_heat(i,k,j) * cp_i
               IF ( z_w < z1can ) THEN
                  fact_c = cp_i
               ELSE
                  fact_c = cp_i * prop_heat(i,k,j)
               END IF
               hfx(i,k,j) = fact_g * grnhfx(i,j) + fact_c * canqfx(i,j)
            
               
               fact_g = prop_heat(i,k,j) * xlv_i
               IF (z_w < z1can) THEN
                  fact_c = xlv_i
               ELSE
                  fact_c = xlv_i * prop_heat(i,k,j)
               END IF
               qfx(i,k,j) = fact_g * grnqfx(i,j) + fact_c * canqfx(i,j)

            else
               call wrf_error_fatal3("<stdin>",275,&
'Invalid fire heat release option: check fire_sfc_flx namelist option')
            end if

         END DO
      END DO
   END DO






   DO j = j_st,j_en
      DO k = k_st,k_en-1
         DO i = i_st,i_en

            rho_i = 1./rho(i,k,j)

            rthfrten(i,k,j) = - (c1h(k)*mu(i,j)+c2h(k)) * rho_i * (hfx(i,k+1,j)-hfx(i,k,j)) / dz8w(i,k,j)
            rqvfrten(i,k,j) = - (c1h(k)*mu(i,j)+c2h(k)) * rho_i * (qfx(i,k+1,j)-qfx(i,k,j)) / dz8w(i,k,j)

         END DO
      END DO
   END DO

   call print_3d_stats(its,ite,kts,kte,jts,jte,ims,ime,kms,kme,jms,jme,rthfrten,'fire_tendency:rthfrten')
   call print_3d_stats(its,ite,kts,kte,jts,jte,ims,ime,kms,kme,jms,jme,rqvfrten,'fire_tendency:rqvfrten')

   RETURN

END SUBROUTINE fire_tendency

SUBROUTINE tg_dist(ims,ime, kms,kme, jms,jme, &
                   i_st,i_en, j_st,j_en, k_st,k_en, dz8w, &
                   fire_peak_hgt,fire_tg_ub,fire_ext_depth,z_at_w,zs, &
                   prop)
   
   
   

   IMPLICIT NONE

   INTEGER, INTENT(in) :: ims,ime, kms,kme, jms,jme
   INTEGER, INTENT(in) :: i_st,i_en, j_st,j_en, k_st,k_en     
   REAL, INTENT(in), DIMENSION( ims:ime,kms:kme,jms:jme ) :: dz8w   
   REAL, INTENT(in) :: fire_peak_hgt    
   REAL, INTENT(in) :: fire_tg_ub       
   REAL, INTENT(in) :: fire_ext_depth   
   REAL, INTENT(in), DIMENSION( ims:ime,kms:kme,jms:jme ) :: z_at_w 
   REAL, INTENT(in), DIMENSION( ims:ime,jms:jme ) :: zs  
   REAL, INTENT(out), DIMENSION( i_st:i_en,k_st:k_en,j_st:j_en ) :: prop 

   
   INTEGER :: i,j,k

   REAL, PARAMETER :: acoef = 167./148., bcoef = 11./109., fire_tg_lb = 0.
   REAL :: xia, xib
   REAL :: phi_a, phi_b
   REAL :: xi
   REAL :: dz
   REAL :: z_w
   REAL :: prop_temp

   xia = (fire_tg_lb-fire_peak_hgt)/(0.5*fire_ext_depth)
   xib = (fire_tg_ub-fire_peak_hgt)/(0.5*fire_ext_depth)

   phi_a = 0.5*(1.+tanh(acoef*xia+bcoef*(xia**3)))
   phi_b = 0.5*(1.+tanh(acoef*xib+bcoef*(xib**3)))

   DO j = j_st,j_en
      DO k = k_st,k_en
         DO i = i_st,i_en

            xi=(z_w-fire_peak_hgt)/(0.5*fire_ext_depth)

            prop_temp = 0.5*(acoef+3.*bcoef*(xi**2))/(0.5*fire_ext_depth)*(1.-(tanh(acoef*xi+bcoef*(xi**3)))**2)
            prop_temp = prop_temp / (phi_b-phi_a)
   
            
            if (k .eq. k_st) then
               dz = 0.5 * dz8w(i,k,j)
            else if (k .eq. k_en) then
               dz = 0.5 * dz8w(i,k-1,j)
            else
               dz = 0.5 * (dz8w(i,k,j) + dz8w(i,k-1,j))
            end if

            prop(i,k,j) = prop_temp * dz

         END DO
      END DO
   END DO

END SUBROUTINE tg_dist





end module module_fr_fire_atm


