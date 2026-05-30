
MODULE sf_sfclayrev
























  USE ccpp_kind_types,ONLY: kind_phys

  IMPLICIT NONE
  PRIVATE
  PUBLIC:: sf_sfclayrev_run,     &
           sf_sfclayrev_init,    &
           sf_sfclayrev_finalize


  REAL(kind=kind_phys),PARAMETER:: vconvc= 1.
  REAL(kind=kind_phys),PARAMETER:: czo   = 0.0185
  REAL(kind=kind_phys),PARAMETER:: ozo   = 1.59e-5

  REAL(kind=kind_phys),DIMENSION(0:1000 ),SAVE:: psim_stab,psim_unstab,psih_stab,psih_unstab


CONTAINS






  SUBROUTINE sf_sfclayrev_init(errmsg,errflg)



  CHARACTER(len=*),INTENT(OUT):: errmsg
  INTEGER,INTENT(OUT):: errflg


  INTEGER:: n
  REAL(kind=kind_phys):: zolf



  DO n = 0,1000

    zolf = float(n)*0.01
    psim_stab(n)=psim_stable_full(zolf)
    psih_stab(n)=psih_stable_full(zolf)


    zolf = -float(n)*0.01
    psim_unstab(n)=psim_unstable_full(zolf)
    psih_unstab(n)=psih_unstable_full(zolf)
  ENDDO

  errmsg = 'sf_sfclayrev_init OK'
  errflg = 0

  END SUBROUTINE sf_sfclayrev_init





  SUBROUTINE sf_sfclayrev_finalize(errmsg,errflg)



  CHARACTER(len=*),INTENT(OUT):: errmsg
  INTEGER,INTENT(OUT):: errflg



  errmsg = 'sf_sfclayrev_finalize OK'
  errflg = 0

  END SUBROUTINE sf_sfclayrev_finalize





  SUBROUTINE sf_sfclayrev_run(ux,vx,t1d,qv1d,p1d,dz8w1d,               &
                               cp,g,rovcp,r,xlv,psfcpa,chs,chs2,cqs2,   &
                               cpm,pblh,rmol,znt,ust,mavail,zol,mol,   &
                               regime,psim,psih,fm,fh,                 &
                               xland,hfx,qfx,tsk,                      &
                               u10,v10,th2,t2,q2,                      &

                               u80,v80,u140,v140,u220,v220,            &
                               flhc,flqc,qgh,                    &
                               qsfc,lh,gz1oz0,wspd,br,isfflx,dx,       &
                               svp1,svp2,svp3,svpt0,ep1,ep2,           &
                               karman,p1000mb,lakemask,                &
                               shalwater_z0,water_depth,               &
                               isftcflx,iz0tlnd,scm_force_flux,        &
                               ustm,ck,cka,cd,cda,                     &
                               charnock,                               & 
                               its,ite,errmsg,errflg                   &
                               )



  LOGICAL,INTENT(IN):: isfflx
  LOGICAL,INTENT(IN):: shalwater_z0
  LOGICAL,INTENT(IN),OPTIONAL:: scm_force_flux

  INTEGER,INTENT(IN):: its,ite
  INTEGER,INTENT(IN),OPTIONAL:: isftcflx, iz0tlnd

  REAL(kind=kind_phys),INTENT(IN):: svp1,svp2,svp3,svpt0
  REAL(kind=kind_phys),INTENT(IN):: ep1,ep2,karman
  REAL(kind=kind_phys),INTENT(IN):: p1000mb
  REAL(kind=kind_phys),INTENT(IN):: cp,g,rovcp,r,xlv

  REAL(kind=kind_phys),INTENT(IN),DIMENSION(its:):: &
     mavail,       &
     pblh,         &
     psfcpa,       &
     tsk,          &
     xland,        &
     lakemask,     &
     water_depth,  &
     charnock 

  REAL(kind=kind_phys),INTENT(IN),DIMENSION(its:):: &
     dx,         &
     dz8w1d,     &    
     ux,         &
     vx,         &
     qv1d,       &
     p1d,        &
     t1d


  CHARACTER(len=*),INTENT(OUT):: errmsg
  INTEGER,INTENT(OUT):: errflg

  REAL(kind=kind_phys),INTENT(OUT),DIMENSION(its:):: &
     lh,         &
     u10,        &
     v10,        &
     th2,        &
     t2,         &
     q2,         &

     u80,        &
     v80,        &
     u140,       &
     v140,       &
     u220,       &
     v220

  REAL(kind=kind_phys),INTENT(OUT),DIMENSION(its:),OPTIONAL:: &
     ck,         &
     cka,        &
     cd,         &
     cda


  REAL(kind=kind_phys),INTENT(INOUT),DIMENSION(its:):: &
     regime,     &
     hfx,        &
     qfx,        &
     qsfc,       &
     mol,        &
     rmol,       &
     gz1oz0,     &
     wspd,       &
     br,         &
     psim,       &
     psih,       &
     fm,         &
     fh,         &
     znt,        &
     zol,        &
     ust,        &
     cpm,        &
     chs2,       &
     cqs2,       &
     chs,        &
     flhc,       &
     flqc,       &
     qgh

  REAL(kind=kind_phys),INTENT(INOUT),DIMENSION(its:),OPTIONAL:: &
     ustm


  INTEGER:: n,i,k,kk,l,nzol,nk,nzol2,nzol10

  REAL(kind=kind_phys),PARAMETER:: xka = 2.4e-5
  REAL(kind=kind_phys),PARAMETER:: prt = 1.
  REAL(kind=kind_phys),PARAMETER:: salinity_factor = 0.98

  REAL(kind=kind_phys):: pl,thcon,tvcon,e1
  REAL(kind=kind_phys):: zl,tskv,dthvdz,dthvm,vconv,rzol,rzol2,rzol10,zol2,zol10
  REAL(kind=kind_phys):: dtg,psix,dtthx,psix10,psit,psit2,psiq,psiq2,psiq10
  REAL(kind=kind_phys):: fluxc,vsgd,z0q,visc,restar,czil,gz0ozq,gz0ozt
  REAL(kind=kind_phys):: zw,zn1,zn2
  REAL(kind=kind_phys):: zolzz,zol0
  REAL(kind=kind_phys):: zl2,zl10,z0t

  REAL(kind=kind_phys):: psix80, psix140, psix220


  REAL, PARAMETER :: Z_SURF_LAYER_MAX    = 250.0   
  REAL, PARAMETER :: Z0_MIN              = 1.E-8   
  REAL, PARAMETER :: CALM_WIND_THRESHOLD = 1.E-4   

  REAL(kind=kind_phys),DIMENSION(its:ite):: &
     za,         &
     thvx,       &
     zqkl,       &
     zqklp1,     &
     thx,        &
     qx,         &
     psih2,      &
     psim2,      &
     psih10,     &
     psim10,     &

     psim80,     &
     psim140,    &
     psim220,    &
     gz80oz0,    &
     gz140oz0,   &
     gz220oz0,   &

     denomq,     &
     denomq2,    &
     denomt2,    &
     wspdi,      &
     gz2oz0,     &
     gz10oz0,    &
     rhox,       &
     govrth,     &
     tgdsa,      &
     scr3,       &
     scr4,       &
     thgb,       &
     psfc

  REAL(kind=kind_phys),DIMENSION(its:ite):: &
     pq,         &
     pq2,        &
     pq10



  do i = its,ite

    psfc(i)=psfcpa(i)/1000.
  enddo



  do 5 i = its,ite                                         
    tgdsa(i)=tsk(i)                                        


    thgb(i)=tsk(i)*(p1000mb/psfcpa(i))**rovcp   
  5 continue                                                      








  10 continue                                                     
                                                                    
  26 continue                                                   



                                                                    
  do 30 i = its,ite

    pl=p1d(i)/1000.
    scr3(i)=t1d(i)                                                     

    thcon=(p1000mb*0.001/pl)**rovcp
    thx(i)=scr3(i)*thcon                                         
    scr4(i)=scr3(i)                                            
    thvx(i)=thx(i)                                                 
    qx(i)=0.                                                       
  30 continue                                                       

  do i = its,ite
    qgh(i)=0.                                                      
    flhc(i)=0.                                                     
    flqc(i)=0.                                                     
    cpm(i)=cp                                                      
  enddo


  do 50 i = its,ite
    qx(i)=qv1d(i)                                              
    tvcon=(1.+ep1*qx(i))                                     
    thvx(i)=thx(i)*tvcon                                           
    scr4(i)=scr3(i)*tvcon                                      
  50 continue                                                       

  do 60 i=its,ite
    e1=svp1*exp(svp2*(tgdsa(i)-svpt0)/(tgdsa(i)-svp3))                
    
    if(xland(i).gt.1.5 .and. lakemask(i).eq.0.) e1=e1*salinity_factor
    
    if(xland(i).gt.1.5.or.qsfc(i).le.0.0)qsfc(i)=ep2*e1/(psfc(i)-e1)                      


    e1=svp1*exp(svp2*(t1d(i)-svpt0)/(t1d(i)-svp3))                
    pl=p1d(i)/1000.
    qgh(i)=ep2*e1/(pl-e1)                                          
    cpm(i)=cp*(1.+0.8*qx(i))                         
  60 continue                                                       
  80 continue



                                                                    
  do 90 i = its,ite
    zqklp1(i)=0.
    rhox(i)=psfc(i)*1000./(r*scr4(i))                              
  90 continue                                                       

  do 110 i = its,ite                                       
    zqkl(i)=dz8w1d(i)+zqklp1(i)
  110 continue                                                      

  do 120 i = its,ite
    za(i)=0.5*(zqkl(i)+zqklp1(i))                               
  120 continue                                                      

  do 160 i=its,ite
    govrth(i)=g/thx(i)                                       
  160 continue                                                      
                                                                    


  do 260 i = its,ite

    IF (za(i) > Z_SURF_LAYER_MAX) CYCLE 


    IF (znt(i) < Z0_MIN) znt(i) = Z0_MIN

    gz1oz0(i)=alog((za(i)+znt(i))/znt(i))   
    gz2oz0(i)=alog((2.+znt(i))/znt(i))    
    gz10oz0(i)=alog((10.+znt(i))/znt(i))   

    gz80oz0(i) = alog((80. + znt(i)) / znt(i))
    gz140oz0(i) = alog((140. + znt(i)) / znt(i))
    gz220oz0(i) = alog((220. + znt(i)) / znt(i))
    
    if((xland(i)-1.5).ge.0)then                                    
        zl=znt(i)                                                  
    else                                                         
        zl=0.01                                                    
    endif                                                      
    wspd(i)=sqrt(ux(i)*ux(i)+vx(i)*vx(i))                 

    tskv=thgb(i)*(1.+ep1*qsfc(i))                      
    dthvdz=(thvx(i)-tskv)                                            






    if(xland(i).lt.1.5) then
       fluxc = max(hfx(i)/rhox(i)/cp                     &
                   + ep1*tskv*qfx(i)/rhox(i),0.)
       vconv = vconvc*(g/tgdsa(i)*pblh(i)*fluxc)**.33
    else
       if(-dthvdz.ge.0)then
          dthvm=-dthvdz
       else
          dthvm=0.
       endif


       vconv = sqrt(dthvm)
    endif

    vsgd = 0.32 * (max(dx(i)/5000.-1.,0.))**.33
    wspd(i)=sqrt(wspd(i)*wspd(i)+vconv*vconv+vsgd*vsgd)
    wspd(i)=amax1(wspd(i),0.1)
    br(i)=govrth(i)*za(i)*dthvdz/(wspd(i)*wspd(i))                 

    if(mol(i).lt.0.)br(i)=amin1(br(i),0.0)
    rmol(i)=-govrth(i)*dthvdz*za(i)*karman
  260 continue



















  do 320 i = its,ite

    IF (za(i) > Z_SURF_LAYER_MAX) CYCLE

    if(br(i).gt.0) then
        if(br(i).gt.250.0) then
           zol(i)=zolri(250.0,za(i),znt(i))
        else
           zol(i)=zolri(br(i),za(i),znt(i))
        endif
    endif

    if(br(i).lt.0) then
        if(ust(i).lt.0.001)then
           zol(i)=br(i)*gz1oz0(i)
        else
           if(br(i).lt.-250.0) then
             zol(i)=zolri(-250.0,za(i),znt(i))
           else
              zol(i)=zolri(br(i),za(i),znt(i))
           endif
        endif
    endif



    zolzz=zol(i)*(za(i)+znt(i))/za(i) 
    zol10=zol(i)*(10.+znt(i))/za(i)   
    zol2=zol(i)*(2.+znt(i))/za(i)     
    zol0=zol(i)*znt(i)/za(i)          
    zl2=(2.)/za(i)*zol(i)             
    zl10=(10.)/za(i)*zol(i)           

    if((xland(i)-1.5).lt.0.)then
        zl=(0.01)/za(i)*zol(i)        
    else
        zl=zol0                       
    endif

    if(br(i).lt.0.)goto 310  
    if(br(i).eq.0.)goto 280  



    regime(i)=1.



    psim(i)=psim_stable(zolzz)-psim_stable(zol0)
    psih(i)=psih_stable(zolzz)-psih_stable(zol0)

    psim10(i)=psim_stable(zol10)-psim_stable(zol0)
    psih10(i)=psih_stable(zol10)-psih_stable(zol0)

    psim2(i)=psim_stable(zol2)-psim_stable(zol0)
    psih2(i)=psih_stable(zol2)-psih_stable(zol0)

    psim80(i)  = psim_stable(zol(i)*(80. +znt(i))/za(i)) - psim_stable(zol0)
    psim140(i) = psim_stable(zol(i)*(140.+znt(i))/za(i)) - psim_stable(zol0)
    psim220(i) = psim_stable(zol(i)*(220.+znt(i))/za(i)) - psim_stable(zol0)



    pq(i)=psih_stable(zol(i))-psih_stable(zl)
    pq2(i)=psih_stable(zl2)-psih_stable(zl)
    pq10(i)=psih_stable(zl10)-psih_stable(zl)


    rmol(i)=zol(i)/za(i) 

    goto 320                                                      



  280 regime(i)=3.                                                
      psim(i)=0.0                                                  
      psih(i)=psim(i)                                                  
      psim10(i)=0.                                             
      psih10(i)=psim10(i)                                          
      psim2(i)=0.                                            
      psih2(i)=psim2(i)                                          

      psim80(i)=0.0; psim140(i)=0.0; psim220(i)=0.0



      pq(i)=psih(i)
      pq2(i)=psih2(i)
      pq10(i)=0.

      zol(i)=0.                                              
      rmol(i) = zol(i)/za(i)  

      goto 320                                                      



  310 continue                                                      
      regime(i)=4.                                                



      psim(i)=psim_unstable(zolzz)-psim_unstable(zol0)
      psih(i)=psih_unstable(zolzz)-psih_unstable(zol0)

      psim10(i)=psim_unstable(zol10)-psim_unstable(zol0)
      psih10(i)=psih_unstable(zol10)-psih_unstable(zol0)

      psim2(i)=psim_unstable(zol2)-psim_unstable(zol0)
      psih2(i)=psih_unstable(zol2)-psih_unstable(zol0)

      psim80(i)  = psim_unstable(zol(i)*(80. +znt(i))/za(i)) - psim_unstable(zol0)
      psim140(i) = psim_unstable(zol(i)*(140.+znt(i))/za(i)) - psim_unstable(zol0)
      psim220(i) = psim_unstable(zol(i)*(220.+znt(i))/za(i)) - psim_unstable(zol0)



      pq(i)=psih_unstable(zol(i))-psih_unstable(zl)
      pq2(i)=psih_unstable(zl2)-psih_unstable(zl)
      pq10(i)=psih_unstable(zl10)-psih_unstable(zl)



      psih(i)=amin1(psih(i),0.9*gz1oz0(i))
      psim(i)=amin1(psim(i),0.9*gz1oz0(i))
      psih2(i)=amin1(psih2(i),0.9*gz2oz0(i))
      psim10(i)=amin1(psim10(i),0.9*gz10oz0(i))

      psim80(i)  = amin1(psim80(i),  0.9*gz80oz0(i))
      psim140(i) = amin1(psim140(i), 0.9*gz140oz0(i))
      psim220(i) = amin1(psim220(i), 0.9*gz220oz0(i))


      psih10(i)=amin1(psih10(i),0.9*gz10oz0(i))
      rmol(i) = zol(i)/za(i)  

  320 continue                                                          




  do 330 i = its,ite

    IF (za(i) > Z_SURF_LAYER_MAX) CYCLE

    dtg=thx(i)-thgb(i)                                             
    psix=gz1oz0(i)-psim(i)                                         
    psix10=gz10oz0(i)-psim10(i)




    psit=gz1oz0(i)-psih(i)
    psit2=gz2oz0(i)-psih2(i)

    if((xland(i)-1.5).ge.0)then                                    
        zl=znt(i)                                                  
    else                                                         
        zl=0.01                                                    
    endif                                                      

    psiq=alog(karman*ust(i)*za(i)/xka+za(i)/zl)-pq(i)
    psiq2=alog(karman*ust(i)*2./xka+2./zl)-pq2(i)


    psiq10=alog(karman*ust(i)*10./xka+10./zl)-pq10(i)



    if((xland(i)-1.5).ge.0.) then
       visc=(1.32+0.009*(scr3(i)-273.15))*1.e-5
       restar=ust(i)*znt(i)/visc
       z0t = (5.5e-5)*(restar**(-0.60))
       z0t = min(z0t,1.0e-4)
       z0t = max(z0t,2.0e-9)
       z0q = z0t


       zolzz=zol(i)*(za(i)+z0t)/za(i) 
       zol10=zol(i)*(10.+z0t)/za(i)   
       zol2=zol(i)*(2.+z0t)/za(i)     
       zol0=zol(i)*z0t/za(i)          

       if(zol(i).gt.0.) then
          psih(i)=psih_stable(zolzz)-psih_stable(zol0)
          psih10(i)=psih_stable(zol10)-psih_stable(zol0)
          psih2(i)=psih_stable(zol2)-psih_stable(zol0)
       else
          if(zol(i).eq.0) then
             psih(i)=0.
             psih10(i)=0.
             psih2(i)=0.
          else
             psih(i)=psih_unstable(zolzz)-psih_unstable(zol0)
             psih10(i)=psih_unstable(zol10)-psih_unstable(zol0)
             psih2(i)=psih_unstable(zol2)-psih_unstable(zol0)
          endif
       endif
       psit=alog((za(i)+z0t)/z0t)-psih(i)
       psit2=alog((2.+z0t)/z0t)-psih2(i)

       zolzz=zol(i)*(za(i)+z0q)/za(i)   
       zol10=zol(i)*(10.+z0q)/za(i)  
       zol2=zol(i)*(2.+z0q)/za(i)     
       zol0=zol(i)*z0q/za(i)          

       if(zol(i).gt.0.) then
          psih(i)=psih_stable(zolzz)-psih_stable(zol0)
          psih10(i)=psih_stable(zol10)-psih_stable(zol0)
          psih2(i)=psih_stable(zol2)-psih_stable(zol0)
       else
          if(zol(i).eq.0) then
             psih(i)=0.
             psih10(i)=0.
             psih2(i)=0.
          else
             psih(i)=psih_unstable(zolzz)-psih_unstable(zol0)
             psih10(i)=psih_unstable(zol10)-psih_unstable(zol0)
             psih2(i)=psih_unstable(zol2)-psih_unstable(zol0)
             endif
           endif

         psiq=alog((za(i)+z0q)/z0q)-psih(i)
         psiq2=alog((2.+z0q)/z0q)-psih2(i)
         psiq10=alog((10.+z0q)/z0q)-psih10(i)
       endif

       if(present(isftcflx)) then
         if(isftcflx.eq.1 .and. (xland(i)-1.5).ge.0.) then





           z0q = 1.e-4



         zolzz=zol(i)*(za(i)+z0q)/za(i) 
         zol10=zol(i)*(10.+z0q)/za(i)   
         zol2=zol(i)*(2.+z0q)/za(i)     
         zol0=zol(i)*z0q/za(i)          

         if(zol(i).gt.0.) then
            psih(i)=psih_stable(zolzz)-psih_stable(zol0)
            psih10(i)=psih_stable(zol10)-psih_stable(zol0)
            psih2(i)=psih_stable(zol2)-psih_stable(zol0)
         else
            if(zol(i).eq.0) then
               psih(i)=0.
               psih10(i)=0.
               psih2(i)=0.
            else
               psih(i)=psih_unstable(zolzz)-psih_unstable(zol0)
               psih10(i)=psih_unstable(zol10)-psih_unstable(zol0)
               psih2(i)=psih_unstable(zol2)-psih_unstable(zol0)
            endif
         endif

         psiq=alog((za(i)+z0q)/z0q)-psih(i)
         psit=psiq
         psiq2=alog((2.+z0q)/z0q)-psih2(i)
         psiq10=alog((10.+z0q)/z0q)-psih10(i)
         psit2=psiq2
       endif
       if(isftcflx.eq.2 .and. (xland(i)-1.5).ge.0.) then





         visc=(1.32+0.009*(scr3(i)-273.15))*1.e-5

         restar=ust(i)*znt(i)/visc
         gz0ozt=0.40*(7.3*sqrt(sqrt(restar))*sqrt(0.71)-5.)



         z0t=znt(i)/exp(gz0ozt)

         zolzz=zol(i)*(za(i)+z0t)/za(i) 
         zol10=zol(i)*(10.+z0t)/za(i)   
         zol2=zol(i)*(2.+z0t)/za(i)     
         zol0=zol(i)*z0t/za(i)          

         if(zol(i).gt.0.) then
            psih(i)=psih_stable(zolzz)-psih_stable(zol0)
            psih10(i)=psih_stable(zol10)-psih_stable(zol0)
            psih2(i)=psih_stable(zol2)-psih_stable(zol0)
         else
            if(zol(i).eq.0) then
               psih(i)=0.
               psih10(i)=0.
               psih2(i)=0.
            else
               psih(i)=psih_unstable(zolzz)-psih_unstable(zol0)
               psih10(i)=psih_unstable(zol10)-psih_unstable(zol0)
               psih2(i)=psih_unstable(zol2)-psih_unstable(zol0)
            endif
         endif



         psit=alog((za(i)+z0t)/z0t)-psih(i)
         psit2=alog((2.+z0t)/z0t)-psih2(i)

         gz0ozq=0.40*(7.3*sqrt(sqrt(restar))*sqrt(0.60)-5.)
         z0q=znt(i)/exp(gz0ozq)

         zolzz=zol(i)*(za(i)+z0q)/za(i) 
         zol10=zol(i)*(10.+z0q)/za(i)   
         zol2=zol(i)*(2.+z0q)/za(i)     
         zol0=zol(i)*z0q/za(i)          

         if(zol(i).gt.0.) then
            psih(i)=psih_stable(zolzz)-psih_stable(zol0)
            psih10(i)=psih_stable(zol10)-psih_stable(zol0)
            psih2(i)=psih_stable(zol2)-psih_stable(zol0)
         else
            if(zol(i).eq.0) then
               psih(i)=0.
               psih10(i)=0.
               psih2(i)=0.
            else
               psih(i)=psih_unstable(zolzz)-psih_unstable(zol0)
               psih10(i)=psih_unstable(zol10)-psih_unstable(zol0)
               psih2(i)=psih_unstable(zol2)-psih_unstable(zol0)
            endif
         endif

         psiq=alog((za(i)+z0q)/z0q)-psih(i)
         psiq2=alog((2.+z0q)/z0q)-psih2(i)
         psiq10=alog((10.+z0q)/z0q)-psih10(i)



       endif
    endif
    if(present(ck) .and. present(cd) .and. present(cka) .and. present(cda)) then
       ck(i)=(karman/psix10)*(karman/psiq10)
       cd(i)=(karman/psix10)*(karman/psix10)
       cka(i)=(karman/psix)*(karman/psiq)
       cda(i)=(karman/psix)*(karman/psix)
    endif
    if(present(iz0tlnd)) then
       if(iz0tlnd.ge.1 .and. (xland(i)-1.5).le.0.) then
          zl=znt(i)

          visc=(1.32+0.009*(scr3(i)-273.15))*1.e-5
          restar=ust(i)*zl/visc



          if(iz0tlnd.eq.1) then
             czil = 10.0 ** ( -0.40 * ( zl / 0.07 ) )
          elseif(iz0tlnd.eq.2) then
             czil = 0.1 
          endif



          z0t=znt(i)/exp(czil*karman*sqrt(restar))

          zolzz=zol(i)*(za(i)+z0t)/za(i) 
          zol10=zol(i)*(10.+z0t)/za(i)   
          zol2=zol(i)*(2.+z0t)/za(i)     
          zol0=zol(i)*z0t/za(i)          

          if(zol(i).gt.0.) then
             psih(i)=psih_stable(zolzz)-psih_stable(zol0)
             psih10(i)=psih_stable(zol10)-psih_stable(zol0)
             psih2(i)=psih_stable(zol2)-psih_stable(zol0)
          else
             if(zol(i).eq.0) then
                psih(i)=0.
                psih10(i)=0.
                psih2(i)=0.
             else
                psih(i)=psih_unstable(zolzz)-psih_unstable(zol0)
                psih10(i)=psih_unstable(zol10)-psih_unstable(zol0)
                psih2(i)=psih_unstable(zol2)-psih_unstable(zol0)
             endif
          endif

          psiq=alog((za(i)+z0t)/z0t)-psih(i)
          psiq2=alog((2.+z0t)/z0t)-psih2(i)
          psit=psiq
          psit2=psiq2





       endif
    endif

    ust(i)=0.5*ust(i)+0.5*karman*wspd(i)/psix                      

    wspdi(i)=sqrt(ux(i)*ux(i)+vx(i)*vx(i))
    if(present(ustm)) then
       ustm(i)=0.5*ustm(i)+0.5*karman*wspdi(i)/psix
    endif

    u10(i)=ux(i)*psix10/psix                                     
    v10(i)=vx(i)*psix10/psix                                     
    th2(i)=thgb(i)+dtg*psit2/psit                                
    q2(i)=qsfc(i)+(qx(i)-qsfc(i))*psiq2/psiq                  
    t2(i) = th2(i)*(psfcpa(i)/p1000mb)**rovcp                      

    if((xland(i)-1.5).lt.0.)then                                    
        ust(i)=amax1(ust(i),0.001)
    endif                                                      
    mol(i)=karman*dtg/psit/prt                               
    denomq(i)=psiq
    denomq2(i)=psiq2
    denomt2(i)=psit2
    fm(i)=psix
    fh(i)=psit






    IF (wspdi(i) > CALM_WIND_THRESHOLD) THEN
      
      psix80  = gz80oz0(i)  - psim80(i)
      u80(i)  = ux(i) * psix80 / psix
      v80(i)  = vx(i) * psix80 / psix
      
      psix140 = gz140oz0(i) - psim140(i)
      u140(i) = ux(i) * psix140 / psix
      v140(i) = vx(i) * psix140 / psix
      
      psix220 = gz220oz0(i) - psim220(i)
      u220(i) = ux(i) * psix220 / psix
      v220(i) = vx(i) * psix220 / psix
    ELSE
      u80(i)=0.0;  v80(i)=0.0
      u140(i)=0.0; v140(i)=0.0
      u220(i)=0.0; v220(i)=0.0
    ENDIF


  330 continue                                                          


  335 continue                                                          
                                                                      

  if(present(scm_force_flux) ) then
    if(scm_force_flux) goto 350
    endif
    do i = its,ite
       qfx(i)=0.                                                     
       hfx(i)=0.                                                     
    enddo
  350 continue                                                          

  if(.not. isfflx) goto 410


  do 360 i = its,ite
    if((xland(i)-1.5).ge.0)then                                    

       
       
       if(shalwater_z0) then
          znt(i) = depth_dependent_z0(water_depth(i),znt(i),ust(i))
       else
          





          znt(i)=charnock(i)*ust(i)*ust(i)/g+0.11*1.5e-5/ust(i)



          

       endif





       if(present(isftcflx)) then
          if(isftcflx.ne.0) then






            zw  = min((ust(i)/1.06)**(0.3),1.0)
            zn1 = 0.011*ust(i)*ust(i)/g + ozo
            zn2 = 10.*exp(-9.5*ust(i)**(-.3333)) + &
                  0.11*1.5e-5/amax1(ust(i),0.01)
            znt(i)=(1.0-zw) * zn1 + zw * zn2
            znt(i)=min(znt(i),2.85e-3)
            znt(i)=max(znt(i),1.27e-7)
          endif
       endif
       zl = znt(i)
    else
       zl = 0.01
    endif                                                      
    flqc(i)=rhox(i)*mavail(i)*ust(i)*karman/denomq(i)


    dtthx=abs(thx(i)-thgb(i))                               
    if(dtthx.gt.1.e-5)then                                      
       flhc(i)=cpm(i)*rhox(i)*ust(i)*mol(i)/(thx(i)-thgb(i))    

 1001  format(f8.5,2x,f12.7,2x,f12.10,2x,f12.10,2x,f13.10,2x,f12.8,f12.8,2x,i3)
    else                                                       
       flhc(i)=0.                                                  
    endif                                                      
  360 continue                                                          






  if(present(scm_force_flux)) then
    if(scm_force_flux) goto 405
    endif

    do 370 i = its,ite
       qfx(i)=flqc(i)*(qsfc(i)-qx(i))                         

       lh(i)=xlv*qfx(i)
    370 continue                                                      



    390 continue                                                      
    do 400 i = its,ite
       if(xland(i)-1.5.gt.0.)then                              
          hfx(i)=flhc(i)*(thgb(i)-thx(i)) 






       elseif(xland(i)-1.5.lt.0.)then                                
          hfx(i)=flhc(i)*(thgb(i)-thx(i))                     

       endif                                                     
    400 continue                                                      

    405 continue                                                      
          
    do i = its,ite
      if((xland(i)-1.5).ge.0)then
         zl=znt(i)
      else
         zl=0.01
      endif



      chs(i)=ust(i)*karman/denomq(i)








      cqs2(i)=ust(i)*karman/denomq2(i)
          chs2(i)=ust(i)*karman/denomt2(i)
    enddo

    410 continue                                                          











  errmsg = 'sf_sfclayrev_run OK'
  errflg = 0

  END SUBROUTINE sf_sfclayrev_run


  REAL(kind=kind_phys) FUNCTION zolri(ri,z,z0)
  REAL(kind=kind_phys),INTENT(IN):: ri,z,z0

  INTEGER:: iter
  REAL(kind=kind_phys):: fx1,fx2,x1,x2

  IF(ri.lt.0.)THEN
     x1=-5.
     x2=0.
  ELSE
     x1=0.
     x2=5.
  ENDIF

  fx1=zolri2(x1,ri,z,z0)
  fx2=zolri2(x2,ri,z,z0)
  iter = 0
  DO WHILE (abs(x1 - x2) > 0.01)
     IF (iter .eq. 10) RETURN

     IF(fx1.eq.fx2)RETURN
     IF(abs(fx2).lt.abs(fx1))THEN
        x1=x1-fx1/(fx2-fx1)*(x2-x1)
        fx1=zolri2(x1,ri,z,z0)
        zolri=x1
     ELSE
        x2=x2-fx2/(fx2-fx1)*(x2-x1)
        fx2=zolri2(x2,ri,z,z0)
        zolri=x2
     ENDIF
     iter = iter + 1
  ENDDO

  RETURN
  END FUNCTION zolri


  REAL(kind=kind_phys) FUNCTION zolri2(zol2,ri2,z,z0)
  REAL(kind=kind_phys),INTENT(IN):: ri2,z,z0
  REAL(kind=kind_phys),INTENT(INOUT):: zol2
  REAL(kind=kind_phys):: psih2,psix2,zol20,zol3

  IF(zol2*ri2 .lt. 0.)zol2=0.  

  zol20=zol2*z0/z 
  zol3=zol2+zol20 

  IF(ri2.lt.0) THEN
     psix2=log((z+z0)/z0)-(psim_unstable(zol3)-psim_unstable(zol20))
     psih2=log((z+z0)/z0)-(psih_unstable(zol3)-psih_unstable(zol20))
  ELSE
     psix2=log((z+z0)/z0)-(psim_stable(zol3)-psim_stable(zol20))
     psih2=log((z+z0)/z0)-(psih_stable(zol3)-psih_stable(zol20))
  ENDIF

  zolri2=zol2*psih2/psix2**2-ri2

  RETURN
  END FUNCTION zolri2





  REAL(kind=kind_phys) FUNCTION psim_stable_full(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  psim_stable_full=-6.1*log(zolf+(1+zolf**2.5)**(1./2.5))

  RETURN
  END FUNCTION psim_stable_full


  REAL(kind=kind_phys) FUNCTION psih_stable_full(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  psih_stable_full=-5.3*log(zolf+(1+zolf**1.1)**(1./1.1))

  RETURN
  END FUNCTION psih_stable_full


  REAL(kind=kind_phys) FUNCTION psim_unstable_full(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  REAL(kind=kind_phys):: psimc,psimk,x,y,ym
  x=(1.-16.*zolf)**.25
  psimk=2*ALOG(0.5*(1+X))+ALOG(0.5*(1+X*X))-2.*ATAN(X)+2.*ATAN(1.)

  ym=(1.-10.*zolf)**0.33
  psimc=(3./2.)*log((ym**2.+ym+1.)/3.)-sqrt(3.)*ATAN((2.*ym+1)/sqrt(3.))+4.*ATAN(1.)/sqrt(3.)

  psim_unstable_full=(psimk+zolf**2*(psimc))/(1+zolf**2.)

  RETURN
  END FUNCTION psim_unstable_full


  REAL(kind=kind_phys) FUNCTION psih_unstable_full(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  REAL(kind=kind_phys):: psihc,psihk,y,yh
  y=(1.-16.*zolf)**.5
  psihk=2.*log((1+y)/2.)

  yh=(1.-34.*zolf)**0.33
  psihc=(3./2.)*log((yh**2.+yh+1.)/3.)-sqrt(3.)*ATAN((2.*yh+1)/sqrt(3.))+4.*ATAN(1.)/sqrt(3.)

  psih_unstable_full=(psihk+zolf**2*(psihc))/(1+zolf**2.)

  RETURN
  END FUNCTION psih_unstable_full



  REAL(kind=kind_phys) FUNCTION psim_stable(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  INTEGER:: nzol
  REAL(kind=kind_phys):: rzol
  nzol = int(zolf*100.)
  rzol = zolf*100. - nzol
  IF(nzol+1 .lt. 1000)THEN
     psim_stable = psim_stab(nzol) + rzol*(psim_stab(nzol+1)-psim_stab(nzol))
  ELSE
     psim_stable = psim_stable_full(zolf)
  ENDIF

  RETURN
  END FUNCTION psim_stable


  REAL(kind=kind_phys) FUNCTION psih_stable(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  INTEGER:: nzol
  REAL(kind=kind_phys):: rzol
  nzol = int(zolf*100.)
  rzol = zolf*100. - nzol
  IF(nzol+1 .lt. 1000)THEN
     psih_stable = psih_stab(nzol) + rzol*(psih_stab(nzol+1)-psih_stab(nzol))
  ELSE
     psih_stable = psih_stable_full(zolf)
  ENDIF

  RETURN
  END FUNCTION psih_stable


  REAL(kind=kind_phys) FUNCTION psim_unstable(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  INTEGER:: nzol
  REAL(kind=kind_phys):: rzol
  nzol = int(-zolf*100.)
  rzol = -zolf*100. - nzol
  IF(nzol+1 .lt. 1000)THEN
     psim_unstable = psim_unstab(nzol) + rzol*(psim_unstab(nzol+1)-psim_unstab(nzol))
  ELSE
     psim_unstable = psim_unstable_full(zolf)
  ENDIF

  RETURN
  END FUNCTION psim_unstable


  REAL(kind=kind_phys) FUNCTION psih_unstable(zolf)
  REAL(kind=kind_phys),INTENT(IN):: zolf
  INTEGER:: nzol
  REAL(kind=kind_phys):: rzol
  nzol = int(-zolf*100.)
  rzol = -zolf*100. - nzol
  IF(nzol+1 .lt. 1000)THEN
     psih_unstable = psih_unstab(nzol) + rzol*(psih_unstab(nzol+1)-psih_unstab(nzol))
  ELSE
     psih_unstable = psih_unstable_full(zolf)
  ENDIF

  RETURN
  END FUNCTION psih_unstable


  REAL(kind=kind_phys) FUNCTION depth_dependent_z0(water_depth,z0,ust)
  REAL(kind=kind_phys),INTENT(IN):: water_depth,z0,ust
  REAL(kind=kind_phys):: depth_b
  REAL(kind=kind_phys):: effective_depth
  IF(water_depth .lt. 10.0) THEN
     effective_depth = 10.0
  ELSEIF(water_depth .gt. 100.0) THEN
     effective_depth = 100.0
  ELSE
     effective_depth = water_depth
  ENDIF
  
  depth_b = 1 / 30.0 * log (1260.0 / effective_depth)
  depth_dependent_z0 = exp((2.7 * ust - 1.8 / depth_b) / (ust + 0.17 / depth_b) )
  depth_dependent_z0 = MIN(depth_dependent_z0,0.1)

  RETURN
  END FUNCTION depth_dependent_z0


END MODULE sf_sfclayrev

























