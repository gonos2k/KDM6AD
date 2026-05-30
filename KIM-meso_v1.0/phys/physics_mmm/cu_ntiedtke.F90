
 module cu_ntiedtke_common
 use ccpp_kind_types,only: kind_phys


 implicit none
 save

 real(kind=kind_phys):: alf
 real(kind=kind_phys):: als
 real(kind=kind_phys):: alv
 real(kind=kind_phys):: cpd
 real(kind=kind_phys):: g
 real(kind=kind_phys):: rd
 real(kind=kind_phys):: rv

 real(kind=kind_phys),parameter:: t13   = 1.0/3.0
 real(kind=kind_phys),parameter:: tmelt = 273.16
 real(kind=kind_phys),parameter:: c1es  = 610.78
 real(kind=kind_phys),parameter:: c3les = 17.2693882
 real(kind=kind_phys),parameter:: c3ies = 21.875
 real(kind=kind_phys),parameter:: c4les = 35.86
 real(kind=kind_phys),parameter:: c4ies = 7.66

 real(kind=kind_phys),parameter:: rtwat = tmelt
 real(kind=kind_phys),parameter:: rtber = tmelt-5.
 real(kind=kind_phys),parameter:: rtice = tmelt-23.

 integer,parameter:: momtrans = 2
 real(kind=kind_phys),parameter:: entrdd  = 2.0e-4
 real(kind=kind_phys),parameter:: cmfcmax = 1.0
 real(kind=kind_phys),parameter:: cmfcmin = 1.e-10
 real(kind=kind_phys),parameter:: cmfdeps = 0.30
 real(kind=kind_phys),parameter:: zdnoprc = 2.0e4
 real(kind=kind_phys),parameter:: cprcon  = 1.4e-3
 real(kind=kind_phys),parameter:: pgcoef  = 0.7

 real(kind=kind_phys):: rcpd
 real(kind=kind_phys):: c2es
 real(kind=kind_phys):: c5les
 real(kind=kind_phys):: c5ies
 real(kind=kind_phys):: r5alvcp
 real(kind=kind_phys):: r5alscp
 real(kind=kind_phys):: ralvdcp
 real(kind=kind_phys):: ralsdcp
 real(kind=kind_phys):: ralfdcp
 real(kind=kind_phys):: vtmpc1
 real(kind=kind_phys):: zrg

 logical,parameter:: nonequil = .true.
 logical,parameter:: lmfpen   = .true.
 logical,parameter:: lmfmid   = .true.
 logical,parameter:: lmfscv   = .true.
 logical,parameter:: lmfdd    = .true.
 logical,parameter:: lmfdudv  = .true.



 end module cu_ntiedtke_common


 module cu_ntiedtke
 use ccpp_kind_types,only: kind_phys
 use cu_ntiedtke_common


 implicit none
 private
 public:: cu_ntiedtke_run,     &
          cu_ntiedtke_init,    &
          cu_ntiedtke_finalize


 contains






 subroutine cu_ntiedtke_init(con_cp,con_rd,con_rv,con_xlv,con_xls,con_xlf,con_grav,errmsg,errflg)



 real(kind=kind_phys),intent(in):: &
    con_cp,  &
    con_rd,  &
    con_rv,  &
    con_xlv, &
    con_xls, &
    con_xlf, &
    con_grav


 character(len=*),intent(out):: errmsg
 integer,intent(out):: errflg



 alf = con_xlf
 als = con_xls
 alv = con_xlv
 cpd = con_cp
 g   = con_grav
 rd  = con_rd
 rv  = con_rv

 rcpd    = 1.0/con_cp
 c2es    = c1es*con_rd/con_rv
 c5les   = c3les*(tmelt-c4les)
 c5ies   = c3ies*(tmelt-c4ies)
 r5alvcp = c5les*con_xlv*rcpd
 r5alscp = c5ies*con_xls*rcpd
 ralvdcp = con_xlv*rcpd
 ralsdcp = con_xls*rcpd
 ralfdcp = con_xlf*rcpd
 vtmpc1  = con_rv/con_rd-1.0
 zrg     = 1.0/con_grav

 errmsg = 'cu_ntiedtke_init OK'
 errflg = 0

 end subroutine cu_ntiedtke_init





 subroutine cu_ntiedtke_finalize(errmsg,errflg)



 character(len=*),intent(out):: errmsg
 integer,intent(out):: errflg



 errmsg = 'cu_ntiedtke_finalize OK'
 errflg = 0

 end subroutine cu_ntiedtke_finalize






      subroutine cu_ntiedtke_run(pu,pv,pt,pqv,pqc,pqi,pqvf,ptf,poz,pzz,pomg, &
     &         pap,paph,evap,hfx,zprecc,lndj,lq,km,km1,dt,dx,errmsg,errflg)







































      integer,intent(in):: lq,km,km1
      integer,intent(in),dimension(:):: lndj

      real(kind=kind_phys),intent(in):: dt
      real(kind=kind_phys),intent(in),dimension(:):: dx
      real(kind=kind_phys),intent(in),dimension(:):: evap,hfx
      real(kind=kind_phys),intent(in),dimension(:,:):: pqvf,ptf
      real(kind=kind_phys),intent(in),dimension(:,:):: poz,pomg,pap
      real(kind=kind_phys),intent(in),dimension(:,:):: pzz,paph


      real(kind=kind_phys),intent(inout),dimension(:):: zprecc
      real(kind=kind_phys),intent(inout),dimension(:,:):: pu,pv,pt,pqv,pqc,pqi


      character(len=*),intent(out):: errmsg
      integer,intent(out):: errflg


      logical,dimension(lq):: locum
      integer:: i,j,k
      integer,dimension(lq):: icbot,ictop,ktype

      real(kind=kind_phys):: ztmst,fliq,fice,ztc,zalf,tt
      real(kind=kind_phys):: ztpp1,zew,zqs,zcor
      real(kind=kind_phys):: dxref

      real(kind=kind_phys),dimension(lq):: pqhfl,prsfc,pssfc,phhfl,zrain
      real(kind=kind_phys),dimension(lq):: scale_fac,scale_fac2

      real(kind=kind_phys),dimension(lq,km):: pum1,pvm1,ztt,ptte,pqte,pvom,pvol,pverv,pgeo
      real(kind=kind_phys),dimension(lq,km):: zqq,pcte
      real(kind=kind_phys),dimension(lq,km):: ztp1,zqp1,ztu,zqu,zlu,zlude,zmfu,zmfd,zqsat
      real(kind=kind_phys),dimension(lq,km1):: pgeoh



      ztmst=dt



      dxref = 15000.
      do j=1,lq
      if (dx(j).lt.dxref) then
          scale_fac(j) = (1.06133+log(dxref/dx(j)))**3
          scale_fac2(j) = scale_fac(j)**0.5
      else
          scale_fac(j) = 1.+1.33e-5*dx(j)
          scale_fac2(j) = 1.
      end if
      end do



      do j=1,lq
        zrain(j)=0.0
        locum(j)=.false.
        prsfc(j)=0.0
        pssfc(j)=0.0
        pqhfl(j)=evap(j)
        phhfl(j)=hfx(j)
        pgeoh(j,km1)=g*pzz(j,km1)
      end do



      do k=1,km
        do j=1,lq
          pcte(j,k)=0.0
          pvom(j,k)=0.0
          pvol(j,k)=0.0
          ztp1(j,k)=pt(j,k)
          zqp1(j,k)=pqv(j,k)/(1.0+pqv(j,k))
          pum1(j,k)=pu(j,k)
          pvm1(j,k)=pv(j,k)
          pverv(j,k)=pomg(j,k)
          pgeo(j,k)=g*poz(j,k)
          pgeoh(j,k)=g*pzz(j,k)
          tt=ztp1(j,k)
          zew  = foeewm(tt)
          zqs  = zew/pap(j,k)
          zqs  = min(0.5,zqs)
          zcor = 1./(1.-vtmpc1*zqs)
          zqsat(j,k)=zqs*zcor
          pqte(j,k)=pqvf(j,k)
          zqq(j,k) =pqte(j,k)
          ptte(j,k)=ptf(j,k)
          ztt(j,k) =ptte(j,k)
        end do
      end do




      call cumastrn        &
     &    (lq,       km,       km1,      km-1,    ztp1,  &
     &     zqp1,     pum1,     pvm1,     pverv,   zqsat, &
     &     pqhfl,    ztmst,    pap,      paph,    pgeo,  &
     &     ptte,     pqte,     pvom,     pvol,    prsfc, &
     &     pssfc,    locum,                              &
     &     ktype,    icbot,    ictop,    ztu,     zqu,   &
     &     zlu,      zlude,    zmfu,     zmfd,    zrain, &
     &     pcte,     phhfl,    lndj,     pgeoh,   dx,    &
     &     scale_fac, scale_fac2)



      do k=1,km
      do j=1,lq
      if(pcte(j,k).gt.0.) then
        fliq=foealfa(ztp1(j,k))
        fice=1.0-fliq
        pqc(j,k)=pqc(j,k)+fliq*pcte(j,k)*ztmst
        pqi(j,k)=pqi(j,k)+fice*pcte(j,k)*ztmst
      endif
      end do
      end do

      do k=1,km
        do j=1,lq
          pt(j,k)=  ztp1(j,k)+(ptte(j,k)-ztt(j,k))*ztmst
          zqp1(j,k)=zqp1(j,k)+(pqte(j,k)-zqq(j,k))*ztmst
          pqv(j,k)=zqp1(j,k)/(1.0-zqp1(j,k))
        end do
      end do

      do j=1,lq
        zprecc(j)=amax1(0.0,(prsfc(j)+pssfc(j))*ztmst)
      end do

      if (lmfdudv) then
        do k=1,km
          do j=1,lq
            pu(j,k)=pu(j,k)+pvom(j,k)*ztmst
            pv(j,k)=pv(j,k)+pvol(j,k)*ztmst
          end do
        end do
      endif

      errmsg = 'cu_ntiedtke_run OK'
      errflg = 0

      return
      end subroutine cu_ntiedtke_run









      subroutine cumastrn  &
     &    (klon,     klev,     klevp1,   klevm1,   pten,  &
     &     pqen,     puen,     pven,     pverv,    pqsen, &
     &     pqhfl,    ztmst,    pap,      paph,     pgeo,  &
     &     ptte,     pqte,     pvom,     pvol,     prsfc, &
     &     pssfc,    ldcum,                               &
     &     ktype,    kcbot,    kctop,    ptu,      pqu,   &
     &     plu,      plude,    pmfu,     pmfd,     prain, &
     &     pcte,     phhfl,    lndj,     zgeoh,    dx,    &
     &     scale_fac,  scale_fac2)
      implicit none




























































      integer,intent(in):: klev,klon,klevp1,klevm1
      integer,intent(in),dimension(klon):: lndj

      real(kind=kind_phys),intent(in):: ztmst
      real(kind=kind_phys),intent(in),dimension(klon):: dx
      real(kind=kind_phys),intent(in),dimension(klon):: pqhfl,phhfl
      real(kind=kind_phys),intent(in),dimension(klon):: scale_fac,scale_fac2
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pten,pqen,puen,pven,pverv
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pap,pgeo
      real(kind=kind_phys),intent(in),dimension(klon,klevp1):: paph,zgeoh


      integer,intent(inout),dimension(klon):: ktype,kcbot,kctop
      logical,intent(inout),dimension(klon):: ldcum

      real(kind=kind_phys),intent(inout),dimension(klon):: pqsen
      real(kind=kind_phys),intent(inout),dimension(klon):: prsfc,pssfc,prain
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pcte,ptte,pqte,pvom,pvol
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: ptu,pqu,plu,plude,pmfu,pmfd


      logical:: llo1
      logical,dimension(klon):: loddraf,llo2

      integer:: jl,jk,ik
      integer:: ikb,ikt,icum,itopm2
      integer,dimension(klon):: kdpl,idtop,ictop0,ilwmin
      integer,dimension(klon,klev):: ilab

      real(kind=kind_phys):: zcons,zcons2,zqumqe,zdqmin,zdh,zmfmax
      real(kind=kind_phys):: zalfaw,zalv,zqalv,zc5ldcp,zc4les,zhsat,zgam,zzz,zhhat
      real(kind=kind_phys):: zpbmpt,zro,zdz,zdp,zeps,zfac,wspeed
      real(kind=kind_phys):: zduten,zdvten,ztdis,pgf_u,pgf_v
      real(kind=kind_phys):: zlon
      real(kind=kind_phys):: ztau,zerate,zderate,zmfa
      real(kind=kind_phys),dimension(klon):: zmfs
      real(kind=kind_phys),dimension(klon):: zsfl,zcape,zcape1,zcape2,ztauc,ztaubl,zheat
      real(kind=kind_phys),dimension(klon):: wup,zdqcv
      real(kind=kind_phys),dimension(klon):: wbase,zmfuub
      real(kind=kind_phys),dimension(klon):: upbl
      real(kind=kind_phys),dimension(klon):: zhcbase,zmfub,zmfub1,zdhpbl
      real(kind=kind_phys),dimension(klon):: zmfuvb,zsum12,zsum22
      real(kind=kind_phys),dimension(klon):: zrfl
      real(kind=kind_phys),dimension(klev):: pmean
      real(kind=kind_phys),dimension(klon,klev):: pmfude_rate,pmfdde_rate
      real(kind=kind_phys),dimension(klon,klev):: zdpmel
      real(kind=kind_phys),dimension(klon,klev):: zmfuus,zmfdus,zuv2,ztenu,ztenv
      real(kind=kind_phys),dimension(klon,klev):: ztenh,zqenh,zqsenh,ztd,zqd
      real(kind=kind_phys),dimension(klon,klev):: zmfus,zmfds,zmfuq,zmfdq,zdmfup,zdmfdp,zmful
      real(kind=kind_phys),dimension(klon,klev):: zuu,zvu,zud,zvd,zlglac
      real(kind=kind_phys),dimension(klon,klevp1):: pmflxr,pmflxs




      zcons=1./(g*ztmst)
      zcons2=3./(g*ztmst)




      call cuinin &
     &    (klon,     klev,     klevp1,   klevm1,   pten,  &
     &     pqen,     pqsen,    puen,     pven,     pverv, &
     &     pgeo,     paph,     zgeoh,    ztenh,    zqenh, &
     &     zqsenh,   ilwmin,   ptu,      pqu,      ztd,   &
     &     zqd,      zuu,      zvu,      zud,      zvd,   &
     &     pmfu,     pmfd,     zmfus,    zmfds,    zmfuq, &
     &     zmfdq,    zdmfup,   zdmfdp,   zdpmel,   plu,   &
     &     plude,    ilab)







       call cutypen &
     &     ( klon,     klev,     klevp1,   klevm1,     pqen, &
     &      ztenh,    zqenh,     zqsenh,    zgeoh,     paph, &
     &      phhfl,    pqhfl,       pgeo,    pqsen,      pap, &
     &       pten,     lndj,        ptu,      pqu,     ilab, &
     &      ldcum,    kcbot,     ictop0,    ktype,    wbase, &
     &        plu,    kdpl)



       do jl=1,klon
         zdhpbl(jl)=0.0
         upbl(jl) = 0.0
         idtop(jl)=0
       end do

       do jk=2,klev
       do jl=1,klon
         if(jk.ge.kcbot(jl) .and. ldcum(jl)) then
            zdhpbl(jl)=zdhpbl(jl)+(alv*pqte(jl,jk)+cpd*ptte(jl,jk))&
     &                 *(paph(jl,jk+1)-paph(jl,jk))
            if(lndj(jl) .eq. 0) then
              wspeed = sqrt(puen(jl,jk)**2 + pven(jl,jk)**2)
              upbl(jl) = upbl(jl) + wspeed*(paph(jl,jk+1)-paph(jl,jk))
            end if
         end if
       end do
       end do

      do jl=1,klon
        if(ldcum(jl)) then
           ikb=kcbot(jl)
           zmfmax = (paph(jl,ikb)-paph(jl,ikb-1))*zcons2
           if(ktype(jl) == 1) then
             zmfub(jl)= 0.1*zmfmax
           else if ( ktype(jl) == 2 ) then
             zqumqe = pqu(jl,ikb) + plu(jl,ikb) - zqenh(jl,ikb)
             zdqmin = max(0.01*zqenh(jl,ikb),1.e-10)
             zdh = cpd*(ptu(jl,ikb)-ztenh(jl,ikb)) + alv*zqumqe
             zdh = g*max(zdh,1.e5*zdqmin)
             if ( zdhpbl(jl) > 0. ) then
               zmfub(jl) = zdhpbl(jl)/zdh
               zmfub(jl) = min(zmfub(jl),zmfmax)
             else
               zmfub(jl) = 0.1*zmfmax
               ldcum(jl) = .false.
             end if
            end if
        else
           zmfub(jl) = 0.
        end if
      end do





      call cuascn &
     &    (klon,     klev,     klevp1,   klevm1,   ztenh,   &
     &     zqenh,    puen,     pven,     pten,     pqen,    &
     &     pqsen,    pgeo,     zgeoh,    pap,      paph,    &
     &     pqte,     pverv,    ilwmin,   ldcum,    zhcbase, &
     &     ktype,    ilab,     ptu,      pqu,      plu,     &
     &     zuu,      zvu,      pmfu,     zmfub,             &
     &     zmfus,    zmfuq,    zmful,    plude,    zdmfup,  &
     &     kcbot,    kctop,    ictop0,   icum,     ztmst,   &
     &     zqsenh,   zlglac,   lndj,     wup,      wbase,   &
     &     kdpl,     pmfude_rate)




      do jl=1,klon
        if ( ldcum(jl) ) then
          ikb = kcbot(jl)
          itopm2 = kctop(jl)
          zpbmpt = paph(jl,ikb) - paph(jl,itopm2)
          if ( ktype(jl) == 1 .and. zpbmpt <  zdnoprc ) ktype(jl) = 2
          if ( ktype(jl) == 2 .and. zpbmpt >= zdnoprc ) ktype(jl) = 1
          ictop0(jl) = kctop(jl)
        end if
        zrfl(jl)=zdmfup(jl,1)
      end do

      do jk=2,klev
        do jl=1,klon
          zrfl(jl)=zrfl(jl)+zdmfup(jl,jk)
        end do
      end do

      do jk = 1,klev
      do jl = 1,klon
        pmfd(jl,jk) = 0.
        zmfds(jl,jk) = 0.
        zmfdq(jl,jk) = 0.
        zdmfdp(jl,jk) = 0.
        zdpmel(jl,jk) = 0.
      end do
      end do




      if(lmfdd) then


        call cudlfsn &
     &    (klon,     klev,&
     &     kcbot,    kctop,    lndj,   ldcum,  &
     &     ztenh,    zqenh,    puen,   pven,   &
     &     pten,     pqsen,    pgeo,           &
     &     zgeoh,    paph,     ptu,    pqu,   plu, &
     &     zuu,      zvu,      zmfub,  zrfl,   &
     &     ztd,      zqd,      zud,    zvd,    &
     &     pmfd,     zmfds,    zmfdq,  zdmfdp, &
     &     idtop,    loddraf)


        call cuddrafn &
     &    (klon,     klev,     loddraf,                  &
     &     ztenh,    zqenh,    puen,     pven,           &
     &     pgeo,     zgeoh,    paph,     zrfl,           &
     &     ztd,      zqd,      zud,      zvd,      pmfu, &
     &     pmfd,     zmfds,    zmfdq,    zdmfdp,   pmfdde_rate)

      end if







      do jl=1,klon
      if(ldcum(jl) .and. ktype(jl) .eq. 1) then
        ikb = kcbot(jl)
        ikt = kctop(jl)
        zheat(jl)=0.0
        zcape(jl)=0.0
        zcape1(jl)=0.0
        zcape2(jl)=0.0
        zmfub1(jl)=zmfub(jl)

        ztauc(jl)  = (zgeoh(jl,ikt)-zgeoh(jl,ikb)) / &
                   ((2.+ min(15.0,wup(jl)))*g)
        if(lndj(jl) .eq. 0) then
          upbl(jl) = 2.+ upbl(jl)/(paph(jl,klev+1)-paph(jl,ikb))
          ztaubl(jl) = (zgeoh(jl,ikb)-zgeoh(jl,klev+1))/(g*upbl(jl))
          ztaubl(jl) = min(300., ztaubl(jl))
        else
          ztaubl(jl) = ztauc(jl)
        end if
      end if
      end do

      do jk = 1 , klev
      do jl = 1 , klon
        llo1 = ldcum(jl) .and. ktype(jl) .eq. 1
        if ( llo1 .and. jk <= kcbot(jl) .and. jk > kctop(jl) ) then
          ikb = kcbot(jl)
          zdz = pgeo(jl,jk-1)-pgeo(jl,jk)
          zdp = pap(jl,jk)-pap(jl,jk-1)
          zheat(jl) = zheat(jl) + ((pten(jl,jk-1)-pten(jl,jk)+zdz*rcpd) / &
                      ztenh(jl,jk)+vtmpc1*(pqen(jl,jk-1)-pqen(jl,jk))) * &
                      (g*(pmfu(jl,jk)+pmfd(jl,jk)))
          zcape1(jl) = zcape1(jl) + ((ptu(jl,jk)-ztenh(jl,jk))/ztenh(jl,jk) + &
                      vtmpc1*(pqu(jl,jk)-zqenh(jl,jk))-plu(jl,jk))*zdp
        end if

        if ( llo1 .and. jk >= kcbot(jl) ) then
        if((paph(jl,klev+1)-paph(jl,kdpl(jl)))<50.e2) then
          zdp = paph(jl,jk+1)-paph(jl,jk)
          zcape2(jl) = zcape2(jl) + ztaubl(jl)* &
                     ((1.+vtmpc1*pqen(jl,jk))*ptte(jl,jk)+vtmpc1*pten(jl,jk)*pqte(jl,jk))*zdp
        end if
        end if
      end do
      end do

      do jl=1,klon
       if(ldcum(jl).and.ktype(jl).eq.1) then
           ikb = kcbot(jl)
           ikt = kctop(jl)
           ztauc(jl) = max(ztmst,ztauc(jl))
           ztauc(jl) = max(360.,ztauc(jl))
           ztauc(jl) = min(10800.,ztauc(jl))
           ztau = ztauc(jl) * scale_fac(jl)
           if(nonequil) then
             zcape2(jl)= max(0.,zcape2(jl))
             zcape(jl) = max(0.,min(zcape1(jl)-zcape2(jl),5000.))
           else
             zcape(jl) = max(0.,min(zcape1(jl),5000.))
           end if
           zheat(jl) = max(1.e-4,zheat(jl))
           zmfub1(jl) = (zcape(jl)*zmfub(jl))/(zheat(jl)*ztau)
           zmfub1(jl) = max(zmfub1(jl),0.001)
           zmfmax=(paph(jl,ikb)-paph(jl,ikb-1))*zcons2
           zmfub1(jl)=min(zmfub1(jl),zmfmax)
       end if
      end do




       do jl=1,klon
         if(ldcum(jl) .and. ktype(jl) .eq. 2) then
           ikb=kcbot(jl)
           if(pmfd(jl,ikb).lt.0.0 .and. loddraf(jl)) then
              zeps=-pmfd(jl,ikb)/max(zmfub(jl),cmfcmin)
           else
              zeps=0.
           endif
           zqumqe=pqu(jl,ikb)+plu(jl,ikb)-  &
     &            zeps*zqd(jl,ikb)-(1.-zeps)*zqenh(jl,ikb)
           zdqmin=max(0.01*zqenh(jl,ikb),cmfcmin)
           zmfmax=(paph(jl,ikb)-paph(jl,ikb-1))*zcons2

           zdh=cpd*(ptu(jl,ikb)-zeps*ztd(jl,ikb)- &
     &       (1.-zeps)*ztenh(jl,ikb))+alv*zqumqe
           zdh=g*max(zdh,1.e5*zdqmin)
           if(zdhpbl(jl).gt.0.)then
             zmfub1(jl)=zdhpbl(jl)/zdh
           else
             zmfub1(jl) = zmfub(jl)
           end if
           zmfub1(jl) = zmfub1(jl)/scale_fac2(jl)
           zmfub1(jl) = min(zmfub1(jl),zmfmax)
         end if



         if(ldcum(jl) .and. ktype(jl) .eq. 3 ) then
            zmfub1(jl) = zmfub(jl)
         end if

       end do



       do jk=1,klev
       do jl=1,klon
        if( ldcum(jl) ) then
           zfac=zmfub1(jl)/max(zmfub(jl),cmfcmin)
           pmfd(jl,jk)=pmfd(jl,jk)*zfac
           zmfds(jl,jk)=zmfds(jl,jk)*zfac
           zmfdq(jl,jk)=zmfdq(jl,jk)*zfac
           zdmfdp(jl,jk)=zdmfdp(jl,jk)*zfac
           pmfdde_rate(jl,jk) = pmfdde_rate(jl,jk)*zfac
        end if
       end do
       end do



    do jl = 1,klon
      if ( ldcum(jl) ) zmfs(jl) = zmfub1(jl)/max(cmfcmin,zmfub(jl))
    end do
    do jk = 2 , klev
      do jl = 1,klon
        if ( ldcum(jl) .and. jk >= kctop(jl)-1 ) then
          ikb = kcbot(jl)
          if ( jk>ikb ) then
            zdz = ((paph(jl,klev+1)-paph(jl,jk))/(paph(jl,klev+1)-paph(jl,ikb)))
            pmfu(jl,jk) = pmfu(jl,ikb)*zdz
          end if
          zmfmax = (paph(jl,jk)-paph(jl,jk-1))*zcons2
          if ( pmfu(jl,jk)*zmfs(jl) > zmfmax ) then
            zmfs(jl) = min(zmfs(jl),zmfmax/pmfu(jl,jk))
          end if
        end if
      end do
    end do
    do jk = 2 , klev
      do jl = 1,klon
        if ( ldcum(jl) .and. jk <= kcbot(jl) .and. jk >= kctop(jl)-1 ) then
          pmfu(jl,jk) = pmfu(jl,jk)*zmfs(jl)
          zmfus(jl,jk) = zmfus(jl,jk)*zmfs(jl)
          zmfuq(jl,jk) = zmfuq(jl,jk)*zmfs(jl)
          zmful(jl,jk) = zmful(jl,jk)*zmfs(jl)
          zdmfup(jl,jk) = zdmfup(jl,jk)*zmfs(jl)
          plude(jl,jk) = plude(jl,jk)*zmfs(jl)
          pmfude_rate(jl,jk) = pmfude_rate(jl,jk)*zmfs(jl)
        end if
      end do
    end do



    do jl = 1,klon
      if ( ktype(jl) == 2 .and. &
           kcbot(jl) == kctop(jl) .and. kcbot(jl) >= klev-1 ) then
        ldcum(jl) = .false.
        ktype(jl) = 0
      end if
    end do

    if ( .not. lmfscv .or. .not. lmfpen ) then
      do jl = 1,klon
        llo2(jl) = .false.
        if ( (.not. lmfscv .and. ktype(jl) == 2) .or. &
             (.not. lmfpen .and. ktype(jl) == 1) ) then
          llo2(jl) = .true.
          ldcum(jl) = .false.
        end if
      end do
    end if



    do jl = 1,klon
      if ( loddraf(jl) .and. idtop(jl) <= kctop(jl) ) then
        idtop(jl) = kctop(jl) + 1
      end if
    end do
    do jk = 2 , klev
      do jl = 1,klon
        if ( loddraf(jl) ) then
          if ( jk < idtop(jl) ) then
            pmfd(jl,jk) = 0.
            zmfds(jl,jk) = 0.
            zmfdq(jl,jk) = 0.
            pmfdde_rate(jl,jk) = 0.
            zdmfdp(jl,jk) = 0.
          else if ( jk == idtop(jl) ) then
            pmfdde_rate(jl,jk) = 0.
          end if
        end if
      end do
    end do



       call cuflxn                                      &
     &  (  klon,     klev,     ztmst                    &
     &  ,  pten,     pqen,     pqsen,    ztenh,   zqenh &
     &  ,  paph,     pap,      zgeoh,    lndj,    ldcum &
     &  ,  kcbot,    kctop,    idtop,    itopm2         &
     &  ,  ktype,    loddraf                            &
     &  ,  pmfu,     pmfd,     zmfus,    zmfds          &
     &  ,  zmfuq,    zmfdq,    zmful,    plude          &
     &  ,  zdmfup,   zdmfdp,   zdpmel,   zlglac         &
     &  ,  prain,    pmfdde_rate, pmflxr, pmflxs )


    do jl=1,klon
      zmfs(jl) = 1.
      zmfuub(jl)=0.
    end do
    do jk = 2 , klev
      do jl = 1,klon
        if ( loddraf(jl) .and. jk >= idtop(jl)-1 ) then
          zmfmax = pmfu(jl,jk)*0.98
          if ( pmfd(jl,jk)+zmfmax+1.e-15 < 0. ) then
            zmfs(jl) = min(zmfs(jl),-zmfmax/pmfd(jl,jk))
          end if
        end if
      end do
    end do

    do jk = 2 , klev
      do jl = 1 , klon
        if ( zmfs(jl) < 1. .and. jk >= idtop(jl)-1 ) then
          pmfd(jl,jk) = pmfd(jl,jk)*zmfs(jl)
          zmfds(jl,jk) = zmfds(jl,jk)*zmfs(jl)
          zmfdq(jl,jk) = zmfdq(jl,jk)*zmfs(jl)
          pmfdde_rate(jl,jk) = pmfdde_rate(jl,jk)*zmfs(jl)
          zmfuub(jl) = zmfuub(jl) - (1.-zmfs(jl))*zdmfdp(jl,jk)
          pmflxr(jl,jk+1) = pmflxr(jl,jk+1) + zmfuub(jl)
          zdmfdp(jl,jk) = zdmfdp(jl,jk)*zmfs(jl)
        end if
      end do
    end do

    do jk = 2 , klev - 1
      do jl = 1, klon
        if ( loddraf(jl) .and. jk >= idtop(jl)-1 ) then
          zerate = -pmfd(jl,jk) + pmfd(jl,jk-1) + pmfdde_rate(jl,jk)
          if ( zerate < 0. ) then
            pmfdde_rate(jl,jk) = pmfdde_rate(jl,jk) - zerate
          end if
        end if
        if ( ldcum(jl) .and. jk >= kctop(jl)-1 ) then
          zerate = pmfu(jl,jk) - pmfu(jl,jk+1) + pmfude_rate(jl,jk)
          if ( zerate < 0. ) then
            pmfude_rate(jl,jk) = pmfude_rate(jl,jk) - zerate
          end if
          zdmfup(jl,jk) = pmflxr(jl,jk+1) + pmflxs(jl,jk+1) - &
                          pmflxr(jl,jk) - pmflxs(jl,jk)
          zdmfdp(jl,jk) = 0.
        end if
      end do
    end do


    do jl = 1,klon
      if ( loddraf(jl) ) then
        jk = idtop(jl)
        ik = min(jk+1,klev)
        if ( zmfdq(jl,jk) < 0.3*zmfdq(jl,ik) ) then
            zmfdq(jl,jk) = 0.3*zmfdq(jl,ik)
        end if
      end if
    end do



    do jk = 2 , klev
      do jl = 1, klon
        if ( ldcum(jl) .and. jk >= kctop(jl)-1 .and. jk < kcbot(jl) ) then
          zdz = ztmst*g/(paph(jl,jk+1)-paph(jl,jk))
          zmfa = zmfuq(jl,jk+1) + zmfdq(jl,jk+1) - &
                 zmfuq(jl,jk) - zmfdq(jl,jk) + &
                 zmful(jl,jk+1) - zmful(jl,jk) + zdmfup(jl,jk)
          zmfa = (zmfa-plude(jl,jk))*zdz
          if ( pqen(jl,jk)+zmfa < 0. ) then
            plude(jl,jk) = plude(jl,jk) + 2.*(pqen(jl,jk)+zmfa)/zdz
          end if
          if ( plude(jl,jk) < 0. ) plude(jl,jk) = 0.
        end if
        if ( .not. ldcum(jl) ) pmfude_rate(jl,jk) = 0.
        if ( abs(pmfd(jl,jk-1)) < 1.0e-20 ) pmfdde_rate(jl,jk) = 0.
      end do
    end do

    do jl=1,klon
      prsfc(jl) = pmflxr(jl,klev+1)
      pssfc(jl) = pmflxs(jl,klev+1)
    end do




      call cudtdqn(klon,klev,itopm2,kctop,idtop,ldcum,loddraf,         &
                 ztmst,paph,zgeoh,pgeo,pten,ztenh,pqen,zqenh,pqsen,    &
                 zlglac,plude,pmfu,pmfd,zmfus,zmfds,zmfuq,zmfdq,zmful, &
                 zdmfup,zdmfdp,zdpmel,ptte,pqte,pcte)



      if(lmfdudv) then
      do jk = klev-1 , 2 , -1
        ik = jk + 1
        do jl = 1,klon
          if ( ldcum(jl) ) then
            if ( jk == kcbot(jl) .and. ktype(jl) < 3 ) then
              ikb = kdpl(jl)
              zuu(jl,jk) = puen(jl,ikb-1)
              zvu(jl,jk) = pven(jl,ikb-1)
            else if ( jk == kcbot(jl) .and. ktype(jl) == 3 ) then
              zuu(jl,jk) = puen(jl,jk-1)
              zvu(jl,jk) = pven(jl,jk-1)
            end if
            if ( jk < kcbot(jl) .and. jk >= kctop(jl) ) then
            if(momtrans .eq. 1)then
              zfac = 0.
              if ( ktype(jl) == 1 .or. ktype(jl) == 3 ) zfac = 2.
              if ( ktype(jl) == 1 .and. jk <= kctop(jl)+2 ) zfac = 3.
              zerate = pmfu(jl,jk) - pmfu(jl,ik) + &
                (1.+zfac)*pmfude_rate(jl,jk)
              zderate = (1.+zfac)*pmfude_rate(jl,jk)
              zmfa = 1./max(cmfcmin,pmfu(jl,jk))
              zuu(jl,jk) = (zuu(jl,ik)*pmfu(jl,ik) + &
                zerate*puen(jl,jk)-zderate*zuu(jl,ik))*zmfa
              zvu(jl,jk) = (zvu(jl,ik)*pmfu(jl,ik) + &
                zerate*pven(jl,jk)-zderate*zvu(jl,ik))*zmfa
            else
              pgf_u = -pgcoef*0.5*(pmfu(jl,ik)*(puen(jl,ik)-puen(jl,jk))+&
                                   pmfu(jl,jk)*(puen(jl,jk)-puen(jl,jk-1)))
              pgf_v = -pgcoef*0.5*(pmfu(jl,ik)*(pven(jl,ik)-pven(jl,jk))+&
                                   pmfu(jl,jk)*(pven(jl,jk)-pven(jl,jk-1)))
              zerate = pmfu(jl,jk) - pmfu(jl,ik) + pmfude_rate(jl,jk)
              zderate = pmfude_rate(jl,jk)
              zmfa = 1./max(cmfcmin,pmfu(jl,jk))
              zuu(jl,jk) = (zuu(jl,ik)*pmfu(jl,ik) + &
                zerate*puen(jl,jk)-zderate*zuu(jl,ik)+pgf_u)*zmfa
              zvu(jl,jk) = (zvu(jl,ik)*pmfu(jl,ik) + &
                zerate*pven(jl,jk)-zderate*zvu(jl,ik)+pgf_v)*zmfa
            end if
            end if
          end if
        end do
      end do

      if(lmfdd) then
      do jk = 3 , klev
        ik = jk - 1
        do jl = 1,klon
          if ( ldcum(jl) ) then
            if ( jk == idtop(jl) ) then
              zud(jl,jk) = 0.5*(zuu(jl,jk)+puen(jl,ik))
              zvd(jl,jk) = 0.5*(zvu(jl,jk)+pven(jl,ik))
            else if ( jk > idtop(jl) ) then
              zerate = -pmfd(jl,jk) + pmfd(jl,ik) + pmfdde_rate(jl,jk)
              zmfa = 1./min(-cmfcmin,pmfd(jl,jk))
              zud(jl,jk) = (zud(jl,ik)*pmfd(jl,ik) - &
                zerate*puen(jl,ik)+pmfdde_rate(jl,jk)*zud(jl,ik))*zmfa
              zvd(jl,jk) = (zvd(jl,ik)*pmfd(jl,ik) - &
                zerate*pven(jl,ik)+pmfdde_rate(jl,jk)*zvd(jl,ik))*zmfa
            end if
          end if
        end do
      end do
      end if



      zmfs(:) = 1.
      do jk = 2 , klev
        do jl = 1, klon
          if ( ldcum(jl) .and. jk >= kctop(jl)-1 ) then
            zmfmax = (paph(jl,jk)-paph(jl,jk-1))*zcons
            if ( pmfu(jl,jk) > zmfmax .and. jk >= kctop(jl) ) then
              zmfs(jl) = min(zmfs(jl),zmfmax/pmfu(jl,jk))
            end if
          end if
        end do
      end do
      do jk = 1 , klev
        do jl = 1, klon
          zmfuus(jl,jk) = pmfu(jl,jk)
          zmfdus(jl,jk) = pmfd(jl,jk)
          if ( ldcum(jl) .and. jk >= kctop(jl)-1 ) then
            zmfuus(jl,jk) = pmfu(jl,jk)*zmfs(jl)
            zmfdus(jl,jk) = pmfd(jl,jk)*zmfs(jl)
          end if
        end do
      end do


     do jk = 1 , klev
        do jl = 1, klon
          ztenu(jl,jk) = pvom(jl,jk)
          ztenv(jl,jk) = pvol(jl,jk)
        end do
      end do

      call cududvn(klon,klev,itopm2,ktype,kcbot,kctop, &
                  ldcum,ztmst,paph,puen,pven,zmfuus,zmfdus,zuu,  &
                  zud,zvu,zvd,pvom,pvol)


      do jl = 1, klon
        zsum12(jl) = 0.
        zsum22(jl) = 0.
      end do
        do jk = 1 , klev
          do jl = 1, klon
            zuv2(jl,jk) = 0.
            if ( ldcum(jl) .and. jk >= kctop(jl)-1 ) then
              zdz = (paph(jl,jk+1)-paph(jl,jk))
              zduten = pvom(jl,jk) - ztenu(jl,jk)
              zdvten = pvol(jl,jk) - ztenv(jl,jk)
              zuv2(jl,jk) = sqrt(zduten**2+zdvten**2)
              zsum22(jl) = zsum22(jl) + zuv2(jl,jk)*zdz
              zsum12(jl) = zsum12(jl) - &
                (puen(jl,jk)*zduten+pven(jl,jk)*zdvten)*zdz
            end if
          end do
        end do
        do jk = 1 , klev
          do jl = 1, klon
            if ( ldcum(jl) .and. jk>=kctop(jl)-1 ) then
              ztdis = rcpd*zsum12(jl)*zuv2(jl,jk)/max(1.e-15,zsum22(jl))
              ptte(jl,jk) = ptte(jl,jk) + ztdis
            end if
          end do
        end do

      end if





    if ( .not. lmfscv .or. .not. lmfpen ) then
      do jk = 2 , klev
        do jl = 1, klon
          if ( llo2(jl) .and. jk >= kctop(jl)-1 ) then
            ptu(jl,jk) = pten(jl,jk)
            pqu(jl,jk) = pqen(jl,jk)
            plu(jl,jk) = 0.
            pmfude_rate(jl,jk) = 0.
            pmfdde_rate(jl,jk) = 0.
          end if
        end do
      end do
      do jl = 1, klon
        if ( llo2(jl) ) then
          kctop(jl) = klev - 1
          kcbot(jl) = klev - 1
        end if
      end do
    end if

      return
      end subroutine cumastrn





      subroutine cuinin &
     &    (klon,     klev,     klevp1,   klevm1,   pten,  &
     &     pqen,     pqsen,    puen,     pven,     pverv, &
     &     pgeo,     paph,     pgeoh,    ptenh,    pqenh, &
     &     pqsenh,   klwmin,   ptu,      pqu,      ptd,   &
     &     pqd,      puu,      pvu,      pud,      pvd,   &
     &     pmfu,     pmfd,     pmfus,    pmfds,    pmfuq, &
     &     pmfdq,    pdmfup,   pdmfdp,   pdpmel,   plu,   &
     &     plude,    klab)
      implicit none


















      integer,intent(in):: klon,klev,klevp1,klevm1

      real(kind=kind_phys),intent(in),dimension(klon,klev):: pten,pqen,pqsen,puen,pven
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pgeo,pverv
      real(kind=kind_phys),intent(in),dimension(klon,klev+1):: paph,pgeoh


      integer,intent(out),dimension(klon):: klwmin
      integer,intent(out),dimension(klon,klev):: klab

      real(kind=kind_phys),intent(out),dimension(klon,klev):: ptenh,pqenh,pqsenh
      real(kind=kind_phys),intent(out),dimension(klon,klev):: ptu,ptd,pqu,pqd,plu
      real(kind=kind_phys),intent(out),dimension(klon,klev):: puu,pud,pvu,pvd


      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pmfu,pmfd,pmfus,pmfds,pmfuq,pmfdq
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pdmfup,pdmfdp,plude,pdpmel


      logical,dimension(klon):: loflag
      integer::  jl,jk
      integer::  icall,ik
      real(kind=kind_phys):: zzs
      real(kind=kind_phys),dimension(klon):: zph,zwmax






      do jk=2,klev
      do jl=1,klon
        ptenh(jl,jk)=(max(cpd*pten(jl,jk-1)+pgeo(jl,jk-1), &
     &             cpd*pten(jl,jk)+pgeo(jl,jk))-pgeoh(jl,jk))*rcpd
        pqenh(jl,jk) = pqen(jl,jk-1)
        pqsenh(jl,jk)= pqsen(jl,jk-1)
        zph(jl)=paph(jl,jk)
        loflag(jl)=.true.
      end do

      if ( jk >= klev-1 .or. jk < 2 ) cycle
      ik=jk
      icall=0
      call cuadjtqn(klon,klev,ik,zph,ptenh,pqsenh,loflag,icall)
      do jl=1,klon
        pqenh(jl,jk)=min(pqen(jl,jk-1),pqsen(jl,jk-1)) &
     &            +(pqsenh(jl,jk)-pqsen(jl,jk-1))
        pqenh(jl,jk)=max(pqenh(jl,jk),0.)
      end do
      end do

      do jl=1,klon
        ptenh(jl,klev)=(cpd*pten(jl,klev)+pgeo(jl,klev)- &
     &                pgeoh(jl,klev))*rcpd
        pqenh(jl,klev)=pqen(jl,klev)
        ptenh(jl,1)=pten(jl,1)
        pqenh(jl,1)=pqen(jl,1)
        klwmin(jl)=klev
        zwmax(jl)=0.
      end do

      do jk=klevm1,2,-1
      do jl=1,klon
        zzs=max(cpd*ptenh(jl,jk)+pgeoh(jl,jk), &
     &        cpd*ptenh(jl,jk+1)+pgeoh(jl,jk+1))
        ptenh(jl,jk)=(zzs-pgeoh(jl,jk))*rcpd
      end do
      end do

      do jk=klev,3,-1
      do jl=1,klon
        if(pverv(jl,jk).lt.zwmax(jl)) then
           zwmax(jl)=pverv(jl,jk)
           klwmin(jl)=jk
        end if
      end do
      end do



      do jk=1,klev
      ik=jk-1
      if(jk.eq.1) ik=1
      do jl=1,klon
      ptu(jl,jk)=ptenh(jl,jk)
      ptd(jl,jk)=ptenh(jl,jk)
      pqu(jl,jk)=pqenh(jl,jk)
      pqd(jl,jk)=pqenh(jl,jk)
      plu(jl,jk)=0.
      puu(jl,jk)=puen(jl,ik)
      pud(jl,jk)=puen(jl,ik)
      pvu(jl,jk)=pven(jl,ik)
      pvd(jl,jk)=pven(jl,ik)
      klab(jl,jk)=0
      end do
      end do
      return
      end subroutine cuinin




      subroutine cutypen &
     &   (  klon,    klev,     klevp1,   klevm1,     pqen, &
     &     ptenh,   pqenh,     pqsenh,    pgeoh,     paph, &
     &       hfx,     qfx,       pgeo,    pqsen,      pap, &
     &      pten,    lndj,       cutu,     cuqu,    culab, &
     &     ldcum,   cubot,      cutop,    ktype,    wbase, &
     &      culu,    kdpl)









































      implicit none



      integer,intent(in):: klon,klev,klevp1,klevm1
      integer,intent(in),dimension(klon):: lndj

      real(kind=kind_phys),intent(in),dimension(klon):: qfx,hfx
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pap,pgeo
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pten,pqen,pqsen
      real(kind=kind_phys),intent(in),dimension(klon,klev):: ptenh,pqenh,pqsenh
      real(kind=kind_phys),intent(in),dimension(klon,klevp1):: paph,pgeoh


      logical,intent(out),dimension(klon):: ldcum

      integer,intent(out),dimension(klon):: ktype
      integer,intent(out),dimension(klon):: cubot,cutop,kdpl
      integer,intent(out),dimension(klon,klev):: culab

      real(kind=kind_phys),intent(out),dimension(klon):: wbase
      real(kind=kind_phys),intent(out),dimension(klon,klev):: cutu,cuqu,culu


      logical:: needreset
      logical,dimension(klon):: lldcum
      logical,dimension(klon):: loflag,deepflag,resetflag

      integer:: jl,jk,ik,icall,levels
      integer:: nk,is,ikb,ikt
      integer,dimension(klon):: kctop,kcbot
      integer,dimension(klon):: zcbase,itoppacel
      integer,dimension(klon,klev):: klab

      real(kind=kind_phys):: rho,part1,part2,root,conw,deltt,deltq
      real(kind=kind_phys):: zz,zdken,zdq
      real(kind=kind_phys):: fscale,crirh1,pp
      real(kind=kind_phys):: atop1,atop2,abot
      real(kind=kind_phys):: tmix,zmix,qmix,pmix
      real(kind=kind_phys):: zlglac,dp
      real(kind=kind_phys):: zqsu,zcor,zdp,zesdp,zalfaw,zfacw,zfaci,zfac,zdsdp,zdqsdt,zdtdp
      real(kind=kind_phys):: zpdifftop, zpdiffbot

      real(kind=kind_phys),dimension(klon):: eta,dz,coef,zqold,zph
      real(kind=kind_phys),dimension(klon,klev):: dh,dhen,kup,vptu,vten
      real(kind=kind_phys),dimension(klon,klev):: ptu,pqu,plu
      real(kind=kind_phys),dimension(klon,klev):: zbuo,abuoy,plude


      do jl=1,klon
        kcbot(jl)=klev
        kctop(jl)=klev
        kdpl(jl) =klev
        ktype(jl)=0
        wbase(jl)=0.
        ldcum(jl)=.false.
      end do






      do jk=1,klev
      do jl=1,klon
          plu(jl,jk)=culu(jl,jk)  
          ptu(jl,jk)=cutu(jl,jk)  
          pqu(jl,jk)=cuqu(jl,jk)  
          klab(jl,jk)=culab(jl,jk)
           dh(jl,jk)=0.0  
         dhen(jl,jk)=0.0  
          kup(jl,jk)=0.0  
         vptu(jl,jk)=0.0  
         vten(jl,jk)=0.0  
         zbuo(jl,jk)=0.0  
         abuoy(jl,jk)=0.0
      end do
      end do

      do jl=1,klon
         zqold(jl) = 0.
         lldcum(jl) = .false.
         loflag(jl) = .true.
      end do


      do jk=klevm1,2,-1


      if(jk .eq. klevm1) then
      do jl=1,klon
        rho=pap(jl,klev)/ &
     &         (rd*(pten(jl,klev)*(1.+vtmpc1*pqen(jl,klev))))
        part1 = 1.5*0.4*pgeo(jl,klev)/ &
     &              (rho*pten(jl,klev))
        part2 = -hfx(jl)*rcpd-vtmpc1*pten(jl,klev)*qfx(jl)
        root  = 0.001-part1*part2
        if(part2 .lt. 0.) then
           conw  = 1.2*(root)**t13
           deltt = max(1.5*hfx(jl)/(rho*cpd*conw),0.)
           deltq = max(1.5*qfx(jl)/(rho*conw),0.)
           kup(jl,klev) = 0.5*(conw**2)
           pqu(jl,klev)= pqenh(jl,klev) + deltq
          dhen(jl,klev)= pgeoh(jl,klev) + ptenh(jl,klev)*cpd
           dh(jl,klev) = dhen(jl,klev)  + deltt*cpd
          ptu(jl,klev) = (dh(jl,klev)-pgeoh(jl,klev))*rcpd
          vptu(jl,klev)=ptu(jl,klev)*(1.+vtmpc1*pqu(jl,klev))
          vten(jl,klev)=ptenh(jl,klev)*(1.+vtmpc1*pqenh(jl,klev))
          zbuo(jl,klev)=(vptu(jl,klev)-vten(jl,klev))/vten(jl,klev)
          klab(jl,klev) = 1
        else
          loflag(jl) = .false.
        end if
      end do
      end if

      is=0
      do jl=1,klon
         if(loflag(jl))then
            is=is+1
         endif
      enddo
      if(is.eq.0) exit


      do jl=1,klon
      if(loflag(jl)) then
        eta(jl) = 0.8/(pgeo(jl,jk)*zrg)+2.e-4
        dz(jl)  = (pgeoh(jl,jk)-pgeoh(jl,jk+1))*zrg
        coef(jl)= 0.5*eta(jl)*dz(jl)
        dhen(jl,jk) = pgeoh(jl,jk) + cpd*ptenh(jl,jk)
        dh(jl,jk) = (coef(jl)*(dhen(jl,jk+1)+dhen(jl,jk))&
     &              +(1.-coef(jl))*dh(jl,jk+1))/(1.+coef(jl))
        pqu(jl,jk) =(coef(jl)*(pqenh(jl,jk+1)+pqenh(jl,jk))&
     &              +(1.-coef(jl))*pqu(jl,jk+1))/(1.+coef(jl))
        ptu(jl,jk) = (dh(jl,jk)-pgeoh(jl,jk))*rcpd
        zqold(jl) = pqu(jl,jk)
        zph(jl)=paph(jl,jk)
      end if
      end do

      ik=jk
      icall=1
      call cuadjtqn(klon,klev,ik,zph,ptu,pqu,loflag,icall)
      do jl=1,klon
        if( loflag(jl) ) then
          zdq = max((zqold(jl) - pqu(jl,jk)),0.)
          plu(jl,jk) = plu(jl,jk+1) + zdq
          zlglac=zdq*((1.-foealfa(ptu(jl,jk))) - &
                      (1.-foealfa(ptu(jl,jk+1))))
          plu(jl,jk) = min(plu(jl,jk),5.e-3)
          dh(jl,jk) =  pgeoh(jl,jk) + cpd*(ptu(jl,jk)+ralfdcp*zlglac)

          vptu(jl,jk) = ptu(jl,jk)*(1.+vtmpc1*pqu(jl,jk)-plu(jl,jk))+&
                        ralfdcp*zlglac
          vten(jl,jk) = ptenh(jl,jk)*(1.+vtmpc1*pqenh(jl,jk))
          zbuo(jl,jk) = (vptu(jl,jk) - vten(jl,jk))/vten(jl,jk)
          abuoy(jl,jk)=(zbuo(jl,jk)+zbuo(jl,jk+1))*0.5*g
          atop1 = 1.0 - 2.*coef(jl)
          atop2 = 2.0*dz(jl)*abuoy(jl,jk)
          abot =  1.0 + 2.*coef(jl)
          kup(jl,jk)  = (atop1*kup(jl,jk+1) + atop2) / abot


         if ( plu(jl,jk) > 0. .and. klab(jl,jk+1) == 1 ) then
              ik = jk + 1
              zqsu = foeewm(ptu(jl,ik))/paph(jl,ik)
              zqsu = min(0.5,zqsu)
              zcor = 1./(1.-vtmpc1*zqsu)
              zqsu = zqsu*zcor
              zdq = min(0.,pqu(jl,ik)-zqsu)
              zalfaw = foealfa(ptu(jl,ik))
              zfacw = c5les/((ptu(jl,ik)-c4les)**2)
              zfaci = c5ies/((ptu(jl,ik)-c4ies)**2)
              zfac = zalfaw*zfacw + (1.-zalfaw)*zfaci
              zesdp = foeewm(ptu(jl,ik))/paph(jl,ik)
              zcor = 1./(1.-vtmpc1*zesdp)
              zdqsdt = zfac*zcor*zqsu
              zdtdp = rd*ptu(jl,ik)/(cpd*paph(jl,ik))
              zdp = zdq/(zdqsdt*zdtdp)
              zcbase(jl) = paph(jl,ik) + zdp

              zpdifftop = zcbase(jl) - paph(jl,jk)
              zpdiffbot = paph(jl,jk+1) - zcbase(jl)
              if ( zpdifftop > zpdiffbot .and. kup(jl,jk+1) > 0. ) then
                ikb = min(klev-1,jk+1)
                klab(jl,ikb) = 2
                klab(jl,jk) = 2
                kcbot(jl) = ikb
                plu(jl,jk+1) = 1.0e-8
              else if ( zpdifftop <= zpdiffbot .and.kup(jl,jk) > 0. ) then
                klab(jl,jk) = 2
                kcbot(jl) = jk
              end if
          end if

          if(kup(jl,jk) .lt. 0.)then
            loflag(jl) = .false.
            if(plu(jl,jk+1) .gt. 0.) then
              kctop(jl) = jk
              lldcum(jl) = .true.
            else
              lldcum(jl) = .false.
            end if
          else 
            if(plu(jl,jk) .gt. 0.)then
              klab(jl,jk)=2
            else
              klab(jl,jk)=1
            end if
          end if
        end if
      end do

      end do 

      do jl=1,klon
        ikb = kcbot(jl)
        ikt = kctop(jl)
        if(paph(jl,ikb) - paph(jl,ikt) > zdnoprc) lldcum(jl) = .false.
        if(lldcum(jl)) then
            ktype(jl) = 2
            ldcum(jl) = .true.
            wbase(jl) = sqrt(max(2.*kup(jl,ikb),0.))
            cubot(jl) = ikb
            cutop(jl) = ikt
            kdpl(jl)  = klev
        else
            cutop(jl) = -1
            cubot(jl) = -1
            kdpl(jl)  = klev - 1
            ldcum(jl) = .false.
            wbase(jl) = 0.
        end if
      end do

      do jk=klev,1,-1
       do jl=1,klon
           ikt = kctop(jl)
           if(jk .ge. ikt)then
             culab(jl,jk) = klab(jl,jk)
             cutu(jl,jk)  = ptu(jl,jk)
             cuqu(jl,jk)  = pqu(jl,jk)
             culu(jl,jk)  = plu(jl,jk)
           end if
       end do
      end do








      deltt = 0.2
      deltq = 1.0e-4
      do jl=1,klon
        deepflag(jl) = .false.
      end do

      do jk=klev,1,-1
       do jl=1,klon
         if((paph(jl,klev+1)-paph(jl,jk)) .lt. 350.e2) itoppacel(jl) = jk
       end do
      end do

      do levels=klevm1-1,klev/2+1,-1 
        do jk=1,klev
          do jl=1,klon
             plu(jl,jk)=0.0  
             ptu(jl,jk)=0.0  
             pqu(jl,jk)=0.0  
             dh(jl,jk)=0.0   
             dhen(jl,jk)=0.0  
             kup(jl,jk)=0.0   
             vptu(jl,jk)=0.0  
             vten(jl,jk)=0.0  
             abuoy(jl,jk)=0.0
             zbuo(jl,jk)=0.0
             klab(jl,jk)=0
          end do
        end do

        do jl=1,klon
           kcbot(jl)    =  levels
           kctop(jl)    =  levels
           zqold(jl)    = 0.
           lldcum(jl)   = .false.
           resetflag(jl)= .false.
           loflag(jl)   = (.not. deepflag(jl)) .and. (levels.ge.itoppacel(jl))
        end do


      do jk=levels,2,-1
        is=0
        do jl=1,klon
         if(loflag(jl))then
            is=is+1
         endif
        enddo
        if(is.eq.0) exit


        if(jk .eq. levels) then
          do jl=1,klon
          if(loflag(jl)) then
            if((paph(jl,klev+1)-paph(jl,jk)) < 60.e2) then
              tmix=0.
              qmix=0.
              zmix=0.
              pmix=0.
              do nk=jk+2,jk,-1
              if(pmix < 50.e2) then
                dp = paph(jl,nk) - paph(jl,nk-1)
                tmix=tmix+dp*ptenh(jl,nk)
                qmix=qmix+dp*pqenh(jl,nk)
                zmix=zmix+dp*pgeoh(jl,nk)
                pmix=pmix+dp
              end if
              end do
              tmix=tmix/pmix
              qmix=qmix/pmix
              zmix=zmix/pmix
            else
              tmix=ptenh(jl,jk+1)
              qmix=pqenh(jl,jk+1)
              zmix=pgeoh(jl,jk+1)
            end if

            pqu(jl,jk+1) = qmix + deltq
            dhen(jl,jk+1)= zmix + tmix*cpd
            dh(jl,jk+1)  = dhen(jl,jk+1) + deltt*cpd
            ptu(jl,jk+1) = (dh(jl,jk+1)-pgeoh(jl,jk+1))*rcpd
            kup(jl,jk+1) = 0.5
            klab(jl,jk+1)= 1
            vptu(jl,jk+1)=ptu(jl,jk+1)*(1.+vtmpc1*pqu(jl,jk+1))
            vten(jl,jk+1)=ptenh(jl,jk+1)*(1.+vtmpc1*pqenh(jl,jk+1))
            zbuo(jl,jk+1)=(vptu(jl,jk+1)-vten(jl,jk+1))/vten(jl,jk+1)
          end if
          end do
        end if


        do jl=1,klon
           if(loflag(jl)) then

             fscale = min(1.,(pqsen(jl,jk)/pqsen(jl,levels))**3)
             eta(jl) = 1.75e-3*fscale
             dz(jl)  = (pgeoh(jl,jk)-pgeoh(jl,jk+1))*zrg
             coef(jl)= 0.5*eta(jl)*dz(jl)
             dhen(jl,jk) = pgeoh(jl,jk) + cpd*ptenh(jl,jk)
             dh(jl,jk) = (coef(jl)*(dhen(jl,jk+1)+dhen(jl,jk))&
     &              +(1.-coef(jl))*dh(jl,jk+1))/(1.+coef(jl))
             pqu(jl,jk) =(coef(jl)*(pqenh(jl,jk+1)+pqenh(jl,jk))&
     &              +(1.-coef(jl))*pqu(jl,jk+1))/(1.+coef(jl))
             ptu(jl,jk) = (dh(jl,jk)-pgeoh(jl,jk))*rcpd
             zqold(jl) = pqu(jl,jk)
             zph(jl)=paph(jl,jk)
           end if
        end do

        ik=jk
        icall=1
        call cuadjtqn(klon,klev,ik,zph,ptu,pqu,loflag,icall)

      do jl=1,klon
        if( loflag(jl) ) then
          zdq = max((zqold(jl) - pqu(jl,jk)),0.)
          plu(jl,jk) = plu(jl,jk+1) + zdq
          zlglac=zdq*((1.-foealfa(ptu(jl,jk))) - &
                      (1.-foealfa(ptu(jl,jk+1))))
          plu(jl,jk) = 0.5*plu(jl,jk)
          dh(jl,jk) =  pgeoh(jl,jk) + cpd*(ptu(jl,jk)+ralfdcp*zlglac)

          vptu(jl,jk) = ptu(jl,jk)*(1.+vtmpc1*pqu(jl,jk)-plu(jl,jk))+&
                        ralfdcp*zlglac
          vten(jl,jk) = ptenh(jl,jk)*(1.+vtmpc1*pqenh(jl,jk))
          zbuo(jl,jk) = (vptu(jl,jk) - vten(jl,jk))/vten(jl,jk)
          abuoy(jl,jk)=(zbuo(jl,jk)+zbuo(jl,jk+1))*0.5*g
          atop1 = 1.0 - 2.*coef(jl)
          atop2 = 2.0*dz(jl)*abuoy(jl,jk)
          abot =  1.0 + 2.*coef(jl)
          kup(jl,jk)  = (atop1*kup(jl,jk+1) + atop2) / abot

          if ( plu(jl,jk) > 0. .and. klab(jl,jk+1) == 1 ) then
              ik = jk + 1
              zqsu = foeewm(ptu(jl,ik))/paph(jl,ik)
              zqsu = min(0.5,zqsu)
              zcor = 1./(1.-vtmpc1*zqsu)
              zqsu = zqsu*zcor
              zdq = min(0.,pqu(jl,ik)-zqsu)
              zalfaw = foealfa(ptu(jl,ik))
              zfacw = c5les/((ptu(jl,ik)-c4les)**2)
              zfaci = c5ies/((ptu(jl,ik)-c4ies)**2)
              zfac = zalfaw*zfacw + (1.-zalfaw)*zfaci
              zesdp = foeewm(ptu(jl,ik))/paph(jl,ik)
              zcor = 1./(1.-vtmpc1*zesdp)
              zdqsdt = zfac*zcor*zqsu
              zdtdp = rd*ptu(jl,ik)/(cpd*paph(jl,ik))
              zdp = zdq/(zdqsdt*zdtdp)
              zcbase(jl) = paph(jl,ik) + zdp

              zpdifftop = zcbase(jl) - paph(jl,jk)
              zpdiffbot = paph(jl,jk+1) - zcbase(jl)
              if ( zpdifftop > zpdiffbot .and. kup(jl,jk+1) > 0. ) then
                ikb = min(klev-1,jk+1)
                klab(jl,ikb) = 2
                klab(jl,jk) = 2
                kcbot(jl) = ikb
                plu(jl,jk+1) = 1.0e-8
              else if ( zpdifftop <= zpdiffbot .and.kup(jl,jk) > 0. ) then
                klab(jl,jk) = 2
                kcbot(jl) = jk
              end if
          end if

          if(kup(jl,jk) .lt. 0.)then
            loflag(jl) = .false.
            if(plu(jl,jk+1) .gt. 0.) then
              kctop(jl) = jk
              lldcum(jl) = .true.
            else
              lldcum(jl) = .false.
            end if
          else
            if(plu(jl,jk) .gt. 0.)then
              klab(jl,jk)=2
            else
              klab(jl,jk)=1
            end if
          end if
        end if
      end do

      end do 

      needreset = .false.
      do jl=1,klon
        ikb = kcbot(jl)
        ikt = kctop(jl)
        if(paph(jl,ikb) - paph(jl,ikt) < zdnoprc) lldcum(jl) = .false.
        if(lldcum(jl)) then
         ktype(jl)    = 1
         ldcum(jl)    = .true.
         deepflag(jl) = .true.
         wbase(jl)    = sqrt(max(2.*kup(jl,ikb),0.))
         cubot(jl)    = ikb
         cutop(jl)    = ikt
         kdpl(jl)     = levels+1
         needreset    = .true.
         resetflag(jl)= .true.
        end if
      end do

      if(needreset) then
      do jk=klev,1,-1
        do jl=1,klon
          if(resetflag(jl)) then
            ikt = kctop(jl)
            ikb = kdpl(jl)
            if(jk .le. ikb .and. jk .ge. ikt )then
             culab(jl,jk) = klab(jl,jk)
             cutu(jl,jk)  = ptu(jl,jk)
             cuqu(jl,jk)  = pqu(jl,jk)
             culu(jl,jk)  = plu(jl,jk)
            else
             culab(jl,jk) = 1
             cutu(jl,jk)  = ptenh(jl,jk)
             cuqu(jl,jk)  = pqenh(jl,jk)
             culu(jl,jk)  = 0.
            end if
            if ( jk .lt. ikt ) culab(jl,jk) = 0
          end if
        end do
      end do
      end if

      end do 

      return
      end subroutine cutypen




      subroutine cuascn &
     &    (klon,     klev,     klevp1,   klevm1,   ptenh,   &
     &     pqenh,    puen,     pven,     pten,     pqen,    &
     &     pqsen,    pgeo,     pgeoh,    pap,      paph,    &
     &     pqte,     pverv,    klwmin,   ldcum,    phcbase, &
     &     ktype,    klab,     ptu,      pqu,      plu,     &
     &     puu,      pvu,      pmfu,     pmfub,             &
     &     pmfus,    pmfuq,    pmful,    plude,    pdmfup,  &
     &     kcbot,    kctop,    kctop0,   kcum,     ztmst,   &
     &     pqsenh,   plglac,   lndj,     wup,      wbase,   &
     &     kdpl,     pmfude_rate)

      implicit none







































































      integer,intent(in):: klev,klon,klevp1,klevm1
      integer,intent(in),dimension(klon):: lndj
      integer,intent(in),dimension(klon):: klwmin
      integer,intent(in),dimension(klon):: kdpl

      real(kind=kind_phys),intent(in):: ztmst
      real(kind=kind_phys),intent(in),dimension(klon):: wbase
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pten,pqen,pqsen,puen,pven,pqte,pverv
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pap,pgeo
      real(kind=kind_phys),intent(in),dimension(klon,klevp1):: paph,pgeoh


      logical,intent(inout),dimension(klon):: ldcum

      integer,intent(inout):: kcum
      integer,intent(inout),dimension(klon):: kcbot,kctop,kctop0
      integer,intent(inout),dimension(klon,klev):: klab

      real(kind=kind_phys),intent(inout),dimension(klon):: phcbase
      real(kind=kind_phys),intent(inout),dimension(klon):: pmfub
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: ptenh,pqenh,pqsenh
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: ptu,pqu,plu,puu,pvu
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pmfu,pmfus,pmfuq,pmful,plude,pdmfup


      integer,intent(out),dimension(klon):: ktype

      real(kind=kind_phys),intent(out),dimension(klon):: wup
      real(kind=kind_phys),intent(out),dimension(klon,klev):: plglac,pmfude_rate


      logical:: llo2,llo3
      logical,dimension(klon):: loflag,llo1

      integer:: jl,jk
      integer::ikb,icum,itopm2,ik,icall,is,jlm,jll
      integer,dimension(klon):: jlx

      real(kind=kind_phys):: zcons2,zfacbuo,zprcdgw,z_cwdrag,z_cldmax,z_cwifrac,z_cprc2
      real(kind=kind_phys):: zmftest,zmfmax,zqeen,zseen,zscde,zqude
      real(kind=kind_phys):: zmfusk,zmfuqk,zmfulk
      real(kind=kind_phys):: zbc,zbe,zkedke,zmfun,zwu,zprcon,zdt,zcbf,zzco
      real(kind=kind_phys):: zlcrit,zdfi,zc,zd,zint,zlnew,zvw,zvi,zalfaw,zrold
      real(kind=kind_phys):: zrnew,zz,zdmfeu,zdmfdu,dp
      real(kind=kind_phys):: zfac,zbuoc,zdkbuo,zdken,zvv,zarg,zchange,zxe,zxs,zdshrd
      real(kind=kind_phys):: atop1,atop2,abot

      real(kind=kind_phys),dimension(klon):: eta,dz,zoentr,zdpmean
      real(kind=kind_phys),dimension(klon):: zph,zdmfen,zdmfde,zmfuu,zmfuv,zpbase,zqold,zluold,zprecip
      real(kind=kind_phys),dimension(klon,klev):: zlrain,zbuo,kup,zodetr,pdmfen




      zcons2=3./(g*ztmst)
      zfacbuo = 0.5/(1.+0.5)
      zprcdgw = cprcon*zrg
      z_cldmax = 5.e-3
      z_cwifrac = 0.5
      z_cprc2 = 0.5
      z_cwdrag = (3.0/8.0)*0.506/0.2



      llo3 = .false.
      do jl=1,klon
        zluold(jl)=0.
        wup(jl)=0.
        zdpmean(jl)=0.
        zoentr(jl)=0.
        if(.not.ldcum(jl)) then
          ktype(jl)=0
          kcbot(jl) = -1
          pmfub(jl) = 0.
          pqu(jl,klev) = 0.
        end if
      end do

 
      do jk=1,klev
      do jl=1,klon
          if(jk.ne.kcbot(jl)) plu(jl,jk)=0.
          pmfu(jl,jk)=0.
          pmfus(jl,jk)=0.
          pmfuq(jl,jk)=0.
          pmful(jl,jk)=0.
          plude(jl,jk)=0.
          plglac(jl,jk)=0.
          pdmfup(jl,jk)=0.
          zlrain(jl,jk)=0.
          zbuo(jl,jk)=0.
          kup(jl,jk)=0.
          pdmfen(jl,jk) = 0.
          pmfude_rate(jl,jk) = 0.
          if(.not.ldcum(jl).or.ktype(jl).eq.3) klab(jl,jk)=0
          if(.not.ldcum(jl).and.paph(jl,jk).lt.4.e4) kctop0(jl)=jk
      end do
      end do

      do jl = 1,klon
        if ( ktype(jl) == 3 ) ldcum(jl) = .false.
      end do



      do jl=1,klon
        kctop(jl)=kcbot(jl)
        if(ldcum(jl)) then
          ikb = kcbot(jl)
          kup(jl,ikb) = 0.5*wbase(jl)**2
          pmfu(jl,ikb) = pmfub(jl)
          pmfus(jl,ikb) = pmfub(jl)*(cpd*ptu(jl,ikb)+pgeoh(jl,ikb))
          pmfuq(jl,ikb) = pmfub(jl)*pqu(jl,ikb)
          pmful(jl,ikb) = pmfub(jl)*plu(jl,ikb)
        end if
      end do








      do jk=klevm1,3,-1



      ik=jk
      call cubasmcn&
     &    (klon,     klev,     klevm1,   ik,      pten,          &
     &     pqen,     pqsen,    puen,     pven,    pverv,         &
     &     pgeo,     pgeoh,    ldcum,    ktype,   klab,  zlrain, &
     &     pmfu,     pmfub,    kcbot,    ptu,                    &
     &     pqu,      plu,      puu,      pvu,      pmfus,        &
     &     pmfuq,    pmful,    pdmfup)
      is = 0
      jlm = 0
      do jl = 1,klon
        loflag(jl) = .false.
        zprecip(jl) = 0.
        llo1(jl) = .false.
        is = is + klab(jl,jk+1)
        if ( klab(jl,jk+1) == 0 ) klab(jl,jk) = 0
        if ( (ldcum(jl) .and. klab(jl,jk+1) == 2) .or.   &
             (ktype(jl) == 3 .and. klab(jl,jk+1) == 1) ) then
          loflag(jl) = .true.
          jlm = jlm + 1
          jlx(jlm) = jl
        end if
        zph(jl) = paph(jl,jk)
        if ( ktype(jl) == 3 .and. jk == kcbot(jl) ) then
          zmfmax = (paph(jl,jk)-paph(jl,jk-1))*zcons2
          if ( pmfub(jl) > zmfmax ) then
            zfac = zmfmax/pmfub(jl)
            pmfu(jl,jk+1) = pmfu(jl,jk+1)*zfac
            pmfus(jl,jk+1) = pmfus(jl,jk+1)*zfac
            pmfuq(jl,jk+1) = pmfuq(jl,jk+1)*zfac
            pmfub(jl) = zmfmax
          end if
          pmfub(jl)=min(pmfub(jl),zmfmax)
        end if
      end do

      if(is.gt.0) llo3 = .true.



      ik=jk
      call cuentrn(klon,klev,ik,kcbot,ldcum,llo3, &
                  pgeoh,pmfu,zdmfen,zdmfde)


      if(llo3) then


        do jl = 1,klon
          zqold(jl) = 0.
        end do
        do jll = 1 , jlm
          jl = jlx(jll)
          zdmfde(jl) = min(zdmfde(jl),0.75*pmfu(jl,jk+1))
          if ( jk == kcbot(jl) ) then
            zoentr(jl) = -1.75e-3*(min(1.,pqen(jl,jk)/pqsen(jl,jk)) - &
                         1.)*(pgeoh(jl,jk)-pgeoh(jl,jk+1))*zrg
            zoentr(jl) = min(0.4,zoentr(jl))*pmfu(jl,jk+1)
          end if
          if ( jk < kcbot(jl) ) then
            zmfmax = (paph(jl,jk)-paph(jl,jk-1))*zcons2
            zxs = max(pmfu(jl,jk+1)-zmfmax,0.)
            wup(jl) = wup(jl) + kup(jl,jk+1)*(pap(jl,jk+1)-pap(jl,jk))
            zdpmean(jl) = zdpmean(jl) + pap(jl,jk+1) - pap(jl,jk)
            zdmfen(jl) = zoentr(jl)
            if ( ktype(jl) >= 2 ) then
              zdmfen(jl) = 2.0*zdmfen(jl)
              zdmfde(jl) = zdmfen(jl)
            end if
            zdmfde(jl) = zdmfde(jl) * &
                         (1.6-min(1.,pqen(jl,jk)/pqsen(jl,jk)))
            zmftest = pmfu(jl,jk+1) + zdmfen(jl) - zdmfde(jl)
            zchange = max(zmftest-zmfmax,0.)
            zxe = max(zchange-zxs,0.)
            zdmfen(jl) = zdmfen(jl) - zxe
            zchange = zchange - zxe
            zdmfde(jl) = zdmfde(jl) + zchange
          end if
          pdmfen(jl,jk) = zdmfen(jl) - zdmfde(jl)
          pmfu(jl,jk) = pmfu(jl,jk+1) + zdmfen(jl) - zdmfde(jl)
          zqeen = pqenh(jl,jk+1)*zdmfen(jl)
          zseen = (cpd*ptenh(jl,jk+1)+pgeoh(jl,jk+1))*zdmfen(jl)
          zscde = (cpd*ptu(jl,jk+1)+pgeoh(jl,jk+1))*zdmfde(jl)
          zqude = pqu(jl,jk+1)*zdmfde(jl)
          plude(jl,jk) = plu(jl,jk+1)*zdmfde(jl)
          zmfusk = pmfus(jl,jk+1) + zseen - zscde
          zmfuqk = pmfuq(jl,jk+1) + zqeen - zqude
          zmfulk = pmful(jl,jk+1) - plude(jl,jk)
          plu(jl,jk) = zmfulk*(1./max(cmfcmin,pmfu(jl,jk)))
          pqu(jl,jk) = zmfuqk*(1./max(cmfcmin,pmfu(jl,jk)))
          ptu(jl,jk) = (zmfusk * &
            (1./max(cmfcmin,pmfu(jl,jk)))-pgeoh(jl,jk))*rcpd
          ptu(jl,jk) = max(100.,ptu(jl,jk))
          ptu(jl,jk) = min(400.,ptu(jl,jk))
          zqold(jl) = pqu(jl,jk)
          zlrain(jl,jk) = zlrain(jl,jk+1)*(pmfu(jl,jk+1)-zdmfde(jl)) * &
                          (1./max(cmfcmin,pmfu(jl,jk)))
          zluold(jl) = plu(jl,jk)
        end do

        do jl = 1,klon
          if ( jk > kdpl(jl) ) then
            ptu(jl,jk) = ptenh(jl,jk)
            pqu(jl,jk) = pqenh(jl,jk)
            plu(jl,jk) = 0.
            zluold(jl) = plu(jl,jk)
          end if
        end do



      ik=jk
      icall=1

      if ( jlm > 0 ) then
        call cuadjtqn(klon,klev,ik,zph,ptu,pqu,loflag,icall)
      end if

        do jll = 1 , jlm
          jl = jlx(jll)
          if ( pqu(jl,jk) /= zqold(jl) ) then
            plglac(jl,jk) = plu(jl,jk) * &
                           ((1.-foealfa(ptu(jl,jk)))- &
                            (1.-foealfa(ptu(jl,jk+1))))
            ptu(jl,jk) = ptu(jl,jk) + ralfdcp*plglac(jl,jk)
          end if
        end do
        do jll = 1 , jlm
          jl = jlx(jll)
          if ( pqu(jl,jk) /= zqold(jl) ) then
            klab(jl,jk) = 2
            plu(jl,jk) = plu(jl,jk) + zqold(jl) - pqu(jl,jk)
            zbc = ptu(jl,jk)*(1.+vtmpc1*pqu(jl,jk)-plu(jl,jk+1) - &
              zlrain(jl,jk+1))
            zbe = ptenh(jl,jk)*(1.+vtmpc1*pqenh(jl,jk))
            zbuo(jl,jk) = zbc - zbe

            if ( ktype(jl) == 3 .and. klab(jl,jk+1) == 1 ) then
              if ( zbuo(jl,jk) > -0.5 ) then
                ldcum(jl) = .true.
                kctop(jl) = jk
                kup(jl,jk) = 0.5
              else
                klab(jl,jk) = 0
                pmfu(jl,jk) = 0.
                plude(jl,jk) = 0.
                plu(jl,jk) = 0.
              end if
            end if
            if ( klab(jl,jk+1) == 2 ) then
              if ( zbuo(jl,jk) < 0. ) then
                ptenh(jl,jk) = 0.5*(pten(jl,jk)+pten(jl,jk-1))
                pqenh(jl,jk) = 0.5*(pqen(jl,jk)+pqen(jl,jk-1))
                zbuo(jl,jk) = zbc - ptenh(jl,jk)*(1.+vtmpc1*pqenh(jl,jk))
              end if
              zbuoc = (zbuo(jl,jk) / &
                (ptenh(jl,jk)*(1.+vtmpc1*pqenh(jl,jk)))+zbuo(jl,jk+1) / &
                (ptenh(jl,jk+1)*(1.+vtmpc1*pqenh(jl,jk+1))))*0.5
              zdkbuo = (pgeoh(jl,jk)-pgeoh(jl,jk+1))*zfacbuo*zbuoc

              if ( zdmfen(jl) > 0. ) then
                zdken = min(1.,(1.+z_cwdrag)*zdmfen(jl) / &
                        max(cmfcmin,pmfu(jl,jk+1)))
              else
                zdken = min(1.,(1.+z_cwdrag)*zdmfde(jl) / &
                        max(cmfcmin,pmfu(jl,jk+1)))
              end if
              kup(jl,jk) = (kup(jl,jk+1)*(1.-zdken)+zdkbuo) / &
                           (1.+zdken)
              if ( zbuo(jl,jk) < 0. ) then
                zkedke = kup(jl,jk)/max(1.e-10,kup(jl,jk+1))
                zkedke = max(0.,min(1.,zkedke))
                zmfun = sqrt(zkedke)*pmfu(jl,jk+1)
                zdmfde(jl) = max(zdmfde(jl),pmfu(jl,jk+1)-zmfun)
                plude(jl,jk) = plu(jl,jk+1)*zdmfde(jl)
                pmfu(jl,jk) = pmfu(jl,jk+1) + zdmfen(jl) - zdmfde(jl)
              end if
              if ( zbuo(jl,jk) > -0.2  ) then
                ikb = kcbot(jl)
                zoentr(jl) = 1.75e-3*(0.3-(min(1.,pqen(jl,jk-1) /    &
                  pqsen(jl,jk-1))-1.))*(pgeoh(jl,jk-1)-pgeoh(jl,jk)) * &
                  zrg*min(1.,pqsen(jl,jk)/pqsen(jl,ikb))**3
                zoentr(jl) = min(0.4,zoentr(jl))*pmfu(jl,jk)
              else
                zoentr(jl) = 0.
              end if

              if ( jk > kdpl(jl) ) then
                pmfu(jl,jk) = pmfu(jl,jk+1)
                kup(jl,jk) = 0.5
              end if
              if ( kup(jl,jk) > 0. .and. pmfu(jl,jk) > 0. ) then
                kctop(jl) = jk
                llo1(jl) = .true.
              else
                klab(jl,jk) = 0
                pmfu(jl,jk) = 0.
                kup(jl,jk) = 0.
                zdmfde(jl) = pmfu(jl,jk+1)
                plude(jl,jk) = plu(jl,jk+1)*zdmfde(jl)
              end if

              if ( pmfu(jl,jk+1) > 0. ) pmfude_rate(jl,jk) = zdmfde(jl)
            end if
          else if ( ktype(jl) == 2 .and. pqu(jl,jk) == zqold(jl) ) then
            klab(jl,jk) = 0
            pmfu(jl,jk) = 0.
            kup(jl,jk) = 0.
            zdmfde(jl) = pmfu(jl,jk+1)
            plude(jl,jk) = plu(jl,jk+1)*zdmfde(jl)
            pmfude_rate(jl,jk) = zdmfde(jl)
          end if
        end do

        do jl = 1,klon
          if ( llo1(jl) ) then



            if ( lndj(jl).eq.1 ) then
              zdshrd = 5.e-4
            else
              zdshrd = 3.e-4
            end if
            ikb=kcbot(jl)
            if ( plu(jl,jk) > zdshrd )then
              zwu = min(15.0,sqrt(2.*max(0.1,kup(jl,jk+1))))
              zprcon = zprcdgw/(0.75*zwu)

              zdt = min(rtber-rtice,max(rtber-ptu(jl,jk),0.))
              zcbf = 1. + z_cprc2*sqrt(zdt)
              zzco = zprcon*zcbf
              zlcrit = zdshrd/zcbf
              zdfi = pgeoh(jl,jk) - pgeoh(jl,jk+1)
              zc = (plu(jl,jk)-zluold(jl))
              zarg = (plu(jl,jk)/zlcrit)**2
              if ( zarg < 25.0 ) then
                zd = zzco*(1.-exp(-zarg))*zdfi
              else
                zd = zzco*zdfi
              end if
              zint = exp(-zd)
              zlnew = zluold(jl)*zint + zc/zd*(1.-zint)
              zlnew = max(0.,min(plu(jl,jk),zlnew))
              zlnew = min(z_cldmax,zlnew)
              zprecip(jl) = max(0.,zluold(jl)+zc-zlnew)
              pdmfup(jl,jk) = zprecip(jl)*pmfu(jl,jk)
              zlrain(jl,jk) = zlrain(jl,jk) + zprecip(jl)
              plu(jl,jk) = zlnew
            end if
          end if
        end do
        do jl = 1, klon
          if ( llo1(jl) ) then
            if ( zlrain(jl,jk) > 0. ) then
              zvw = 21.18*zlrain(jl,jk)**0.2
              zvi = z_cwifrac*zvw
              zalfaw = foealfa(ptu(jl,jk))
              zvv = zalfaw*zvw + (1.-zalfaw)*zvi
              zrold = zlrain(jl,jk) - zprecip(jl)
              zc = zprecip(jl)
              zwu = min(15.0,sqrt(2.*max(0.1,kup(jl,jk))))
              zd = zvv/zwu
              zint = exp(-zd)
              zrnew = zrold*zint + zc/zd*(1.-zint)
              zrnew = max(0.,min(zlrain(jl,jk),zrnew))
              zlrain(jl,jk) = zrnew
            end if
          end if
        end do
        do jll = 1 , jlm
          jl = jlx(jll)
          pmful(jl,jk) = plu(jl,jk)*pmfu(jl,jk)
          pmfus(jl,jk) = (cpd*ptu(jl,jk)+pgeoh(jl,jk))*pmfu(jl,jk)
          pmfuq(jl,jk) = pqu(jl,jk)*pmfu(jl,jk)
        end do
      end if
    end do



      do jl = 1,klon
       if ( kctop(jl) == -1 ) ldcum(jl) = .false.
        kcbot(jl) = max(kcbot(jl),kctop(jl))
        if ( ldcum(jl) ) then
          wup(jl) = max(1.e-2,wup(jl)/max(1.,zdpmean(jl)))
          wup(jl) = sqrt(2.*wup(jl))
        end if
      end do

      return
      end subroutine cuascn



      subroutine cudlfsn   &
     &    (klon,     klev,                              &
     &     kcbot,    kctop,    lndj,   ldcum,           &
     &     ptenh,    pqenh,    puen,     pven,          &
     &     pten,     pqsen,    pgeo,                    &
     &     pgeoh,    paph,     ptu,      pqu,      plu, &
     &     puu,      pvu,      pmfub,    prfl,          &
     &     ptd,      pqd,      pud,      pvd,           &
     &     pmfd,     pmfds,    pmfdq,    pdmfdp,        &
     &     kdtop,    lddraf)



















































































      implicit none


      integer,intent(in):: klon
      logical,intent(in),dimension(klon):: ldcum

      integer,intent(in):: klev
      integer,intent(in),dimension(klon):: lndj
      integer,intent(in),dimension(klon):: kcbot,kctop

      real(kind=kind_phys),intent(in),dimension(klon):: pmfub
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pten,pqsen,pgeo,puen,pven
      real(kind=kind_phys),intent(in),dimension(klon,klev):: ptenh,pqenh
      real(kind=kind_phys),intent(in),dimension(klon,klev):: ptu,pqu,puu,pvu,plu
      real(kind=kind_phys),intent(in),dimension(klon,klev+1):: pgeoh,paph


      real(kind=kind_phys),intent(inout),dimension(klon):: prfl
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pud,pvd


      logical,intent(out),dimension(klon):: lddraf
      integer,intent(out),dimension(klon):: kdtop

      real(kind=kind_phys),intent(out),dimension(klon,klev):: ptd,pqd,pmfd,pmfds,pmfdq,pdmfdp


      logical,dimension(klon):: llo2
      integer:: jl,jk
      integer:: is,ik,icall,ike
      integer,dimension(klon):: ikhsmin

      real(kind=kind_phys):: zhsk,zttest,zqtest,zbuo,zmftop
      real(kind=kind_phys),dimension(klon):: zcond,zph,zhsmin
      real(kind=kind_phys),dimension(klon,klev):: ztenwb,zqenwb





      do jl=1,klon
        lddraf(jl)=.false.
        kdtop(jl)=klev+1
        ikhsmin(jl)=klev+1
        zhsmin(jl)=1.e8
      enddo





















      do jk=3,klev-2
         do jl=1,klon
           zhsk=cpd*pten(jl,jk)+pgeo(jl,jk) +  &
     &         foelhm(pten(jl,jk))*pqsen(jl,jk)
           if(zhsk .lt. zhsmin(jl)) then
              zhsmin(jl) = zhsk
              ikhsmin(jl)= jk
           end if
         end do
      end do


      ike=klev-3
      do jk=3,ike




        is=0
        do jl=1,klon
          ztenwb(jl,jk)=ptenh(jl,jk)
          zqenwb(jl,jk)=pqenh(jl,jk)
          zph(jl)=paph(jl,jk)
          llo2(jl)=ldcum(jl).and.prfl(jl).gt.0..and..not.lddraf(jl).and.   &
     &     (jk.lt.kcbot(jl).and.jk.gt.kctop(jl)).and. jk.ge.ikhsmin(jl)
          if(llo2(jl))then
            is=is+1
          endif
        enddo
        if(is.eq.0) cycle

        ik=jk
        icall=2
        call cuadjtqn                                           &
     &   ( klon, klev, ik, zph, ztenwb, zqenwb, llo2, icall)





        do jl=1,klon
          if(llo2(jl)) then
            zttest=0.5*(ptu(jl,jk)+ztenwb(jl,jk))
            zqtest=0.5*(pqu(jl,jk)+zqenwb(jl,jk))
            zbuo=zttest*(1.+vtmpc1  *zqtest)-                    &
     &       ptenh(jl,jk)*(1.+vtmpc1  *pqenh(jl,jk))
            zcond(jl)=pqenh(jl,jk)-zqenwb(jl,jk)
            zmftop=-cmfdeps*pmfub(jl)
            if(zbuo.lt.0..and.prfl(jl).gt.10.*zmftop*zcond(jl)) then
              kdtop(jl)=jk
              lddraf(jl)=.true.
              ptd(jl,jk)=zttest
              pqd(jl,jk)=zqtest
              pmfd(jl,jk)=zmftop
              pmfds(jl,jk)=pmfd(jl,jk)*(cpd*ptd(jl,jk)+pgeoh(jl,jk))
              pmfdq(jl,jk)=pmfd(jl,jk)*pqd(jl,jk)
              pdmfdp(jl,jk-1)=-0.5*pmfd(jl,jk)*zcond(jl)
              prfl(jl)=prfl(jl)+pdmfdp(jl,jk-1)
            endif
          endif
        enddo

      enddo

      return
      end subroutine cudlfsn







       subroutine cuddrafn                               &
     &   ( klon,     klev,    lddraf                     &
     &   , ptenh,    pqenh,    puen,     pven            &
     &   , pgeo,     pgeoh,    paph,     prfl            &
     &   , ptd,      pqd,      pud,      pvd,      pmfu  &
     &   , pmfd,     pmfds,    pmfdq,    pdmfdp,   pmfdde_rate )

































































      implicit none


      integer,intent(in)::klon
      logical,intent(in),dimension(klon):: lddraf

      integer,intent(in)::klev

      real(kind=kind_phys),intent(in),dimension(klon,klev):: ptenh,pqenh,puen,pven
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pgeo,pmfu
      real(kind=kind_phys),intent(in),dimension(klon,klev+1):: pgeoh,paph


      real(kind=kind_phys),intent(inout),dimension(klon):: prfl
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: ptd,pqd,pud,pvd
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pmfd,pmfds,pmfdq,pdmfdp


      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pmfdde_rate


      logical:: llo1
      logical,dimension(klon):: llo2

      integer::  jl,jk
      integer::  is,ik,icall,ike
      integer,dimension(klon):: itopde

      real(kind=kind_phys):: zentr,zdz,zzentr,zseen,zqeen,zsdde,zqdde,zdmfdp
      real(kind=kind_phys):: zmfdsk,zmfdqk,zbuo,zrain,zbuoyz,zmfduk,zmfdvk
      real(kind=kind_phys),dimension(klon):: zdmfen,zdmfde,zcond,zoentr,zbuoy,zph












      do jl=1,klon
        zoentr(jl)=0.
        zbuoy(jl)=0.
        zdmfen(jl)=0.
        zdmfde(jl)=0.
      enddo

      do jk=klev,1,-1
       do jl=1,klon
         pmfdde_rate(jl,jk) = 0.
         if((paph(jl,klev+1)-paph(jl,jk)).lt. 60.e2) itopde(jl) = jk
       end do
      end do

      do jk=3,klev
        is=0
        do jl=1,klon
          zph(jl)=paph(jl,jk)
          llo2(jl)=lddraf(jl).and.pmfd(jl,jk-1).lt.0.
          if(llo2(jl)) then
            is=is+1
          endif
        enddo
        if(is.eq.0) cycle

        do jl=1,klon
          if(llo2(jl)) then
            zentr = entrdd*pmfd(jl,jk-1)*(pgeoh(jl,jk-1)-pgeoh(jl,jk))*zrg
            zdmfen(jl)=zentr
            zdmfde(jl)=zentr
          endif
        enddo
 
        do jl=1,klon
          if(llo2(jl)) then
          if(jk.gt.itopde(jl)) then
            zdmfen(jl)=0.
            zdmfde(jl)=pmfd(jl,itopde(jl))*                    &
     &       (paph(jl,jk)-paph(jl,jk-1))/                  &
     &       (paph(jl,klev+1)-paph(jl,itopde(jl)))
          endif
          endif
        enddo

        do jl=1,klon
          if(llo2(jl)) then
          if(jk.le.itopde(jl)) then
            zdz=-(pgeoh(jl,jk-1)-pgeoh(jl,jk))*zrg
            zzentr=zoentr(jl)*zdz*pmfd(jl,jk-1)
            zdmfen(jl)=zdmfen(jl)+zzentr
            zdmfen(jl)=max(zdmfen(jl),0.3*pmfd(jl,jk-1))
            zdmfen(jl)=max(zdmfen(jl),-0.75*pmfu(jl,jk)-   &
   &         (pmfd(jl,jk-1)-zdmfde(jl)))
            zdmfen(jl)=min(zdmfen(jl),0.)
          endif
          endif
        enddo

        do jl=1,klon
          if(llo2(jl)) then
            pmfd(jl,jk)=pmfd(jl,jk-1)+zdmfen(jl)-zdmfde(jl)
            zseen=(cpd*ptenh(jl,jk-1)+pgeoh(jl,jk-1))*zdmfen(jl)
            zqeen=pqenh(jl,jk-1)*zdmfen(jl)
            zsdde=(cpd*ptd(jl,jk-1)+pgeoh(jl,jk-1))*zdmfde(jl)
            zqdde=pqd(jl,jk-1)*zdmfde(jl)
            zmfdsk=pmfds(jl,jk-1)+zseen-zsdde
            zmfdqk=pmfdq(jl,jk-1)+zqeen-zqdde
            pqd(jl,jk)=zmfdqk*(1./min(-cmfcmin,pmfd(jl,jk)))
            ptd(jl,jk)=(zmfdsk*(1./min(-cmfcmin,pmfd(jl,jk)))-&
     &                  pgeoh(jl,jk))*rcpd
            ptd(jl,jk)=min(400.,ptd(jl,jk))
            ptd(jl,jk)=max(100.,ptd(jl,jk))
            zcond(jl)=pqd(jl,jk)
          endif
        enddo

        ik=jk
        icall=2
        call cuadjtqn(klon, klev, ik, zph, ptd, pqd, llo2, icall )
                                                                          
        do jl=1,klon
          if(llo2(jl)) then
            zcond(jl)=zcond(jl)-pqd(jl,jk)
            zbuo=ptd(jl,jk)*(1.+vtmpc1  *pqd(jl,jk))-          &
     &      ptenh(jl,jk)*(1.+vtmpc1  *pqenh(jl,jk))
            if(prfl(jl).gt.0..and.pmfu(jl,jk).gt.0.) then
              zrain=prfl(jl)/pmfu(jl,jk)
              zbuo=zbuo-ptd(jl,jk)*zrain
            endif
            if(zbuo.ge.0 .or. prfl(jl).le.(pmfd(jl,jk)*zcond(jl))) then
              pmfd(jl,jk)=0.
              zbuo=0.
            endif
            pmfds(jl,jk)=(cpd*ptd(jl,jk)+pgeoh(jl,jk))*pmfd(jl,jk)
            pmfdq(jl,jk)=pqd(jl,jk)*pmfd(jl,jk)
            zdmfdp=-pmfd(jl,jk)*zcond(jl)
            pdmfdp(jl,jk-1)=zdmfdp
            prfl(jl)=prfl(jl)+zdmfdp


            zbuoyz=zbuo/ptenh(jl,jk)
            zbuoyz=min(zbuoyz,0.0)
            zdz=-(pgeo(jl,jk-1)-pgeo(jl,jk))
            zbuoy(jl)=zbuoy(jl)+zbuoyz*zdz
            zoentr(jl)=g*zbuoyz*0.5/(1.+zbuoy(jl))
            pmfdde_rate(jl,jk) = -zdmfde(jl)
          endif
        enddo

      enddo

      return
      end subroutine cuddrafn



       subroutine cuflxn &
     &  (  klon,     klev,     ztmst &                                                             
     &  ,  pten,     pqen,     pqsen,    ptenh,    pqenh &
     &  ,  paph,     pap,      pgeoh,    lndj,   ldcum   &
     &  ,  kcbot,    kctop,    kdtop,    ktopm2          &
     &  ,  ktype,    lddraf                              &
     &  ,  pmfu,     pmfd,     pmfus,    pmfds           &
     &  ,  pmfuq,    pmfdq,    pmful,    plude           &
     &  ,  pdmfup,   pdmfdp,   pdpmel,   plglac          &
     &  ,  prain,    pmfdde_rate, pmflxr, pmflxs )                                         
                                                                               

                                                                               


                                                                               


                                                                               



                                                                               
                                                                               



                                                                               





                                                                               

                                                                               


                                                                               

                                                                               









                                                                               

                                                                               

                                                                               

                                                                               

                                                                               

                                                                               










                                                                               

                                                                               






                                                                               




      implicit none


      integer,intent(in):: klon
      logical,intent(in),dimension(klon):: ldcum

      integer,intent(in):: klev
      integer,intent(in),dimension(klon):: lndj
      integer,intent(in),dimension(klon):: kcbot,kctop,kdtop

      real(kind=kind_phys),intent(in):: ztmst
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pten,ptenh,pqen,pqenh
      real(kind=kind_phys),intent(in),dimension(klon,klev):: pap
      real(kind=kind_phys),intent(in),dimension(klon,klev+1):: paph,pgeoh


      logical,intent(inout),dimension(klon):: lddraf

      integer,intent(inout):: ktopm2
      integer,intent(inout),dimension(klon):: ktype

      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pmfu,pmfd,pmfus,pmfds
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pmfuq,pmfdq,pmful,plude
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pdmfup,pdmfdp
      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pqsen


      real(kind=kind_phys),dimension(klon):: prain
      real(kind=kind_phys),dimension(klon,klev):: pdpmel,plglac
      real(kind=kind_phys),dimension(klon,klev):: pmfdde_rate
      real(kind=kind_phys),dimension(klon,klev+1):: pmflxr,pmflxs


      logical:: llddraf

      integer:: jl,jk
      integer:: is,ik,icall,ike,ikb
      integer,dimension(klon):: idbas

      real(kind=kind_phys):: ztaumel,zcons1a,zcons1,zcons2,zcucov,zcpecons
      real(kind=kind_phys):: zalfaw,zrfl,zdrfl1,zrnew,zrmin,zrfln,zdrfl,zdenom
      real(kind=kind_phys):: zpdr,zpds,zzp,zfac,zsnmlt
      real(kind=kind_phys),dimension(klon):: rhevap




      ztaumel=18000.
      zcons1a=cpd/(alf*g*ztaumel)
      zcons2=3./(g*ztmst)
      zcucov=0.05
      zcpecons=5.44e-4/g



      do jl=1,klon
        prain(jl)=0.
        if(.not.ldcum(jl).or.kdtop(jl).lt.kctop(jl)) lddraf(jl)=.false.
        if(.not.ldcum(jl)) ktype(jl)=0
        idbas(jl) = klev
        if(lndj(jl) .eq. 1) then
          rhevap(jl) = 0.7
        else
          rhevap(jl) = 0.9
        end if
      enddo

      ktopm2= 2
      do jk=ktopm2,klev
        ikb = min(jk+1,klev)
        do jl=1,klon
          pmflxr(jl,jk) = 0.
          pmflxs(jl,jk) = 0.
          pdpmel(jl,jk) = 0.
          if(ldcum(jl).and.jk.ge.kctop(jl)) then
            pmfus(jl,jk)=pmfus(jl,jk)-pmfu(jl,jk)*           &
     &       (cpd*ptenh(jl,jk)+pgeoh(jl,jk))
            pmfuq(jl,jk)=pmfuq(jl,jk)-pmfu(jl,jk)*pqenh(jl,jk)
            plglac(jl,jk)=pmfu(jl,jk)*plglac(jl,jk)
            llddraf = lddraf(jl) .and. jk >= kdtop(jl)
            if ( llddraf .and.jk.ge.kdtop(jl)) then
              pmfds(jl,jk) = pmfds(jl,jk)-pmfd(jl,jk) * &
                           (cpd*ptenh(jl,jk)+pgeoh(jl,jk))
              pmfdq(jl,jk) = pmfdq(jl,jk)-pmfd(jl,jk)*pqenh(jl,jk)
            else
              pmfd(jl,jk) = 0.
              pmfds(jl,jk) = 0.
              pmfdq(jl,jk) = 0.
              pdmfdp(jl,jk-1) = 0.
            end if
            if ( llddraf .and. pmfd(jl,jk) < 0. .and. &
               abs(pmfd(jl,ikb)) < 1.e-20 ) then
               idbas(jl) = jk
            end if
          else
            pmfu(jl,jk)=0.
            pmfd(jl,jk)=0.
            pmfus(jl,jk)=0.
            pmfds(jl,jk)=0.
            pmfuq(jl,jk)=0.
            pmfdq(jl,jk)=0.
            pmful(jl,jk)=0.
            plglac(jl,jk)=0.
            pdmfup(jl,jk-1)=0.
            pdmfdp(jl,jk-1)=0.
            plude(jl,jk-1)=0.
          endif
        enddo
      enddo

      do jl=1,klon
        pmflxr(jl,klev+1) = 0.
        pmflxs(jl,klev+1) = 0.
      end do
      do jl=1,klon
        if(ldcum(jl)) then
          ikb=kcbot(jl)
          ik=ikb+1
          zzp=((paph(jl,klev+1)-paph(jl,ik))/                  &
     &     (paph(jl,klev+1)-paph(jl,ikb)))
          if(ktype(jl).eq.3) then
            zzp=zzp**2
          endif
          pmfu(jl,ik)=pmfu(jl,ikb)*zzp
          pmfus(jl,ik)=(pmfus(jl,ikb)-                         &
     &         foelhm(ptenh(jl,ikb))*pmful(jl,ikb))*zzp
          pmfuq(jl,ik)=(pmfuq(jl,ikb)+pmful(jl,ikb))*zzp
          pmful(jl,ik)=0.
        endif
      enddo

      do jk=ktopm2,klev
        do jl=1,klon
          if(ldcum(jl).and.jk.gt.kcbot(jl)+1) then
            ikb=kcbot(jl)+1
            zzp=((paph(jl,klev+1)-paph(jl,jk))/                &
     &       (paph(jl,klev+1)-paph(jl,ikb)))
            if(ktype(jl).eq.3) then
              zzp=zzp**2
            endif
            pmfu(jl,jk)=pmfu(jl,ikb)*zzp
            pmfus(jl,jk)=pmfus(jl,ikb)*zzp
            pmfuq(jl,jk)=pmfuq(jl,ikb)*zzp
            pmful(jl,jk)=0.
          endif
          ik = idbas(jl)
          llddraf = lddraf(jl) .and. jk > ik .and. ik < klev
          if ( llddraf .and. ik == kcbot(jl)+1 ) then
           zzp = ((paph(jl,klev+1)-paph(jl,jk))/(paph(jl,klev+1)-paph(jl,ik)))
           if ( ktype(jl) == 3 ) zzp = zzp*zzp
            pmfd(jl,jk) = pmfd(jl,ik)*zzp
            pmfds(jl,jk) = pmfds(jl,ik)*zzp
            pmfdq(jl,jk) = pmfdq(jl,ik)*zzp
            pmfdde_rate(jl,jk) = -(pmfd(jl,jk-1)-pmfd(jl,jk))
           else if ( llddraf .and. ik /= kcbot(jl)+1 .and. jk == ik+1 ) then
            pmfdde_rate(jl,jk) = -(pmfd(jl,jk-1)-pmfd(jl,jk))
           end if
        enddo
      enddo





        do jk=ktopm2,klev
        do jl=1,klon
          if(ldcum(jl) .and. jk >=kctop(jl)-1 ) then
            prain(jl)=prain(jl)+pdmfup(jl,jk)
            if(pmflxs(jl,jk).gt.0..and.pten(jl,jk).gt.tmelt) then
              zcons1=zcons1a*(1.+0.5*(pten(jl,jk)-tmelt))
              zfac=zcons1*(paph(jl,jk+1)-paph(jl,jk))
              zsnmlt=min(pmflxs(jl,jk),zfac*(pten(jl,jk)-tmelt))
              pdpmel(jl,jk)=zsnmlt
              pqsen(jl,jk)=foeewm(pten(jl,jk)-zsnmlt/zfac)/pap(jl,jk)
            endif
            zalfaw=foealfa(pten(jl,jk))
          
          
          
            if ( pten(jl,jk) < tmelt .and. zalfaw > 0. ) then
              plglac(jl,jk) = plglac(jl,jk)+zalfaw*(pdmfup(jl,jk)+pdmfdp(jl,jk))
              zalfaw = 0.
            end if
            pmflxr(jl,jk+1)=pmflxr(jl,jk)+zalfaw*               &
     &       (pdmfup(jl,jk)+pdmfdp(jl,jk))+pdpmel(jl,jk)
            pmflxs(jl,jk+1)=pmflxs(jl,jk)+(1.-zalfaw)*          &
     &       (pdmfup(jl,jk)+pdmfdp(jl,jk))-pdpmel(jl,jk)
            if(pmflxr(jl,jk+1)+pmflxs(jl,jk+1).lt.0.0) then
              pdmfdp(jl,jk)=-(pmflxr(jl,jk)+pmflxs(jl,jk)+pdmfup(jl,jk))
              pmflxr(jl,jk+1)=0.0
              pmflxs(jl,jk+1)=0.0
              pdpmel(jl,jk)  =0.0
            else if ( pmflxr(jl,jk+1) < 0. ) then
              pmflxs(jl,jk+1) = pmflxs(jl,jk+1)+pmflxr(jl,jk+1)
              pmflxr(jl,jk+1) = 0.
            else if ( pmflxs(jl,jk+1) < 0. ) then
              pmflxr(jl,jk+1) = pmflxr(jl,jk+1)+pmflxs(jl,jk+1)
              pmflxs(jl,jk+1) = 0.
            end if
          endif
        enddo
      enddo
      do jk=ktopm2,klev
        do jl=1,klon
          if(ldcum(jl).and.jk.ge.kcbot(jl)) then
            zrfl=pmflxr(jl,jk)+pmflxs(jl,jk)
            if(zrfl.gt.1.e-20) then
              zdrfl1=zcpecons*max(0.,pqsen(jl,jk)-pqen(jl,jk))*zcucov* &
     &         (sqrt(paph(jl,jk)/paph(jl,klev+1))/5.09e-3*             &
     &         zrfl/zcucov)**0.5777*                                   &
     &         (paph(jl,jk+1)-paph(jl,jk))
              zrnew=zrfl-zdrfl1
              zrmin=zrfl-zcucov*max(0.,rhevap(jl)*pqsen(jl,jk) &
     &              -pqen(jl,jk)) *zcons2*(paph(jl,jk+1)-paph(jl,jk))
              zrnew=max(zrnew,zrmin)
              zrfln=max(zrnew,0.)
              zdrfl=min(0.,zrfln-zrfl)
              zdenom=1./max(1.e-20,pmflxr(jl,jk)+pmflxs(jl,jk))
              zalfaw=foealfa(pten(jl,jk))
              if ( pten(jl,jk) < tmelt ) zalfaw = 0.
              zpdr=zalfaw*pdmfdp(jl,jk)
              zpds=(1.-zalfaw)*pdmfdp(jl,jk)
              pmflxr(jl,jk+1)=pmflxr(jl,jk)+zpdr         &
     &         +pdpmel(jl,jk)+zdrfl*pmflxr(jl,jk)*zdenom
              pmflxs(jl,jk+1)=pmflxs(jl,jk)+zpds         &
     &         -pdpmel(jl,jk)+zdrfl*pmflxs(jl,jk)*zdenom
              pdmfup(jl,jk)=pdmfup(jl,jk)+zdrfl
              if ( pmflxr(jl,jk+1)+pmflxs(jl,jk+1) < 0. ) then
                pdmfup(jl,jk) = pdmfup(jl,jk)-(pmflxr(jl,jk+1)+pmflxs(jl,jk+1))
                pmflxr(jl,jk+1) = 0.
                pmflxs(jl,jk+1) = 0.
                pdpmel(jl,jk)   = 0.
              else if ( pmflxr(jl,jk+1) < 0. ) then
                pmflxs(jl,jk+1) = pmflxs(jl,jk+1)+pmflxr(jl,jk+1)
                pmflxr(jl,jk+1) = 0.
              else if ( pmflxs(jl,jk+1) < 0. ) then
                pmflxr(jl,jk+1) = pmflxr(jl,jk+1)+pmflxs(jl,jk+1)
                pmflxs(jl,jk+1) = 0.
              end if
            else
              pmflxr(jl,jk+1)=0.0
              pmflxs(jl,jk+1)=0.0
              pdmfdp(jl,jk)=0.0
              pdpmel(jl,jk)=0.0
            endif
          endif
        enddo
      enddo
                                      
      return
      end subroutine cuflxn 



     subroutine cudtdqn(klon,klev,ktopm2,kctop,kdtop,ldcum,          &
                     lddraf,ztmst,paph,pgeoh,pgeo,pten,ptenh,pqen,   &
                     pqenh,pqsen,plglac,plude,pmfu,pmfd,pmfus,pmfds, &
                     pmfuq,pmfdq,pmful,pdmfup,pdmfdp,pdpmel,ptent,ptenq,pcte)
    implicit none


    integer,intent(in):: klon
    logical,intent(in),dimension(klon):: ldcum,lddraf

    integer,intent(in):: klev,ktopm2
    integer,intent(in),dimension(klon):: kctop,kdtop

    real(kind=kind_phys),intent(in):: ztmst
    real(kind=kind_phys),intent(in),dimension(klon,klev):: pgeo
    real(kind=kind_phys),intent(in),dimension(klon,klev):: pten
    real(kind=kind_phys),intent(in),dimension(klon,klev):: pmfu,pmfus,pmfd,pmfds
    real(kind=kind_phys),intent(in),dimension(klon,klev):: pmfuq,pmfdq,pmful
    real(kind=kind_phys),intent(in),dimension(klon,klev):: plglac,plude,pdpmel
    real(kind=kind_phys),intent(in),dimension(klon,klev):: pdmfup,pdmfdp
    real(kind=kind_phys),intent(in),dimension(klon,klev):: pqen, ptenh,pqenh,pqsen
    real(kind=kind_phys),intent(in),dimension(klon,klev+1):: paph,pgeoh


    real(kind=kind_phys),intent(inout),dimension(klon,klev):: ptent,ptenq,pcte


    integer::  jk ,ik ,jl
    real(kind=kind_phys):: zalv ,zzp
    real(kind=kind_phys),dimension(klon,klev):: zdtdt,zdqdt,zdp

    
    
    do jk = 1 , klev
      do jl = 1, klon
        if ( ldcum(jl) ) then
          zdp(jl,jk) = g/(paph(jl,jk+1)-paph(jl,jk))
        end if
      end do
    end do
    
    
    
    do jk = ktopm2 , klev
      if ( jk < klev ) then
        do jl = 1,klon
          if ( ldcum(jl) ) then
            zalv = foelhm(pten(jl,jk))
            zdtdt(jl,jk) = zdp(jl,jk)*rcpd * &
              (pmfus(jl,jk+1)-pmfus(jl,jk)+pmfds(jl,jk+1) - &
               pmfds(jl,jk)+alf*plglac(jl,jk)-alf*pdpmel(jl,jk) - &
               zalv*(pmful(jl,jk+1)-pmful(jl,jk)-plude(jl,jk)-pdmfup(jl,jk)-pdmfdp(jl,jk)))
            zdqdt(jl,jk) = zdp(jl,jk)*(pmfuq(jl,jk+1) - &
              pmfuq(jl,jk)+pmfdq(jl,jk+1)-pmfdq(jl,jk)+pmful(jl,jk+1) - &
              pmful(jl,jk)-plude(jl,jk)-pdmfup(jl,jk)-pdmfdp(jl,jk))
          end if
        end do
      else
        do jl = 1,klon
          if ( ldcum(jl) ) then
            zalv = foelhm(pten(jl,jk))
            zdtdt(jl,jk) = -zdp(jl,jk)*rcpd * &
              (pmfus(jl,jk)+pmfds(jl,jk)+alf*pdpmel(jl,jk) - &
               zalv*(pmful(jl,jk)+pdmfup(jl,jk)+pdmfdp(jl,jk)+plude(jl,jk)))
            zdqdt(jl,jk) = -zdp(jl,jk)*(pmfuq(jl,jk) + plude(jl,jk) + &
              pmfdq(jl,jk)+(pmful(jl,jk)+pdmfup(jl,jk)+pdmfdp(jl,jk)))
          end if
        end do
      end if
    end do
  
  
  
    do jk = ktopm2 , klev
     do jl = 1, klon
       if ( ldcum(jl) ) then
         ptent(jl,jk) = ptent(jl,jk) + zdtdt(jl,jk)
         ptenq(jl,jk) = ptenq(jl,jk) + zdqdt(jl,jk)
         pcte(jl,jk)  = zdp(jl,jk)*plude(jl,jk)
       end if
     end do
    end do

    return
  end subroutine cudtdqn



    subroutine cududvn(klon,klev,ktopm2,ktype,kcbot,kctop,ldcum,  &
                    ztmst,paph,puen,pven,pmfu,pmfd,puu,pud,pvu,pvd,ptenu, &
                    ptenv)
    implicit none


    integer,intent(in):: klon
    logical,intent(in),dimension(klon):: ldcum
    integer,intent(in):: klev,ktopm2
    integer,intent(in),dimension(klon):: ktype,kcbot,kctop

    real(kind=kind_phys),intent(in):: ztmst
    real(kind=kind_phys),intent(in),dimension(klon,klev):: pmfu,pmfd,puen,pven
    real(kind=kind_phys),intent(in),dimension(klon,klev):: puu,pud,pvu,pvd
    real(kind=kind_phys),intent(in),dimension(klon,klev+1):: paph


    real(kind=kind_phys),intent(inout),dimension(klon,klev):: ptenu,ptenv


    integer:: ik,ikb,jk,jl

    real(kind=kind_phys):: zzp,zdtdt
    real(kind=kind_Phys),dimension(klon,klev):: zdudt,zdvdt,zdp
    real(kind=kind_phys),dimension(klon,klev):: zuen,zven,zmfuu,zmfdu,zmfuv,zmfdv


    do jk = 1 , klev
      do jl = 1, klon
        if ( ldcum(jl) ) then
          zuen(jl,jk) = puen(jl,jk)
          zven(jl,jk) = pven(jl,jk)
          zdp(jl,jk) = g/(paph(jl,jk+1)-paph(jl,jk))
        end if
      end do
    end do



    do jk = ktopm2 , klev
      ik = jk - 1
      do jl = 1,klon
        if ( ldcum(jl) ) then
          zmfuu(jl,jk) = pmfu(jl,jk)*(puu(jl,jk)-zuen(jl,ik))
          zmfuv(jl,jk) = pmfu(jl,jk)*(pvu(jl,jk)-zven(jl,ik))
          zmfdu(jl,jk) = pmfd(jl,jk)*(pud(jl,jk)-zuen(jl,ik))
          zmfdv(jl,jk) = pmfd(jl,jk)*(pvd(jl,jk)-zven(jl,ik))
        end if
      end do
    end do
    
      do jk = ktopm2 , klev
        do jl = 1, klon
          if ( ldcum(jl) .and. jk > kcbot(jl) ) then
            ikb = kcbot(jl)
            zzp = ((paph(jl,klev+1)-paph(jl,jk))/(paph(jl,klev+1)-paph(jl,ikb)))
            if ( ktype(jl) == 3 ) zzp = zzp*zzp
            zmfuu(jl,jk) = zmfuu(jl,ikb)*zzp
            zmfuv(jl,jk) = zmfuv(jl,ikb)*zzp
            zmfdu(jl,jk) = zmfdu(jl,ikb)*zzp
            zmfdv(jl,jk) = zmfdv(jl,ikb)*zzp
          end if
        end do
      end do



    do jk = ktopm2 , klev
      if ( jk < klev ) then
        ik = jk + 1
        do jl = 1,klon
          if ( ldcum(jl) ) then
            zdudt(jl,jk) = zdp(jl,jk) * &
                          (zmfuu(jl,ik)-zmfuu(jl,jk)+zmfdu(jl,ik)-zmfdu(jl,jk))
            zdvdt(jl,jk) = zdp(jl,jk) * &
                          (zmfuv(jl,ik)-zmfuv(jl,jk)+zmfdv(jl,ik)-zmfdv(jl,jk))
          end if
        end do
      else
        do jl = 1,klon
          if ( ldcum(jl) ) then
            zdudt(jl,jk) = -zdp(jl,jk)*(zmfuu(jl,jk)+zmfdu(jl,jk))
            zdvdt(jl,jk) = -zdp(jl,jk)*(zmfuv(jl,jk)+zmfdv(jl,jk))
          end if
        end do
      end if
    end do



    do jk = ktopm2 , klev
      do jl = 1, klon
        if ( ldcum(jl) ) then
          ptenu(jl,jk) = ptenu(jl,jk) + zdudt(jl,jk)
          ptenv(jl,jk) = ptenv(jl,jk) + zdvdt(jl,jk)
        end if
      end do
    end do

    return
    end subroutine cududvn



      subroutine cuadjtqn &
     &    (klon, klev, kk, psp, pt, pq, ldflag,  kcall)








































                                                                                    
      implicit none   
                 

      integer,intent(in):: klon
      logical,intent(in),dimension(klon):: ldflag
      integer,intent(in):: kcall,kk,klev

      real(kind=kind_phys),intent(in),dimension(klon):: psp


      real(kind=kind_phys),intent(inout),dimension(klon,klev):: pt,pq


      integer:: jl,jk
      integer:: isum

      real(kind=kind_phys)::zqmax,zqsat,zcor,zqp,zcond,zcond1,zl,zi,zf




      zqmax=0.5




      if ( kcall == 1 ) then
      do jl = 1,klon
        if ( ldflag(jl) ) then
          zqp = 1./psp(jl)
          zl = 1./(pt(jl,kk)-c4les)
          zi = 1./(pt(jl,kk)-c4ies)
          zqsat = c2es*(foealfa(pt(jl,kk))*exp(c3les*(pt(jl,kk)-tmelt)*zl) + &
                (1.-foealfa(pt(jl,kk)))*exp(c3ies*(pt(jl,kk)-tmelt)*zi))
          zqsat = zqsat*zqp
          zqsat = min(0.5,zqsat)
          zcor = 1. - vtmpc1*zqsat
          zf = foealfa(pt(jl,kk))*r5alvcp*zl**2 + &
               (1.-foealfa(pt(jl,kk)))*r5alscp*zi**2
          zcond = (pq(jl,kk)*zcor**2-zqsat*zcor)/(zcor**2+zqsat*zf)
          if ( zcond > 0. ) then
            pt(jl,kk) = pt(jl,kk) + foeldcpm(pt(jl,kk))*zcond
            pq(jl,kk) = pq(jl,kk) - zcond
            zl = 1./(pt(jl,kk)-c4les)
            zi = 1./(pt(jl,kk)-c4ies)
            zqsat = c2es*(foealfa(pt(jl,kk)) * &
              exp(c3les*(pt(jl,kk)-tmelt)*zl)+(1.-foealfa(pt(jl,kk))) * &
              exp(c3ies*(pt(jl,kk)-tmelt)*zi))
            zqsat = zqsat*zqp
            zqsat = min(0.5,zqsat)
            zcor = 1. - vtmpc1*zqsat
            zf = foealfa(pt(jl,kk))*r5alvcp*zl**2 + &
                 (1.-foealfa(pt(jl,kk)))*r5alscp*zi**2
            zcond1 = (pq(jl,kk)*zcor**2-zqsat*zcor)/(zcor**2+zqsat*zf)
            if ( abs(zcond) < 1.e-20 ) zcond1 = 0.
            pt(jl,kk) = pt(jl,kk) + foeldcpm(pt(jl,kk))*zcond1
            pq(jl,kk) = pq(jl,kk) - zcond1
          end if
        end if
      end do
      elseif ( kcall == 2 ) then
      do jl = 1,klon
        if ( ldflag(jl) ) then
          zqp = 1./psp(jl)
          zqsat = foeewm(pt(jl,kk))*zqp
          zqsat = min(0.5,zqsat)
          zcor = 1./(1.-vtmpc1*zqsat)
          zqsat = zqsat*zcor
          zcond = (pq(jl,kk)-zqsat)/(1.+zqsat*zcor*foedem(pt(jl,kk)))
          zcond = min(zcond,0.)
          pt(jl,kk) = pt(jl,kk) + foeldcpm(pt(jl,kk))*zcond
          pq(jl,kk) = pq(jl,kk) - zcond
          zqsat = foeewm(pt(jl,kk))*zqp
          zqsat = min(0.5,zqsat)
          zcor = 1./(1.-vtmpc1*zqsat)
          zqsat = zqsat*zcor
          zcond1 = (pq(jl,kk)-zqsat)/(1.+zqsat*zcor*foedem(pt(jl,kk)))
          if ( abs(zcond) < 1.e-20 ) zcond1 = min(zcond1,0.)
          pt(jl,kk) = pt(jl,kk) + foeldcpm(pt(jl,kk))*zcond1
          pq(jl,kk) = pq(jl,kk) - zcond1
        end if
      end do
      else if ( kcall == 0 ) then
      do jl = 1,klon
        zqp = 1./psp(jl)
        zqsat = foeewm(pt(jl,kk))*zqp
        zqsat = min(0.5,zqsat)
        zcor = 1./(1.-vtmpc1*zqsat)
        zqsat = zqsat*zcor
        zcond1 = (pq(jl,kk)-zqsat)/(1.+zqsat*zcor*foedem(pt(jl,kk)))
        pt(jl,kk) = pt(jl,kk) + foeldcpm(pt(jl,kk))*zcond1
        pq(jl,kk) = pq(jl,kk) - zcond1
        zqsat = foeewm(pt(jl,kk))*zqp
        zqsat = min(0.5,zqsat)
        zcor = 1./(1.-vtmpc1*zqsat)
        zqsat = zqsat*zcor
        zcond1 = (pq(jl,kk)-zqsat)/(1.+zqsat*zcor*foedem(pt(jl,kk)))
        pt(jl,kk) = pt(jl,kk) + foeldcpm(pt(jl,kk))*zcond1
        pq(jl,kk) = pq(jl,kk) - zcond1
      end do
      end if

      return
      end subroutine cuadjtqn



      subroutine cubasmcn &
     &    (klon,     klev,     klevm1,  kk,     pten,          &
     &     pqen,     pqsen,    puen,    pven,   pverv,         &
     &     pgeo,     pgeoh,    ldcum,   ktype,  klab,  plrain, &
     &     pmfu,     pmfub,    kcbot,   ptu,                   &
     &     pqu,      plu,      puu,     pvu,    pmfus,         &
     &     pmfuq,    pmful,    pdmfup)
      implicit none




















      integer,intent(in):: klon
      logical,intent(in),dimension(klon):: ldcum
      integer,intent(in):: kk,klev,klevm1

      real(kind=kind_phys),intent(in),dimension(klon,klev):: pten,pqen,pqsen,pgeo,pverv
      real(kind=kind_phys),intent(in),dimension(klon,klev):: puen,pven 
      real(kind=kind_phys),intent(in),dimension(klon,klev):: puu,pvu   
      real(kind=kind_phys),intent(in),dimension(klon,klev+1):: pgeoh


      integer,intent(out),dimension(klon):: ktype,kcbot
      integer,intent(out),dimension(klon,klev):: klab

      real(kind=kind_phys),intent(out),dimension(klon):: pmfub
      real(kind=kind_phys),intent(out),dimension(klon,klev):: plrain
      real(kind=kind_phys),intent(out),dimension(klon,klev):: ptu,pqu,plu
      real(kind=kind_phys),intent(out),dimension(klon,klev):: pmfu,pmfus,pmfuq,pmful
      real(kind=kind_phys),intent(out),dimension(klon,klev):: pdmfup


      integer:: jl,klevp1
      real(kind=kind_phys):: zzzmb




         do jl=1,klon
          if(.not.ldcum(jl) .and. klab(jl,kk+1).eq.0) then
            if(lmfmid .and. pqen(jl,kk) .gt. 0.80*pqsen(jl,kk).and. &
              pgeo(jl,kk)*zrg .gt. 5.0e2  .and.  &
     &        pgeo(jl,kk)*zrg .lt. 1.0e4 )  then
            ptu(jl,kk+1)=(cpd*pten(jl,kk)+pgeo(jl,kk)-pgeoh(jl,kk+1))&
     &                          *rcpd
            pqu(jl,kk+1)=pqen(jl,kk)
            plu(jl,kk+1)=0.
            zzzmb=max(cmfcmin,-pverv(jl,kk)*zrg)
            zzzmb=min(zzzmb,cmfcmax)
            pmfub(jl)=zzzmb
            pmfu(jl,kk+1)=pmfub(jl)
            pmfus(jl,kk+1)=pmfub(jl)*(cpd*ptu(jl,kk+1)+pgeoh(jl,kk+1))
            pmfuq(jl,kk+1)=pmfub(jl)*pqu(jl,kk+1)
            pmful(jl,kk+1)=0.
            pdmfup(jl,kk+1)=0.
            kcbot(jl)=kk
            klab(jl,kk+1)=1
            plrain(jl,kk+1)=0.0
            ktype(jl)=3
          end if
         end if
        end do
      return
      end subroutine cubasmcn



      subroutine cuentrn(klon,klev,kk,kcbot,ldcum,ldwork, &
                    pgeoh,pmfu,pdmfen,pdmfde)
       implicit none


       logical,intent(in):: ldwork
       integer,intent(in):: klon
       logical,intent(in),dimension(klon):: ldcum

       integer,intent(in):: klev,kk
       integer,intent(in),dimension(klon):: kcbot

       real(kind=kind_phys),intent(in),dimension(klon,klev):: pmfu
       real(kind=kind_phys),intent(in),dimension(klon,klev+1):: pgeoh


       real(kind=kind_phys),intent(out),dimension(klon):: pdmfen
       real(kind=kind_phys),intent(out),dimension(klon):: pdmfde


       logical:: llo1
       integer:: jl
       real(kind=kind_phys):: zdz ,zmf
       real(kind=kind_phys),dimension(klon):: zentr

    
    
    
    if ( ldwork ) then
      do jl = 1,klon
        pdmfen(jl) = 0.
        pdmfde(jl) = 0.
        zentr(jl) = 0.
      end do
      
      
      
      do jl = 1, klon
        if ( ldcum(jl) ) then
          zdz = (pgeoh(jl,kk)-pgeoh(jl,kk+1))*zrg
          zmf = pmfu(jl,kk+1)*zdz
          llo1 = kk < kcbot(jl)
          if ( llo1 ) then
            pdmfen(jl) = zentr(jl)*zmf
            pdmfde(jl) = 0.75e-4*zmf
          end if
        end if
      end do
    end if
    end subroutine cuentrn



      real(kind=kind_phys) function foealfa(tt)








        implicit none
        real(kind=kind_phys),intent(in):: tt
         foealfa = min(1.,((max(rtice,min(rtwat,tt))-rtice) &
     &  /(rtwat-rtice))**2)

        return
      end function foealfa

      real(kind=kind_phys) function foelhm(tt)
        implicit none
        real(kind=kind_phys),intent(in):: tt
        foelhm = foealfa(tt)*alv + (1.-foealfa(tt))*als
      return
      end function foelhm

      real(kind=kind_phys) function foeewm(tt)
        implicit none
        real(kind=kind_phys),intent(in):: tt
        foeewm  = c2es * &
     &     (foealfa(tt)*exp(c3les*(tt-tmelt)/(tt-c4les))+ &
     &     (1.-foealfa(tt))*exp(c3ies*(tt-tmelt)/(tt-c4ies)))
      return
      end function foeewm

      real(kind=kind_phys) function foedem(tt)
        implicit none
        real(kind=kind_phys),intent(in):: tt
        foedem  = foealfa(tt)*r5alvcp*(1./(tt-c4les)**2)+ &
     &              (1.-foealfa(tt))*r5alscp*(1./(tt-c4ies)**2)
      return
      end function foedem

      real(kind=kind_phys) function foeldcpm(tt)
        implicit none
        real(kind=kind_phys),intent(in):: tt
        foeldcpm = foealfa(tt)*ralvdcp+ &
     &        (1.-foealfa(tt))*ralsdcp
      return
      end function  foeldcpm


 end module cu_ntiedtke


























