











































MODULE module_sf_ysl

 REAL    , PARAMETER ::  VCONVC=1.
 REAL    , PARAMETER ::  CZO=0.0185
 REAL    , PARAMETER ::  OZO=1.59E-5

 REAL,   DIMENSION(0:1000),SAVE :: psim_stab,psim_unstab,psih_stab,psih_unstab

CONTAINS


   SUBROUTINE YSL(U3D,V3D,T3D,QV3D,P3D,dz8w,                    &
                     CP,G,ROVCP,R,XLV,PSFC,CHS,CHS2,CQS2,CPM,      &
                     ZNT,UST,PBLH,MAVAIL,ZOL,MOL,REGIME,PSIM,PSIH, &
                     FM,FH,                                        &
                     XLAND,HFX,QFX,LH,TSK,FLHC,FLQC,QGH,QSFC,RMOL, &
                     U10,V10,TH2,T2,Q2,                            &
                     GZ1OZ0,WSPD,BR,ISFFLX,DX,                     &
                     SVP1,SVP2,SVP3,SVPT0,EP1,EP2,                 &
                     KARMAN,EOMEG,STBOLT,                          &
                     P1000mb,                                      &
                     itimestep,                                    & 
                     LAI, VEGTYP, MMINLU,                          & 
                     wspd_jun, ust_jun,                            & 
                     hc_jun, lai_jun, lc_jun,                      & 
                     beta_jun, zpd_jun,                            & 
                     CHS_ori,                                      & 
                     charnock,                                     & 
                     ids,ide, jds,jde, kds,kde,                    &
                     ims,ime, jms,jme, kms,kme,                    &
                     its,ite, jts,jte, kts,kte,                    &
                     ustm,ck,cka,cd,cda,isftcflx,iz0tlnd,scm_force_flux           )

      IMPLICIT NONE























































































      INTEGER,  INTENT(IN )   ::        ids,ide, jds,jde, kds,kde, &
                                        ims,ime, jms,jme, kms,kme, &
                                        its,ite, jts,jte, kts,kte

      INTEGER,  INTENT(IN )   ::        ISFFLX
      REAL,     INTENT(IN )   ::        SVP1,SVP2,SVP3,SVPT0
      REAL,     INTENT(IN )   ::        EP1,EP2,KARMAN,EOMEG,STBOLT
      REAL,     INTENT(IN )   ::        P1000mb

      REAL,     DIMENSION( ims:ime, kms:kme, jms:jme )           , &
                INTENT(IN   )   ::                           dz8w
                                        
      REAL,     DIMENSION( ims:ime, kms:kme, jms:jme )           , &
                INTENT(IN   )   ::                           QV3D, &
                                                              P3D, &
                                                              T3D

      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(IN   )               ::             MAVAIL, &
                                                             PBLH, &
                                                            XLAND, &
                                                              TSK
      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(OUT  )               ::                U10, &
                                                              V10, &
                                                              TH2, &
                                                               T2, &
                                                               Q2, &
                                                             QSFC


      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(INOUT)               ::             REGIME, &
                                                              HFX, &
                                                              QFX, &
                                                               LH, &
                                                          MOL,RMOL


      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(INOUT)   ::                 GZ1OZ0,WSPD,BR, &
                                                  PSIM,PSIH,FM,FH

      REAL,     DIMENSION( ims:ime, kms:kme, jms:jme )           , &
                INTENT(IN   )   ::                            U3D, &
                                                              V3D
                                        
      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(IN   )               ::               PSFC

      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(INOUT)   ::                            ZNT, &
                                                              ZOL, &
                                                              UST, &
                                                              CPM, &
                                                             CHS2, &
                                                             CQS2, &
                                                              CHS

      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(INOUT)   ::                      FLHC,FLQC

      REAL,     DIMENSION( ims:ime, jms:jme )                    , &
                INTENT(INOUT)   ::                                 &
                                                              QGH
                                    
      REAL,     INTENT(IN   )               ::   CP,G,ROVCP,R,XLV,DX
 
      REAL, OPTIONAL, DIMENSION( ims:ime, jms:jme )              , &
                INTENT(OUT)     ::                  ck,cka,cd,cda

      REAL, OPTIONAL, DIMENSION( ims:ime, jms:jme )              , &
                INTENT(INOUT)   ::                           USTM

      INTEGER,  OPTIONAL,  INTENT(IN )   ::     ISFTCFLX, IZ0TLND
      INTEGER,  OPTIONAL,  INTENT(IN )   ::     SCM_FORCE_FLUX


      REAL,     DIMENSION( its:ite ) ::                       U1D, &
                                                              V1D, &
                                                             QV1D, &
                                                              P1D, &
                                                              T1D

      REAL,     DIMENSION( its:ite ) ::                    dz8w1d

      INTEGER ::  I,J
      REAL,DIMENSION(ims:ime, jms:jme),INTENT(INOUT) :: wspd_jun, ust_jun
      REAL,DIMENSION(ims:ime, jms:jme),INTENT(INOUT) :: hc_jun, lai_jun, lc_jun,  beta_jun, zpd_jun, CHS_ori
      REAL,DIMENSION(ims:ime, jms:jme),INTENT(IN) :: LAI
      REAL,DIMENSION(ims:ime, jms:jme),INTENT(IN) :: charnock 
      INTEGER,DIMENSION(ims:ime, jms:jme),INTENT(IN) :: VEGTYP
      CHARACTER(LEN=*),INTENT(IN) :: MMINLU
      INTEGER,INTENT(IN) :: itimestep
      REAL,DIMENSION(its:ite) :: wspd_jun1d, ust_jun1d
      REAL,DIMENSION(its:ite) :: lc_jun1d, lai_jun1d, beta_jun1d, zpd_jun1d, CHS_ori1d

      REAL,DIMENSION(its:ite) :: PSFC1D, CHS1D, CHS21D, CQS21D, CPM1D, PBLH1D, RMOL1D, ZNT1D, &
 & UST1D, MAVAIL1D, ZOL1D, MOL1D, REGIME1D, PSIM1D, PSIH1D, FM1D, FH1D, XLAND1D, HFX1D, QFX1D, &
 & TSK1D, U101D, V101D, TH21D ,T21D, Q21D ,FLHC1D, FLQC1D, QGH1D, QSFC1D, LH1D, GZ1OZ01D, WSPD1D, &
 & BR1D, LAI1D, hc_jun1d , USTM1D, CK1D,CKA1D, CD1D, CDA1D, &
 & cha1d    
     INTEGER, DIMENSION(its:ite) :: VEGTYP1D



      DO J=jts,jte
        DO i=its,ite
          dz8w1d(I) = dz8w(i,1,j)
        ENDDO
   
        DO i=its,ite
           U1D(i) =U3D(i,1,j)
           V1D(i) =V3D(i,1,j)
           QV1D(i)=QV3D(i,1,j)
           P1D(i) =P3D(i,1,j)
           T1D(i) =T3D(i,1,j)
           PSFC1D(i) = PSFC(i,j)
           CHS1D(i) = CHS(i,j)
           CHS21D(i) = CHS2(i,j)
           CQS21D(i) = CQS2(i,j)
           CPM1D(i) = CPM(i,j)
           PBLH1D(i) =  PBLH(i,j)
           RMOL1D(i) = RMOL(i,j)
           ZNT1D(i) = ZNT(i,j)
           UST1D(i) = UST(i,j)
           MAVAIL1D(i) = MAVAIL(i,j)
           ZOL1D(i) = ZOL(i,j)
           MOL1D(i) = MOL(i,j)
           REGIME1D(i)= REGIME(i,j)
           PSIM1D(i) = PSIM(i,j)
           PSIH1D(i) = PSIH(i,j)
           FM1D(i) = FM(i,j)
           FH1D(i) = FH(i,j)
           XLAND1D(i) =XLAND(i,j)
           HFX1D(i) = HFX(i,j)
           QFX1D(i) = QFX(i,j)
           TSK1D(i) = TSK(i,j)
           FLHC1D(i) = FLHC(i,j)
           FLQC1D(i) = FLQC(i,j)
           QGH1D(i) = QGH(i,j)
           LH1D(i) = LH(i,j)
           GZ1OZ01D(i) = GZ1OZ0(i,j)
           WSPD1D(i) = WSPD(i,j)
           BR1D(i) = BR(i,j)
           LAI1D(i) = LAI(i,j)
           VEGTYP1D(i) = VEGTYP(i,j)
           hc_jun1d(i) = hc_jun(i,j)
           USTM1D(i) = USTM(i,j)
           CHA1D(i) = CHARNOCK(i,j)  
        ENDDO

        
        

        CALL YSL1D(J,U1D,V1D,T1D,QV1D,P1D,dz8w1d,            &
                CP,G,ROVCP,R,XLV,PSFC1D,CHS1D,CHS21D,              &
                CQS21D,CPM1D,PBLH1D, RMOL1D,                       &
                ZNT1D,UST1D,MAVAIL1D,ZOL1D,                        &
                MOL1D,REGIME1D,PSIM1D,PSIH1D,                      &
                FM1D,FH1D,                                         &
                XLAND1D,HFX1D,QFX1D,TSK1D,                         &
                U101D,V101D,TH21D,T21D,                            &
                Q21D,FLHC1D,FLQC1D,QGH1D,                          &
                QSFC1D,LH1D,                                       &
                GZ1OZ01D,WSPD1D,BR1D,ISFFLX,DX,                    &
                SVP1,SVP2,SVP3,SVPT0,EP1,EP2,KARMAN,EOMEG,STBOLT,  &
                P1000mb,                                           &
                LAI1D, VEGTYP1D, MMINLU,                           & 
                wspd_jun1d, ust_jun1d,                             & 
                hc_jun1D, lai_jun1d, lc_jun1d,                     & 
                beta_jun1d, zpd_jun1d,                             & 
                CHS_ori1d,                                         & 
                itimestep,                                         & 
                cha1d,                                             & 
                ids,ide, jds,jde, kds,kde,                         &
                ims,ime, jms,jme, kms,kme,                         &
                its,ite, jts,jte, kts,kte                          &

                ,isftcflx,iz0tlnd,scm_force_flux,                  &
                USTM1D,CK1D,CKA1D,                                 &
                CD1D,CDA1D                                         &

                                                                   )
        DO i=its,ite
           wspd_jun(i,j)     = wspd_jun1d(i)
           ust_jun(i,j)      = ust_jun1d(i)
           lai_jun(i,j)      = lai_jun1d(i)
           lc_jun(i,j)       = lc_jun1d(i)
           beta_jun(i,j)     = beta_jun1d(i)
           zpd_jun(i,j)      = zpd_jun1d(i)
           CHS_ori(i,j)      = CHS_ori1d(i)
           ZNT(i,j) = ZNT1D(i)
           UST(i,j) = UST1D(i)
           ZOL(i,j) = ZOL1D(i)
           REGIME(i,j) = REGIME1D(i)
           HFX(i,j) = HFX1D(i)
           QFX(i,j) = QFX1D(i)
           LH(i,j) = LH1D(i)
           RMOL(i,j) = RMOL1D(i)
           MOL(i,j) = MOL1D(i)
           GZ1OZ0(i,j) = GZ1OZ01D(i)
           WSPD(i,j) = WSPD1D(i)
           BR(i,j) = BR1D(i)
           PSIM(i,j) = PSIM1D(i)
           PSIH(i,j) = PSIH1D(i)
           FM(i,j) = FM1D(i)
           FH(i,j) = FH1D(i)
           FLHC(i,j) = FLHC1D(i)
           FLQC(i,j) = FLQC1D(i)
           CHS(i,j) = CHS1D(i)
           CHS2(i,j) = CHS21D(i)
           CQS2(i,j)= CQS21D(i)
           CPM(i,j) = CPM1D(i)
           QGH(i,j) = QGH1D(i)
           CK(i,j) = CK1D(i)
           CKA(i,j) = CKA1D(i)
           CD(i,j) = CD1D(i)
           CDA(i,j) = CDA1D(i)
           hc_jun(i,j) = hc_jun1d(i)
           USTM(i,j) = USTM1D(i)

           U10(i,j) = U101D(i)
           V10(i,j) = V101D(i)
           TH2(i,j) = TH21D(i)
           T2(i,j) = T21D(i)
           Q2(i,j) = Q21D(i)
           QSFC(i,j) = QSFC1D(i)

        ENDDO


      ENDDO


   END SUBROUTINE YSL



   SUBROUTINE YSL1D(J,UX,VX,T1D,QV1D,P1D,dz8w1d,                &
                     CP,G,ROVCP,R,XLV,PSFCPA,CHS,CHS2,CQS2,CPM,PBLH,RMOL, &
                     ZNT,UST,MAVAIL,ZOL,MOL,REGIME,PSIM,PSIH,FM,FH,&
                     XLAND,HFX,QFX,TSK,                            &
                     U10,V10,TH2,T2,Q2,FLHC,FLQC,QGH,              &
                     QSFC,LH,GZ1OZ0,WSPD,BR,ISFFLX,DX,             &
                     SVP1,SVP2,SVP3,SVPT0,EP1,EP2,                 &
                     KARMAN,EOMEG,STBOLT,                          &
                     P1000mb,                                      &
                     LAI, VEGTYP, MMINLU,                          & 
                     wspd_jun, ust_jun,                            & 
                     hc_jun, lai_jun, lc_jun,                      & 
                     beta_jun, zpd_jun,                            & 
                     CHS_ori,                                      & 
                     Itimestep,                                    & 
                     cha1d,                                        & 
                     ids,ide, jds,jde, kds,kde,                    &
                     ims,ime, jms,jme, kms,kme,                    &
                     its,ite, jts,jte, kts,kte,                    &
                     isftcflx, iz0tlnd,scm_force_flux,             &
                     ustm,ck,cka,cd,cda                            )

      IMPLICIT NONE

      REAL,     PARAMETER     ::        XKA=2.4E-5
      REAL,     PARAMETER     ::        PRT=1.

      INTEGER,  INTENT(IN )   ::        ids,ide, jds,jde, kds,kde, &
                                        ims,ime, jms,jme, kms,kme, &
                                        its,ite, jts,jte, kts,kte, &
                                        J

      INTEGER,  INTENT(IN )   ::        ISFFLX
      REAL,     INTENT(IN )   ::        SVP1,SVP2,SVP3,SVPT0
      REAL,     INTENT(IN )   ::        EP1,EP2,KARMAN,EOMEG,STBOLT
      REAL,     INTENT(IN )   ::        P1000mb


      REAL,     DIMENSION( its:ite )                             , &
                INTENT(IN   )               ::             MAVAIL, &
                                                             PBLH, &
                                                            XLAND, &
                                                              TSK

      REAL,     DIMENSION( its:ite )                             , &
                INTENT(IN   )               ::             PSFCPA

      REAL,     DIMENSION( its:ite )                             , &
                INTENT(INOUT)               ::             REGIME, &
                                                              HFX, &
                                                              QFX, &
                                                         MOL,RMOL


      REAL,     DIMENSION( its:ite )                             , &
                INTENT(INOUT)   ::                 GZ1OZ0,WSPD,BR, &
                                                  PSIM,PSIH,FM,FH

      REAL,     DIMENSION( its:ite )                             , &
                INTENT(INOUT)   ::                                 &
                                                              ZOL, &
                                                              UST, &
                                                              CPM, &
                                                             CHS2, &
                                                             CQS2, &
                                                              CHS
      REAL,     DIMENSION( its:ite ), INTENT(INOUT)   ::        ZNT
      REAL,     DIMENSION( its:ite ), INTENT(INOUT)   ::       CHS_ori
      REAL,     DIMENSION( its:ite ), INTENT(IN)      ::       CHA1D  
      REAL,     DIMENSION( its:ite )                             , &
                INTENT(INOUT)   ::                      FLHC,FLQC

      REAL,     DIMENSION( its:ite )                             , &
                INTENT(INOUT)   ::                                 &
                                                              QGH

      REAL,     DIMENSION( its:ite )                             , &
                INTENT(OUT)     ::                        U10,V10, &
                                                TH2,T2,Q2,QSFC,LH

                                    
      REAL,     INTENT(IN   )               ::   CP,G,ROVCP,R,XLV,DX


      REAL,     DIMENSION( its:ite ),  INTENT(IN   )   ::  dz8w1d

      REAL,     DIMENSION( its:ite ),  INTENT(IN   )   ::      UX, &
                                                               VX, &
                                                             QV1D, &
                                                              P1D, &
                                                              T1D
 
      REAL, OPTIONAL, DIMENSION( its:ite )                       , &
                INTENT(OUT)     ::                  ck,cka,cd,cda
      REAL, OPTIONAL, DIMENSION( its:ite )                       , &
                INTENT(INOUT)   ::                           USTM

      INTEGER,  OPTIONAL,  INTENT(IN )   ::     ISFTCFLX, IZ0TLND
      INTEGER,  OPTIONAL,  INTENT(IN )   ::     SCM_FORCE_FLUX



      REAL,     DIMENSION( its:ite )        ::                 ZA, &
                                                        THVX,ZQKL, &
                                                           ZQKLP1, &
                                                           THX,QX, &
                                                            PSIH2, &
                                                            PSIM2, &
                                                           PSIH10, &
                                                           PSIM10, &
                                                           DENOMQ, &
                                                          DENOMQ2, &
                                                          DENOMT2, &
                                                            WSPDI, &
                                                           GZ2OZ0, &
                                                           GZ10OZ0

      REAL,     DIMENSION( its:ite )        ::                     &
                                                      RHOX,GOVRTH, &
                                                            TGDSA

      REAL,     DIMENSION( its:ite)         ::          SCR3,SCR4
      REAL,     DIMENSION( its:ite )        ::         THGB, PSFC

      INTEGER                               ::                 KL

      INTEGER ::  N,I,K,KK,L,NZOL,NK,NZOL2,NZOL10

      REAL    ::  THCON,E1
      REAL,DIMENSION( its:ite ) ::  PL, TVCON
      REAL    ::  DTHVM,VCONV,RZOL,RZOL2,RZOL10,ZOL2,ZOL10
      REAL,DIMENSION( its:ite ) :: TSKV,DTHVDZ

      REAL    ::  DTG,PSIX,DTTHX,PSIX10,PSIT,PSIT2,PSIQ,PSIQ2,PSIQ10
      REAL    ::  FLUXC,VSGD,Z0Q,VISC,RESTAR,CZIL,GZ0OZQ,GZ0OZT
      REAL    ::  ZW, ZN1, ZN2



      REAL    :: zl2,zl10,z0t
      REAL,     DIMENSION( its:ite )        ::         pq,pq2,pq10
      REAL,DIMENSION( its:ite ), INTENT(IN) :: LAI
      INTEGER,DIMENSION( its:ite ), INTENT(IN) :: VEGTYP
      CHARACTER(LEN=*),INTENT(IN) :: MMINLU
      REAL, DIMENSION( its:ite ) :: GZZ0
      REAL,DIMENSION( its:ite ), INTENT(OUT)   :: wspd_jun, ust_jun
      REAL,DIMENSION( its:ite ), INTENT(OUT)   :: lai_jun, lc_jun, beta_jun, zpd_jun
      REAL,DIMENSION( its:ite ), INTENT(IN) :: hc_jun
      integer,intent(in) :: itimestep
      REAL,dimension( its:ite ) :: PSIM_hat, PSIH_hat
      REAL,dimension( its:ite ) :: zl, zol0, zzzol, zolzz, zzzolzz

      REAL,dimension( its:ite )  ::  Hc, VAI, D1, Lc, Prc, ff, Uhc, Thc, &
      & znt_new, znt_old, zpd_dt, dtemp, dwind, PSIH_hat_ori, pq_chs, chs_i1, chs_i2
      real,dimension( its:ite) :: chs_temp
      REAL,dimension( its:ite )  :: beta, beta_old, betaHF, betaNO

      integer :: zzz
      integer :: ITER, ITER_CONFIG
      REAL :: zll
      real,dimension( its:ite ) :: Psim_temp
      real,dimension( its:ite ) :: Psim_hat_temp, Psih_hat_temp, psih_hat_chs

      integer :: ierr
      real, dimension(1:50) ::  SNUPTBL, RSTBL, RGLTBL, HSTBL,                &
                                  SHDTBL, MAXALB,                               &
                                  EMISSMINTBL, EMISSMAXTBL,                     &
                                  LAIMINTBL, LAIMAXTBL,                         &
                                  Z0MINTBL, Z0MAXTBL,                           &
                                  ALBEDOMINTBL, ALBEDOMAXTBL,                   &
                                  ZTOPVTBL,ZBOTVTBL
      INTEGER, dimension(1:50):: NROTBL
      INTEGER :: LUMATCH, IINDEX, LUCATS, LCC
      CHARACTER(LEN=256) :: LUTYPE
      real :: G1, G2, startz, endz, startz1, endz1, zhat
      real,dimension(its:ite) :: cm1, ch1, cm2, ch2
      LOGICAL,parameter :: ONOFF = .TRUE.  

      REAL :: P,pp
      INTEGER :: pr_VEGTYP
      REAL :: pr_znt, pr_zl, pr_zol, pr_br, pr_lai,  pr_ust1, pr_ust2, pr_l
      REAL :: pr_psim_hat, pr_psih_hat, pr_psim, pr_psim1, pr_psim2, pr_psih, pr_psih1, pr_psih2
      REAL :: pr_pq, pr_pq1, pr_pq2, pr_gz1Oz0, pr_gzz0
      REAL :: pr_psix, pr_psit, pr_psiq, pr_lnpq, pr_wspd, pr_lnpq2, pr_psiq2
      REAL :: pr_HC, pr_VAI, pr_PRC, pr_FF, pr_LC, pr_BETA, pr_CHS, Pr_zpd, pr_phihc, pr_zpd2, pr_mol2, pr_ITER
      REAL :: pr_term1, pr_term2, pr_term3, pr_term4

      REAL,dimension( its:ite )  :: beta1, beta2

      REAL, PARAMETER :: betaN = 0.374

      REAL :: TIMES, TIMEE

      ITER_CONFIG = 1
      zpd_jun = 0
      beta_jun = 0

      KL=kte

      DO i=its,ite

         PSFC(I)=PSFCPA(I)/1000.
      ENDDO



      DO 5 I=its,ite                                   
        TGDSA(I)=TSK(I)                                    


        THGB(I)=TSK(I)*(P1000mb/PSFCPA(I))**ROVCP   
    5 CONTINUE                                               














                                                             
                                                   


                                                                                 
      DO 30 I=its,ite

         PL(i)=P1D(I)/1000.
         SCR3(I)=T1D(I)                                                   

         THCON=(P1000mb*0.001/PL(i))**ROVCP
         THX(I)=SCR3(I)*THCON                                               
         SCR4(I)=SCR3(I)                                                    
         THVX(I)=THX(I)                                                     
         QX(I)=0.                                                             
   30 CONTINUE                                                                 

      DO I=its,ite
         QGH(I)=0.                                                                
         FLHC(I)=0.                                                               
         FLQC(I)=0.                                                               
         CPM(I)=CP                                                                
      ENDDO


      DO 50 I=its,ite
         QX(I)=QV1D(I)                                                    
         TVCON(i)=(1.+EP1*QX(I))                                      
         THVX(I)=THX(I)*TVCON(i)                                               
         SCR4(I)=SCR3(I)*TVCON(i)                                              
   50 CONTINUE                                                                 

      DO 60 I=its,ite
        E1=SVP1*EXP(SVP2*(TGDSA(I)-SVPT0)/(TGDSA(I)-SVP3))                       


        QSFC(I)=EP2*E1/(PSFC(I)-E1)


        E1=SVP1*EXP(SVP2*(T1D(I)-SVPT0)/(T1D(I)-SVP3))                       
        PL(i)=P1D(I)/1000.
        QGH(I)=EP2*E1/(PL(i)-E1)                                                 
        CPM(I)=CP*(1.+0.8*QX(I))                                   
   60 CONTINUE                                                                   
   80 CONTINUE
                                                                                 


                                                                                 
      DO 90 I=its,ite
        ZQKLP1(I)=0.
        RHOX(I)=PSFC(I)*1000./(R*SCR4(I))                                       
   90 CONTINUE                                                                   

      DO 110 I=its,ite                                                   
           ZQKL(I)=dz8w1d(I)+ZQKLP1(I)
  110 CONTINUE                                                                 

      DO 120 I=its,ite
         ZA(I)=0.5*(ZQKL(I)+ZQKLP1(I))                                        
  120 CONTINUE                                                                 

      DO 160 I=its,ite
        GOVRTH(I)=G/THX(I)                                                    
  160 CONTINUE                                                                   
                                                                                 


                   
      DO 260 I=its,ite
        GZ1OZ0(I)=ALOG((ZA(I)+ZNT(I))/ZNT(I))   
        GZ2OZ0(I)=ALOG((2.+ZNT(I))/ZNT(I))      
        GZ10OZ0(I)=ALOG((10.+ZNT(I))/ZNT(I))    

        GZZ0  (I)=ALOG((ZA(I))/ZNT(I))

        IF((XLAND(I)-1.5).GE.0)THEN                                            
          ZL(i)=ZNT(I)                                                            
        ELSE                                                                     
          ZL(i)=0.01                                                                
        ENDIF                                                                    
        WSPD(I)=SQRT(UX(I)*UX(I)+VX(I)*VX(I))                        

        TSKV(i)=THGB(I)*(1.+EP1*QSFC(I))                     
        DTHVDZ(i)=(THVX(I)-TSKV(i))                                                 






        if (xland(i).lt.1.5) then
        fluxc = max(hfx(i)/rhox(i)/cp                    &
              + ep1*tskv(i)*qfx(i)/rhox(i),0.)
        VCONV = vconvc*(g/tgdsa(i)*pblh(i)*fluxc)**.33
        else
        IF(-DTHVDZ(i).GE.0)THEN
          DTHVM=-DTHVDZ(i)
        ELSE
          DTHVM=0.
        ENDIF


        VCONV = SQRT(DTHVM)
        endif

        VSGD = 0.32 * (max(dx/5000.-1.,0.))**.33
        WSPD(I)=SQRT(WSPD(I)*WSPD(I)+VCONV*VCONV+vsgd*vsgd)
        WSPD(I)=AMAX1(WSPD(I),0.1)

        WSPD_JUN(I) = WSPD(I)

        BR(I)=GOVRTH(I)*ZA(I)*DTHVDZ(I)/(WSPD(I)*WSPD(I))                        

        IF(MOL(I).LT.0.)BR(I)=AMIN1(BR(I),0.0)

        RMOL(I)=-GOVRTH(I)*DTHVDZ(i)*ZA(I)*KARMAN


  260 CONTINUE                                                                   





















      DO I=its,ite


  VAI(i) = LAI(i)
  IF ( VAI(I) <= 0 ) then
    VAI(i) = 0.1
  ENDIF
  Lc(i) = 4.0 * Hc_jun(i) / VAI(i)

  IF ( Lc(i) >= 500. ) Lc(i) = 500.
  lai_jun(i) = VAI(i)
  lc_jun(i) = Lc(i)
  Hc(i) = Hc_jun(i)

  VAI(i) = LAI(i)
     IF ( (XLAND(I)-1.5).GT.0. .or.                                               &
         (MMINLU .eq. 'USGS' .and. (VEGTYP(I)==1 .or. VEGTYP(I)>=16)) .or.   &
         (MMINLU .eq. 'MODIFIED_IGBP_MODIS_NOAH' .and.                       &
         (VEGTYP(I)==11 .or. VEGTYP(I)==13 .or. VEGTYP(I)==15 .or. VEGTYP(I)==17 ))) then

                                                                   
      if (br(I).gt.0) then
        if (br(I).gt.250.0) then
        zol(I)=zolri(250.0,ZA(I),ZNT(I))
        else
        zol(I)=zolri(br(I),ZA(I),ZNT(I))
        endif
      endif

      if (br(I).lt.0) then
       IF(UST(I).LT.0.001)THEN
          ZOL(I)=BR(I)*GZ1OZ0(I)
        ELSE
        if (br(I).lt.-250.0) then
        zol(I)=zolri(-250.0,ZA(I),ZNT(I))
        else
        zol(I)=zolri(br(I),ZA(I),ZNT(I))
        endif
       ENDIF
      endif
    ELSE
      if (br(I).gt.0) then
        if (br(I).gt.250.0) then
        zol(I)=zolri3(250.0,ZA(I),ZNT(I),0.01,Lc(i),Hc(i),ust(i),xka)
        else
        zol(I)=zolri3(br(I),ZA(I),ZNT(I),0.01,Lc(i),Hc(i),ust(i),xka)
        endif
      endif

      if (br(I).lt.0) then
       IF(UST(I).LT.0.001)THEN
          ZOL(I)=BR(I)*GZZ0(I)
        ELSE
        if (br(I).lt.-250.0) then
        zol(I)=zolri3(-250.0,ZA(I),ZNT(I),0.01,Lc(i),Hc(i),ust(i),xka)
        else
        zol(I)=zolri3(br(I),ZA(I),ZNT(I),0.01,Lc(i),Hc(i),ust(i),xka)
        endif
       ENDIF
      endif
    ENDIF

    IF (BR(I) == 0) zol(i) = 0.

ENDDO 

znt_new(:)=znt(:)
znt_old(:)=0
DO I = its,ite 
zpd_dt(i) = Hc(i) * 0.35

IF (ITER_CONFIG .EQ. 1 .and. XLAND(I) .LT. 1.5 .and.                                           &
    ((MMINLU .eq. 'USGS' .and. (VEGTYP(I)>=2.and.VEGTYP(I)<=15)) .or.                          &
     (MMINLU .eq. 'MODIFIED_IGBP_MODIS_NOAH' .and. (VEGTYP(I) .ne. 11).and.(VEGTYP(I).ne.13).and.(VEGTYP(I).ne.15).and.(VEGTYP(I).ne.17)))) then

ITER = 1


IF (zol(i)==0.) THEN
 MOL(i) = 999999.
ELSE
 MOL(i) = za(i) / zol(i)
ENDIF
beta(i) = betaN /PHIM(zpd_dt(i),MOL(i))

betaHF(i) = betaN /PHIM(zpd_dt(i),MOL(i))
betaNO(i) = 0.4/2./PHIM(zpd_dt(i),MOL(i))
beta(i)   = betaNO(i) + (BetaHF(i)-BetaNO(i))/(1+2* ((abs(Lc(i)/MOL(i)+0.15))**1.5)  )
IF ( Lc(i)/MOL(i) > -0.15 ) beta(i) = betaHF(i)


beta_old(i) = beta(i)

ENDIF 

IF (ITER_CONFIG .EQ. 1 .and. XLAND(I) .LT. 1.5 .and.                                           &
    ((MMINLU .eq. 'USGS' .and. (VEGTYP(I)>=2.and.VEGTYP(I)<=15)) .or.                          &
     (MMINLU .eq. 'MODIFIED_IGBP_MODIS_NOAH' .and. (VEGTYP(I) .ne. 11).and.(VEGTYP(I).ne.13).and.(VEGTYP(I).ne.15).and.(VEGTYP(I).ne.17)))) then

DO WHILE  ( (abs (beta1(i) - beta(i)) > 0.0001 .and. ITER < 5 ).or. ITER == 1 )
  zpd_dt(i) = beta_old(i)*beta_old(i)*Lc(i) 

 IF ( zpd_dt(i) .ge. 0.90*za(i) ) THEN
   zpd_dt(i) = 0.90*za(i)
 ENDIF
 IF ( zpd_dt(i) .ge. 0.90*Hc(i) ) THEN
   zpd_dt(i) = 0.90*Hc(i)
 ENDIF

IF ( ITER >= 2 ) beta2(i) = beta1(i)
beta1(i) = beta(i)

beta(i) = betaN /PHIM(zpd_dt(i),MOL(i))

betaHF(i) = betaN /PHIM(zpd_dt(i),MOL(i))
betaNO(i) = 0.4/2./PHIM(zpd_dt(i),MOL(i))
beta(i)   = betaNO(i) + (BetaHF(i)-BetaNO(i))/(1+2* ((abs(Lc(i)/MOL(i)+0.15))**1.5)  )
IF ( Lc(i)/MOL(i) > -0.15 ) beta(i) = betaHF(i)

beta_old(i) = beta(i)

IF ( abs(beta2(i)-beta(i)) < 0.001 .and. abs(beta1(I)-beta(i)) > 0.001 .and. ITER >= 2 ) then
beta(i) = ( beta(i)+beta1(i) )/ 2.
beta_old(i) = beta(i)
go to 987
ENDIF
IF ( beta(i) < beta1(i) .and. beta(i) < beta2(i) .and. ITER >= 2 ) then
beta(i) = ( beta(i)+beta1(i) )/ 2.
beta_old(i) = beta(i)
go to 987
ENDIF
IF ( beta(i) > beta1(i) .and. beta(i) > beta2(i) .and. ITER >= 2) then
beta(i) = ( beta(i)+beta1(i) )/ 2.
beta_old(i) = beta(i)
go to 987
ENDIF

987 continue

beta_old(i) = beta(i)
ITER = ITER + 1
ENDDO  

beta_jun(I) = beta_old(i)
zpd_jun(I) = zpd_dt(i)

Prc(I) = 0.5 + 0.3 * tanh ( 2. * Lc(I) * zol(I) / za(I) )
ff(I)     = 0.5 * ( sqrt(1. + 4.*0.1*Prc(I) ) -1. )
IF ( BR(i) > 0 ) THEN
  cm2(i) = KARMAN        * ( 2.       -2.*beta_old(i)*beta_old(i)*Lc(i)*5./MOL(i)/PHIM(zpd_dt(i),MOL(i)) ) / (2.*beta_old(i)*PHIM(zpd_dt(i),MOL(i)) - KARMAN         )
  ch2(i) = KARMAN *Prc(i)* ( 2. +ff(i)-2.*beta_old(i)*beta_old(i)*Lc(i)*5./MOL(i)/PHIM(zpd_dt(i),MOL(i)) ) / (2.*beta_old(i)*PHIM(zpd_dt(i),MOL(i)) - KARMAN *Prc(i) )

ELSE IF ( BR(i) < 0 ) THEN
  cm2(i) = KARMAN        * (2.       - 8.*beta_old(i)*beta_old(i)*Lc(i)/MOL(i)*(PHIM(zpd_dt(i),MOL(i))**4))/(2.*beta_old(i)*PHIM(zpd_dt(i),MOL(i)) - KARMAN         )
  ch2(i) = KARMAN *Prc(i)* (2. +ff(i)- 8.*beta_old(i)*beta_old(i)*Lc(i)/MOL(i)*(PHIM(zpd_dt(i),MOL(i))**4))/(2.*beta_old(i)*PHIM(zpd_dt(i),MOL(i)) - KARMAN *Prc(i) )
ELSE
  cm2(i) = KARMAN        * (2.        )/(2*beta_old(i) - KARMAN         )
  ch2(i) = KARMAN *Prc(i)* (2. +ff(i) )/(2*beta_old(i) - KARMAN *Prc(i) )
ENDIF
IF ( cm2(i) >= 5. ) cm2(i) = 5.
IF ( cm2(i) <= 0.  ) cm2(i) = 0.01
IF ( ch2(i) >= 5. ) ch2(i) = 5.
IF ( ch2(i) <= 0.  ) ch2(i) = 0.01


ITER = 1
DO WHILE  ( (abs (znt_old(i) - znt(i)) > 0.001 .and. ITER < 5 ).or. ITER == 1 )

  zzzol(I) = zol(i) / za(i) * zpd_dt(i)
  zol0(i)=zol(I)*znt(I)/za(I)          
  zzzolzz(I) = zzzol(I)+zol0(I)
IF (zzzol(i)==0.) THEN
 MOL(i) = 999999.
ELSE
 MOL(i) = zpd_dt(i) / zzzol(i)
ENDIF

cm1(i) = (1.-(0.4/(betaN*2.)))*exp(cm2(i)/2.)

startz = zpd_dt(i)
endz   = za(i)*2.

PSIM_hat_temp(i) = 0
startz1 = startz
endz1   = za(i)
G1  = (endz1-startz1)/2.*(-1/sqrt(3.)) + (endz1+startz1)/2.
G2  = (endz1-startz1)/2.*( 1/sqrt(3.)) + (endz1+startz1)/2.
PSIM_hat_temp(i) = PSIM_hat_temp(i) + (endz1-startz1)/2. * (     (PHIM(G1,MOL(i)) * (1.-(1.-cm1(i)*exp( cm2(i)/(2.*beta_old(i)*beta_old(i)*Lc(i))*G1*(-1.) ))) / G1)&
& + (PHIM(G2,MOL(i)) * (1.-(1.-cm1(i)*exp( cm2(i)/(2.*beta_old(i)*beta_old(i)*Lc(i))*G2*(-1.) ))) / G2) )

DO zhat = za(i), endz-za(i)/2., za(i)/2.
startz1 = zhat
endz1 = zhat+za(i)/2.
G1  = (endz1-startz1)/2.*(-1./sqrt(3.)) + (endz1+startz1)/2.
G2  = (endz1-startz1)/2.*( 1./sqrt(3.)) + (endz1+startz1)/2.

PSIM_hat_temp(i) = PSIM_hat_temp(i) + (endz1-startz1)/2. * (     (PHIM(G1,MOL(i)) * (1.-(1.-cm1(i)*exp( cm2(i)/(2.*beta_old(i)*beta_old(i)*Lc(i))*G1*(-1.) ))) / G1)&
& + (PHIM(G2,MOL(i)) * (1.-(1.-cm1(i)*exp( cm2(i)/(2.*beta_old(i)*beta_old(i)*Lc(i))*G2*(-1.) ))) / G2) )
ENDDO


  IF ( BR(i) > 0 ) THEN
    psim_temp(i) = psim_stable(zzzol(I))-psim_stable(zol0(i))
  ELSE IF ( BR(i) < 0 ) THEN
    psim_temp(i) = psim_unstable(zzzol(I))-psim_unstable(zol0(i))
  ELSE
    psim_temp(i) = 0
  ENDIF

  ZNT_OLD(i) = ZNT(i)
  ZNT(i) = zpd_dt(i) * exp ( -1.*0.4 / beta_old(i) ) * exp ( -1.*psim_temp(i) ) * exp( PSIM_hat_temp(i) )

 IF ( ZNT(i) > 3./7. * zpd_dt(i) ) THEN
   ZNT(i) = 3./7. * zpd_dt(i)
 ELSE IF ( ZNT(i) < 0.01 ) THEN
   ZNT(i) = 0.01
 ENDIF

ITER = ITER + 1
ENDDO  
ENDIF 






        zolzz(i)=zol(I)*(za(I)+znt(I))/za(I) 
        zol10=zol(I)*(10.+znt(I))/za(I)   
        zol2=zol(I)*(2.+znt(I))/za(I)     
        zol0=zol(I)*znt(I)/za(I)          
        ZL2=(2.)/ZA(I)*ZOL(I)             
        ZL10=(10.)/ZA(I)*ZOL(I)           
        GZ1OZ0(I)=ALOG((ZA(I)+ZNT(I))/ZNT(I))   

        IF((XLAND(I)-1.5).LT.0.)THEN
        ZLL=(0.01)/ZA(I)*ZOL(I)   
        ELSE
        ZLL=zol0(i)                     
        ENDIF


        IF((XLAND(I)-1.5).LT.0 .and.                                               &
           ((MMINLU .eq. 'USGS' .and. (VEGTYP(I)>=2.and.VEGTYP(I)<=15)) .or.       &
            (MMINLU .eq. 'MODIFIED_IGBP_MODIS_NOAH'.and.(VEGTYP(I).ne.11).and.(VEGTYP(I).ne.13).and.(VEGTYP(I).ne.15).and.(VEGTYP(I).ne.17)))) THEN

          call RPSI_hat (zl(i), zol0(i), ZOL(I), ZA(i), ZA(I), Lc(I), zpd_dt(i), cm2(i), ch2(i),&  
                       &D1(i), beta_old(i), PSIM_hat(i), PSIH_hat(i) )          
        ELSE
          PSIM_hat(i) = 0
          PSIH_hat(i) = 0
        ENDIF


IF ( BR(I) .GT. 0. ) THEN




        REGIME(I)=1.



        psim(I)=psim_stable(zol(i))-psim_stable(zol0(i))-PSIM_hat(i)
        psih(I)=psih_stable(zol(i))-psih_stable(zol0(i))

        psim10(I)=psim_stable(zol10)-psim_stable(zol0(i))
        psih10(I)=psih_stable(zol10)-psih_stable(zol0(i))

        psim2(I)=psim_stable(zol2)-psim_stable(zol0(i))
        psih2(I)=psih_stable(zol2)-psih_stable(zol0(i))



        pq(I)=psih_stable(zol(I))-psih_stable(zlL)-PSIH_hat(i)
        pq2(I)=psih_stable(zl2)-psih_stable(zol0(i))
        pq10(I)=psih_stable(zl10)-psih_stable(zol0(i))


        RMOL(I)=ZOL(I)/ZA(I) 

ELSE IF ( BR(i) .EQ. 0. ) THEN



        REGIME(I)=3.                                                           


        PSIM(I)=-PSIM_hat(i)
        PSIH(I)=0.
        PSIM10(I)=0.                                                   
        PSIH10(I)=PSIM10(I)                                           
        PSIM2(I)=0.                                                  
        PSIH2(I)=PSIM2(I)                                           



        pq(I)=-PSIH_hat(i)
        pq2(I)=PSIH2(I)
        pq10(I)=0.

        ZOL(I)=0.                                             
        RMOL(I) = ZOL(I)/ZA(I)  
ELSE



        REGIME(I)=4.                                                           



        psim(I)=psim_unstable(zol(I))-psim_unstable(zol0(i))-PSIM_hat(i)
        psih(I)=psih_unstable(zolzz(i))-psih_unstable(zol0(i))

        psim10(I)=psim_unstable(zol10)-psim_unstable(zol0(i))
        psih10(I)=psih_unstable(zol10)-psih_unstable(zol0(i))

        psim2(I)=psim_unstable(zol2)-psim_unstable(zol0(i))
        psih2(I)=psih_unstable(zol2)-psih_unstable(zol0(i))



        pq(I)=psih_unstable(zol(I))-psih_unstable(zlL)-PSIH_hat(i)
        pq2(I)=psih_unstable(zl2)-psih_unstable(zol0(i))
        pq10(I)=psih_unstable(zl10)-psih_unstable(zol0(i))




        PSIM(I)=AMIN1(PSIM(I),0.9*GZZ0(I))
        PSIH(I)=AMIN1(PSIH(I),0.9*GZ1OZ0(I))
        PSIH2(I)=AMIN1(PSIH2(I),0.9*GZ2OZ0(I))
        PSIM10(I)=AMIN1(PSIM10(I),0.9*GZ10OZ0(I))



        PSIH10(I)=AMIN1(PSIH10(I),0.9*GZ10OZ0(I))

        RMOL(I) = ZOL(I)/ZA(I)  

ENDIF





        DTG=THX(I)-THGB(I)         
        GZZ0(I) = ALOG((ZA(I))/ZNT(I))
        PSIX=GZZ0(I)-PSIM(I)
        PSIX10=GZ10OZ0(I)-PSIM10(I)




       PSIT=GZ1OZ0(I)-PSIH(I)
       PSIT2=GZ2OZ0(I)-PSIH2(I)

        IF((XLAND(I)-1.5).GE.0)THEN                                            
          ZL(I)=ZNT(I)                                                            
        ELSE                                                                     
          ZL(I)=0.01                                                                
        ENDIF                                                                    

        PSIQ=ALOG(KARMAN*UST(I)*ZA(I)/XKA+ZA(I)/ZL(I))-pq(I)
        PSIQ2=ALOG(KARMAN*UST(I)*2./XKA+2./ZL(I))-pq2(I)


        PSIQ10=ALOG(KARMAN*UST(I)*10./XKA+10./ZL(I))-pq10(I)




        IF ( (XLAND(I)-1.5).GE.0. ) THEN
              VISC=(1.32+0.009*(SCR3(I)-273.15))*1.E-5
              RESTAR=UST(I)*ZNT(I)/VISC
              Z0T = (5.5e-5)*(RESTAR**(-0.60))
              Z0T = MIN(Z0T,1.0e-4)
              Z0T = MAX(Z0T,2.0e-9)
              Z0Q = Z0T

              PSIQ=max(ALOG((ZA(I)+Z0Q)/Z0Q)-PSIH(I), 2.)
              PSIT=max(ALOG((ZA(I)+Z0T)/Z0T)-PSIH(I), 2.)
              PSIQ2=max(ALOG((2.+Z0Q)/Z0Q)-PSIH2(I), 2.)
              PSIT2=max(ALOG((2.+Z0T)/Z0T)-PSIH2(I), 2.)
              PSIQ10=max(ALOG((10.+Z0Q)/Z0Q)-PSIH10(I), 2.)
        ENDIF

        IF ( PRESENT(ISFTCFLX) ) THEN
           IF ( ISFTCFLX.EQ.1 .AND. (XLAND(I)-1.5).GE.0. ) THEN





              Z0Q = 1.e-4



           zolzz(i)=zol(I)*(za(I)+z0q)/za(I)    
           zol10=zol(I)*(10.+z0q)/za(I)   
           zol2=zol(I)*(2.+z0q)/za(I)     
           zol0(i)=zol(I)*z0q/za(I)          

              if (zol(I).gt.0.) then
              psih(I)=psih_stable(zolzz(i))-psih_stable(zol0(i))
              psih10(I)=psih_stable(zol10)-psih_stable(zol0(i))
              psih2(I)=psih_stable(zol2)-psih_stable(zol0(i))
              else
                if (zol(I).eq.0) then
                psih(I)=0.
                psih10(I)=0.
                psih2(I)=0.
                else
                psih(I)=psih_unstable(zolzz(i))-psih_unstable(zol0(i))
                psih10(I)=psih_unstable(zol10)-psih_unstable(zol0(i))
                psih2(I)=psih_unstable(zol2)-psih_unstable(zol0(i))
                endif
              endif

              PSIQ=ALOG((ZA(I)+z0q)/Z0Q)-PSIH(I)
              PSIT=PSIQ
              PSIQ2=ALOG((2.+z0q)/Z0Q)-PSIH2(I)
              PSIQ10=ALOG((10.+z0q)/Z0Q)-PSIH10(I)
              PSIT2=PSIQ2
           ENDIF
          IF ( ISFTCFLX.EQ.2 .AND. (XLAND(I)-1.5).GE.0. ) THEN





              VISC=(1.32+0.009*(SCR3(I)-273.15))*1.E-5

              RESTAR=UST(I)*ZNT(I)/VISC
              GZ0OZT=0.40*(7.3*SQRT(SQRT(RESTAR))*SQRT(0.71)-5.)



              z0t=znt(I)/exp(GZ0OZT)

           zolzz(i)=zol(I)*(za(I)+z0t)/za(I)    
           zol10=zol(I)*(10.+z0t)/za(I)   
           zol2=zol(I)*(2.+z0t)/za(I)     
           zol0(i)=zol(I)*z0t/za(I)          

              if (zol(I).gt.0.) then
              psih(I)=psih_stable(zolzz(i))-psih_stable(zol0(i))
              psih10(I)=psih_stable(zol10)-psih_stable(zol0(i))
              psih2(I)=psih_stable(zol2)-psih_stable(zol0(i))
              else
                if (zol(I).eq.0) then
                psih(I)=0.
                psih10(I)=0.
                psih2(I)=0.
                else
                psih(I)=psih_unstable(zolzz(i))-psih_unstable(zol0(i))
                psih10(I)=psih_unstable(zol10)-psih_unstable(zol0(i))
                psih2(I)=psih_unstable(zol2)-psih_unstable(zol0(i))
                endif
              endif



              PSIT=ALOG((ZA(I)+z0t)/Z0t)-PSIH(I)
              PSIT2=ALOG((2.+z0t)/Z0t)-PSIH2(I)

              GZ0OZQ=0.40*(7.3*SQRT(SQRT(RESTAR))*SQRT(0.60)-5.)
              z0q=znt(I)/exp(GZ0OZQ)

           zolzz(i)=zol(I)*(za(I)+z0q)/za(I)    
           zol10=zol(I)*(10.+z0q)/za(I)   
           zol2=zol(I)*(2.+z0q)/za(I)     
           zol0(i)=zol(I)*z0q/za(I)          

              if (zol(I).gt.0.) then
              psih(I)=psih_stable(zolzz(i))-psih_stable(zol0(i))
              psih10(I)=psih_stable(zol10)-psih_stable(zol0(i))
              psih2(I)=psih_stable(zol2)-psih_stable(zol0(i))
              else
                if (zol(I).eq.0) then
                psih(I)=0.
                psih10(I)=0.
                psih2(I)=0.
                else
                psih(I)=psih_unstable(zolzz(i))-psih_unstable(zol0(i))
                psih10(I)=psih_unstable(zol10)-psih_unstable(zol0(i))
                psih2(I)=psih_unstable(zol2)-psih_unstable(zol0(i))
                endif
              endif

              PSIQ=ALOG((ZA(I)+z0q)/Z0q)-PSIH(I)
              PSIQ2=ALOG((2.+z0q)/Z0q)-PSIH2(I)
              PSIQ10=ALOG((10.+z0q)/Z0q)-PSIH10(I)



           ENDIF
        ENDIF
        IF(PRESENT(ck) .and. PRESENT(cd) .and. PRESENT(cka) .and. PRESENT(cda)) THEN
           Ck(I)=(karman/psix10)*(karman/psiq10)
           Cd(I)=(karman/psix10)*(karman/psix10)
           Cka(I)=(karman/psix)*(karman/psiq)
           Cda(I)=(karman/psix)*(karman/psix)
        ENDIF
        IF ( PRESENT(IZ0TLND) ) THEN
           IF ( IZ0TLND.GE.1 .AND. (XLAND(I)-1.5).LE.0. ) THEN
              ZL(I)=ZNT(I)

              VISC=(1.32+0.009*(SCR3(I)-273.15))*1.E-5
              RESTAR=UST(I)*ZL(I)/VISC


                 CZIL = 10.0 ** ( -0.40 * ( ZL(I) / 0.07 ) )



              z0t=znt(I)/exp(CZIL*KARMAN*SQRT(RESTAR))

           zolzz(i)=zol(I)*(za(I)+z0t)/za(I)    
           zol10=zol(I)*(10.+z0t)/za(I)   
           zol2=zol(I)*(2.+z0t)/za(I)     
           zol0(i)=zol(I)*z0t/za(I)          

              if (zol(I).gt.0.) then
              psih(I)=psih_stable(zolzz(i))-psih_stable(zol0(i))
              psih10(I)=psih_stable(zol10)-psih_stable(zol0(i))
              psih2(I)=psih_stable(zol2)-psih_stable(zol0(i))
              else
                if (zol(I).eq.0) then
                psih(I)=0.
                psih10(I)=0.
                psih2(I)=0.
                else
                psih(I)=psih_unstable(zolzz(i))-psih_unstable(zol0(i))
                psih10(I)=psih_unstable(zol10)-psih_unstable(zol0(i))
                psih2(I)=psih_unstable(zol2)-psih_unstable(zol0(i))
                endif
              endif

              PSIQ=ALOG((ZA(I)+z0t)/Z0t)-PSIH(I)
              PSIQ2=ALOG((2.+z0t)/Z0t)-PSIH2(I)
              PSIT=PSIQ
              PSIT2=PSIQ2






           ENDIF
        ENDIF


        UST(I)=KARMAN*WSPD(I)/PSIX
        UST_JUN(I)=UST(I)


        WSPDI(I)=SQRT(UX(I)*UX(I)+VX(I)*VX(I))
        IF ( PRESENT(USTM) ) THEN
        USTM(I)=0.5*USTM(I)+0.5*KARMAN*WSPDI(I)/PSIX
        ENDIF

        U10(I)=UX(I)*PSIX10/PSIX                                    
        V10(I)=VX(I)*PSIX10/PSIX                                   
        TH2(I)=THGB(I)+DTG*PSIT2/PSIT                                
        Q2(I)=QSFC(I)+(QX(I)-QSFC(I))*PSIQ2/PSIQ                   
        T2(I) = TH2(I)*(PSFCPA(I)/P1000mb)**ROVCP                     

        IF((XLAND(I)-1.5).LT.0.)THEN                                            
          UST(I)=AMAX1(UST(I),0.001)
        ENDIF                                                                    
        MOL(I)=KARMAN*DTG/PSIT/PRT                              
        DENOMQ(I)=PSIQ
        DENOMQ2(I)=PSIQ2
        DENOMT2(I)=PSIT2
        FM(I)=PSIX

        IF ((XLAND(I)-1.5).LT.0.) THEN
          FH(I)=PSIQ
        ELSE
          FH(I)=PSIT
        ENDIF

ENDDO  


                                                                                  

      IF ( PRESENT(SCM_FORCE_FLUX) ) THEN
         IF (SCM_FORCE_FLUX.EQ.1) GOTO 350
      ENDIF
      DO i=its,ite
        QFX(i)=0.                                                              
        HFX(i)=0.                                                              
      ENDDO
  350 CONTINUE                                                                   

      IF (ISFFLX.EQ.0) GOTO 410                                                
                                                                                 

                                                                                 
      DO 360 I=its,ite
        IF((XLAND(I)-1.5).GE.0)THEN                                            






          ZNT(I)=cha1d(i)*UST(I)*UST(I)/G+0.11*1.5E-5/UST(I)









          IF ( PRESENT(ISFTCFLX) ) THEN
             IF ( ISFTCFLX.NE.0 ) THEN






                ZW  = MIN((UST(I)/1.06)**(0.3),1.0)
                ZN1 = 0.011*UST(I)*UST(I)/G + OZO
                ZN2 = 10.*exp(-9.5*UST(I)**(-.3333)) + &
                       0.11*1.5E-5/AMAX1(UST(I),0.01)
                ZNT(I)=(1.0-ZW) * ZN1 + ZW * ZN2
                ZNT(I)=MIN(ZNT(I),2.85e-3)
                ZNT(I)=MAX(ZNT(I),1.27e-7)
             ENDIF
          ENDIF
          ZL(I) = ZNT(I)
        ELSE
          ZL(I) = 0.01
        ENDIF                                                                    
        FLQC(I)=RHOX(I)*MAVAIL(I)*UST(I)*KARMAN/DENOMQ(I)


        DTTHX=ABS(THX(I)-THGB(I))                                            
        IF(DTTHX.GT.1.E-5)THEN                                                   
          FLHC(I)=CPM(I)*RHOX(I)*UST(I)*MOL(I)/(THX(I)-THGB(I))          
        ELSE                                                                     
          FLHC(I)=0.                                                             
        ENDIF                                                                    
  360 CONTINUE                                                                   






     IF ( PRESENT(SCM_FORCE_FLUX) ) THEN
        IF (SCM_FORCE_FLUX.EQ.1) GOTO 405
     ENDIF

      DO 370 I=its,ite
        QFX(I)=FLQC(I)*(QSFC(I)-QX(I))                                     
        QFX(I)=AMAX1(QFX(I),0.)                                            
        LH(I)=XLV*QFX(I)
  370 CONTINUE                                                                 
                                                                                

      DO 400 I=its,ite
        IF(XLAND(I)-1.5.GT.0.)THEN                                           
          HFX(I)=FLHC(I)*(THGB(I)-THX(I)) 






        ELSEIF(XLAND(I)-1.5.LT.0.)THEN                                       
          HFX(I)=FLHC(I)*(THGB(I)-THX(I))                                
          HFX(I)=AMAX1(HFX(I),-250.)                                       
        ENDIF                                                                  
  400 CONTINUE                                                                 

  405 CONTINUE                                                                 
         
      DO I=its,ite
         IF((XLAND(I)-1.5).GE.0)THEN
           ZL(I)=ZNT(I)
         ELSE
           ZL(I)=0.01
         ENDIF



         CHS(I)=UST(I)*KARMAN/DENOMQ(I)
         CHS_ori(i) = CHS(i)

IF((XLAND(I)-1.5).LT.0 .and.                                               &
   ((MMINLU .eq. 'USGS' .and. (VEGTYP(I)>=2.and.VEGTYP(I)<=15)) .or.       &
   (MMINLU .eq. 'MODIFIED_IGBP_MODIS_NOAH'.and.(VEGTYP(I).ne.11).and.(VEGTYP(I).ne.13).and.(VEGTYP(I).ne.15).and.(VEGTYP(I).ne.17)))) THEN

Prc(I) = 0.5 + 0.3 * tanh ( 2. * Lc(I) * zol(I) / za(I) )
  chs_temp(i) = ( alog(za(i)/zpd_dt(i)) + chs_i1(i) - chs_i2(i) - PSIH_hat_chs(i))
  IF ( alog(za(i)/zpd_dt(i)) *0.9 < - chs_i1(i) + chs_i2(i) + psih_hat_chs(i) ) chs_temp(i) = alog(za(i)/zpd_dt(i)) * 0.1
  CHS(I) = 1./ ( 1./ (KARMAN * UST(i) / ( chs_temp(i) )) + &
 &               1./ (KARMAN * UST(i) / ( ALOG(KARMAN*UST(I)*ZL(I)/XKA+1) )) + &
 &  Prc(i) / (beta_old(i)*beta_old(i)*Uhc(i)) * ( exp( (zpd_dt(i)-zl(i))/(2.*beta_old(i)*beta_old(i)*Lc(i)) ) -1. ) )



 IF ( CHS(i) <= 0.00001 ) then
 CHS(i) = CHS_ori(i)
 ENDIF


ENDIF










         CQS2(I)=UST(I)*KARMAN/DENOMQ2(I)
         CQS2(I)=CQS2(I)*(CHS(I)/CHS_ori(I))
         CHS2(I)=UST(I)*KARMAN/DENOMT2(I)
         CHS2(I)=CHS2(I)*(CHS(I)/CHS_ORI(I))
 
     ENDDO
                                                                        
  410 CONTINUE                                                                   











   END SUBROUTINE YSL1D


   SUBROUTINE yslinit(errmsg,errflg)

    character(len=*),intent(out):: errmsg
    integer,intent(out):: errflg

    INTEGER                   ::      N
    REAL                      ::      zolf

    DO N=0,1000

       zolf = float(n)*0.01
       psim_stab(n)=psim_stable_full(zolf)
       psih_stab(n)=psih_stable_full(zolf)
 

       zolf = -float(n)*0.01
       psim_unstab(n)=psim_unstable_full(zolf)
       psih_unstab(n)=psih_unstable_full(zolf)

    ENDDO
    errmsg = 'sf_sfclayrev_init OK'
    errflg = 0

   END SUBROUTINE yslinit


  subroutine RPSI_hat(ZL, ZOL0, ZOL, ZZ, ZLVL, Lc, zpd_dt, cm2, ch2, & 
                  &D1, beta,PSIM_hat, PSIH_hat )     
  IMPLICIT NONE


  REAL,intent(IN) :: ZL,ZOL0,ZOL, ZZ, ZLVL, Lc, zpd_dt  
  REAL,intent(IN) :: beta
  REAL,intent(IN) :: cm2, ch2

  REAL,intent(INOUT) :: PSIM_hat, PSIH_hat
  REAL,intent(INOUT) :: D1

  REAL :: startz, endz,ii, startz1,  endz1, zhat
  REAL :: MOL
  REAL :: cm1, ch1
  REAL :: Prc, ff, R, VKC, phim_hat, phih_hat
  REAL :: betaNO, betaHF
  REAL :: G1, G2

  REAL, PARAMETER :: betaN = 0.374

  PSIM_hat = 0
  PSIH_hat = 0

  IF ( ZL == 0 .or. ZOL0 == 0 .or. ZOL == 0 .or. ZLVL == 0 ) then
  ENDIF

  IF (zol==0.) THEN
    MOL = 999999.
  ELSE
    MOL    = ZZ/zol      
  ENDIF

  R      = 0.1
  VKC    = 0.4
  Prc    = 0.5 + 0.3 * tanh ( 2 * Lc / MOL )
  ff     = 0.5 * ( sqrt(1 + 4*R*Prc ) -1 )
  Cm1 = (1 - ( VKC       / ( 2*beta*PHIM(zpd_dt,MOL) ) ))*exp(Cm2/2) 
  Ch1 = (1 - ( VKC * Prc / ( 2*beta*PHIH(zpd_dt,MOL) ) ))*exp(Ch2/2)
  Cm1 = (1 - ( VKC       / ( betaN*2 ) ))*exp(Cm2/2) 
  Ch1 = (1 - ( VKC * Prc / ( betaN*2 ) ))*exp(Ch2/2)
  D1  = 2*beta*beta*Lc    

  startz = zz
  endz   = zlvl*2

  PSIM_hat = 0; PSIH_hat = 0
  IF ( zz <= zlvl ) THEN
    startz1 = startz
    endz1 = zlvl
    G1 = (endz1-startz1)/2 * (-1/sqrt(3.)) + (startz1+endz1)/2
    G2 = (endz1-startz1)/2 * ( 1/sqrt(3.)) + (startz1+endz1)/2
    PSIM_hat = PSIM_hat + (endz1-startz1)/2 * ( (PHIM(G1,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G1  * (-1.) ))) / G1)&
     & + (PHIM(G2,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G2  * (-1.) ))) / G2) )
    PSIH_hat = PSIH_hat + (endz1-startz1)/2 * ( (PHIH(G1,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G1  * (-1.) ))) / G1)&
     & + (PHIH(G2,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G2  * (-1.) ))) / G2) )
  ENDIF

  DO zhat = zlvl, endz-zlvl/2, zlvl/2
    startz1 = zhat
    endz1 = zhat+zlvl/2

    G1 = (endz1-startz1)/2 * (-1/sqrt(3.)) + (startz1+endz1)/2
    G2 = (endz1-startz1)/2 * ( 1/sqrt(3.)) + (startz1+endz1)/2
    PSIM_hat = PSIM_hat + (endz1-startz1)/2 * ( (PHIM(G1,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G1  * (-1.) ))) / G1)&
     & + (PHIM(G2,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G2  * (-1.) ))) / G2) )
    PSIH_hat = PSIH_hat + (endz1-startz1)/2 * ( (PHIH(G1,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G1  * (-1.) ))) / G1)&
     & + (PHIH(G2,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G2  * (-1.) ))) / G2) )
   ENDDO
999 continue

  end subroutine

  subroutine PSI_hat(ZL, ZOL0, ZOL, ZZ, ZLVL, Lc, hc,& 
                  &D1, beta,PSIM_hat, PSIH_hat )     
  IMPLICIT NONE



  REAL,intent(IN) :: ZL,ZOL0,ZOL, ZZ, ZLVL, Lc, Hc

  REAL,intent(INOUT) :: PSIM_hat, PSIH_hat
  REAL,intent(INOUT) :: D1, beta

  REAL :: startz, endz,ii, zhat, startz1, endz1
  REAL :: MOL
  REAL :: cm1, cm2, ch1,ch2
  REAL :: Prc, ff, R, VKC, phim_hat, phih_hat
  REAL :: betaNO, betaHF, beta1, beta2
  REAL :: G1, G2
  REAL :: zpd_dt
  INTEGER :: ITER

  REAL, PARAMETER :: betaN = 0.374

  PSIM_hat = 0
  PSIH_hat = 0

  IF ( ZL == 0 .or. ZOL0 == 0 .or. ZOL == 0 .or. ZLVL == 0 ) then
  ENDIF

  IF (zol==0.) THEN
   MOL = 999999.
  ELSE
   MOL    = ZZ/zol      
  ENDIF

  R    = 0.1
  VKC  = 0.4
  ITER = 1
  zpd_dt = Hc*0.35

  beta = betaN   /PHIM(zpd_dt,MOL)

  betaHF = betaN   /PHIM(zpd_dt,MOL)
  betaNO = 0.4/2./PHIM(zpd_dt,MOL)
  beta   = betaNO + (BetaHF-BetaNO)/(1+2* ((abs(Lc/MOL+0.15))**1.5)  )
  IF ( Lc/MOL > -0.15 ) beta = betaHF

  IF ( beta <= 0.01 ) beta = 0.01

  Prc = 0.5 + 0.3 * tanh ( 2 * Lc / MOL )
  ff  = 0.5 * ( sqrt(1 + 4*R*Prc ) -1 )
  Cm2 = 0.5; Ch2 = 0.5

  Cm1 = (1 - ( VKC       / ( 2*beta*PHIM(zpd_dt,MOL) ) ))*exp(Cm2/2) 
  Ch1 = (1 - ( VKC * Prc / ( 2*beta*PHIH(zpd_dt,MOL) ) ))*exp(Ch2/2)
  Cm1 = (1 - ( VKC       / ( betaN*2 ) ))*exp(Cm2/2) 
  Ch1 = (1 - ( VKC * Prc / ( betaN*2 ) ))*exp(Ch2/2)
  D1  = 2*beta*beta*Lc    

  startz = zz
  endz   = zlvl*2

  PSIM_hat = 0; PSIH_hat = 0
  IF ( zz <= zlvl ) THEN
   startz1 = startz
   endz1 = zlvl
   G1 = (endz1-startz1)/2 * (-1/sqrt(3.)) + (startz1+endz1)/2
   G2 = (endz1-startz1)/2 * ( 1/sqrt(3.)) + (startz1+endz1)/2
   PSIM_hat = PSIM_hat + (endz1-startz1)/2 * ( (PHIM(G1,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G1  * (-1.) ))) / G1)&
   & + (PHIM(G2,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G2  * (-1.) ))) / G2) )
   PSIH_hat = PSIH_hat + (endz1-startz1)/2 * ( (PHIH(G1,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G1  * (-1.) ))) / G1)&
   & + (PHIH(G2,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G2  * (-1.) ))) / G2) )
  ENDIF

  DO zhat = zlvl, endz-zlvl/2, zlvl/2
   startz1 = zhat
   endz1 = zhat+zlvl/2
   G1 = (endz1-startz1)/2 * (-1/sqrt(3.)) + (startz1+endz1)/2
   G2 = (endz1-startz1)/2 * ( 1/sqrt(3.)) + (startz1+endz1)/2
   PSIM_hat = PSIM_hat + (endz1-startz1)/2 * ( (PHIM(G1,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G1  * (-1.) ))) / G1)&
    & + (PHIM(G2,MOL) * (1-(1. - cm1 * exp( cm2/d1 * G2  * (-1.) ))) / G2) )
   PSIH_hat = PSIH_hat + (endz1-startz1)/2 * ( (PHIH(G1,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G1  * (-1.) ))) / G1)&
   & + (PHIH(G2,MOL) * (1-(1. - ch1 * exp( ch2/d1 * G2  * (-1.) ))) / G2) )
  ENDDO

999 continue

end subroutine


      function PHIM(zzz,MOLe)
      real :: PHIM
      real :: zzz, MOLe
      IF (MOLe >= 999999. ) then
        PHIM=1.
      ELSE IF (MOLe > 0 .and. MOLe < 999999.) then
        PHIM=1+5.*(zzz/MOLe)
      ELSE IF (MOLe < 0 .and. MOLe > -999999.) then
        PHIM=(1-16.*(zzz/MOLe))**(-0.25)
      ELSE
        PHIM=1.
      ENDIF
      return
      end function


      function PHIH(zzz,MOLe)
      real :: PHIH
      real :: zzz, MOLe
      IF (MOLe >= 999999. ) then
        PHIH=1.
      ELSE IF (MOLe > 0 .and. MOLe < 999999. ) then
        PHIH=1+5.*(zzz/MOLe)
      ELSE IF (MOLe < 0 .and. MOLe > -999999.) then
        PHIH=(1-16.*(zzz/MOLe))**(-0.50)
      ELSE
        PHIH=1.
      ENDIF
      return
      end function

      function zolri(ri,z,z0)

      if (ri.lt.0.)then
        x1=-5.
        x2=0.
      else
        x1=0.
        x2=5.
      endif

      fx1=zolri2(x1,ri,z,z0)
      fx2=zolri2(x2,ri,z,z0)
      Do While (abs(x1 - x2) > 0.01)
      if(abs(fx2).lt.abs(fx1))then
        x1=x1-fx1/(fx2-fx1)*(x2-x1)
        fx1=zolri2(x1,ri,z,z0)
        zolri=x1
      else
        x2=x2-fx2/(fx2-fx1)*(x2-x1)
        fx2=zolri2(x2,ri,z,z0)
        zolri=x2
      endif

      enddo

      return
      end function



      function zolri2(zol2,ri2,z,z0)

      if(zol2*ri2 .lt. 0.)zol2=0.  

      zol20=zol2*z0/z 
      zol3=zol2+zol20 

      if (ri2.lt.0) then
      psix2=log((z+z0)/z0)-(psim_unstable(zol3)-psim_unstable(zol20))
      psih2=log((z+z0)/z0)-(psih_unstable(zol3)-psih_unstable(zol20))
      else
      psix2=log((z+z0)/z0)-(psim_stable(zol3)-psim_stable(zol20))
      psih2=log((z+z0)/z0)-(psih_stable(zol3)-psih_stable(zol20))
      endif

      zolri2=zol2*psih2/psix2**2-ri2

      return
      end function



      function zolri3(jri,jz,jz0,jzl,Lc,Hc,ust,xka)
      real :: zolri3
      real :: jri,jz,jz0,jzl, Lc, Hc, ust, xka
      real :: jx1, jx2, fjx1, fjx2
      real :: D1, beta, prc, ff
      Integer :: jjun 

      jjun =0
      if (jri.lt.0.)then
        jx1=-5.
        jx2=0.
      CALL PSI_hat(jzl*jx1/jz,jz0*jx1/jz,jx1,jz,jz, Lc, Hc, & 
                  &D1, beta, PSIM_hat, PSIH_hat)           
      fjx1=zolri4(jx1,jri,jz,jz0,jzl,PSIM_hat,PSIH_hat,ust,xka)
      fjx2=zolri4(jx2,jri,jz,jz0,jzl,0.,0.,ust,xka)
      else
        jx1=0.
        jx2=5.
      CALL PSI_hat(jzl*jx2/jz,jz0*jx2/jz,jx2,jz,jz, Lc, Hc,&  
                  &D1, beta, PSIM_hat, PSIH_hat)           
      fjx1=zolri4(jx1,jri,jz,jz0,jzl,0.,0.,ust,xka)
      fjx2=zolri4(jx2,jri,jz,jz0,jzl,PSIM_hat,PSIH_hat,ust,xka)
      endif

      Do While (abs(jx1 - jx2) > 0.01)
      if(abs(fjx2).lt.abs(fjx1))then
        jx1=jx1-fjx1/(fjx2-fjx1)*(jx2-jx1)
        CALL PSI_hat(jzl*jx1/jz,jz0*jx1/jz,jx1,jz,jz, Lc, Hc,&  
                    &D1, beta, PSIM_hat, PSIH_hat)           
        fjx1=zolri4(jx1,jri,jz,jz0,jzl,PSIM_hat,PSIH_hat,ust,xka)
        zolri3=jx1
      else
        jx2=jx2-fjx2/(fjx2-fjx1)*(jx2-jx1)
        CALL PSI_hat(jzl*jx2/jz,jz0*jx2/jz,jx2,jz,jz, Lc, Hc, & 
                    &D1, beta, PSIM_hat, PSIH_hat)           
        fjx2=zolri4(jx2,jri,jz,jz0,jzl,PSIM_hat,PSIH_hat,ust,xka)
        zolri3=jx2
      endif

      jjun = jjun + 1
      IF ( jjun > 100 ) then
         zolri3 = (jx1 + jx2 ) /2.
        EXIT
      END IF

      enddo

      return
      end function


      function zolri4(kzol2,kri2,kz,kz0,kzl,PSIM_hat,PSIH_hat,ust,xka)
      real :: zolri4
      real :: kzol20,kzol2,kri2,kz,kz0,kzl,PSIM_hat,PSIH_hat,ust,xka
      real :: kpsix2, kpsih2
      real :: temp, kzol3, kzol2l

      if(kzol2*kri2 .lt. 0.)kzol2=0.  

      kzol20=kzol2*kz0/kz 
      kzol3=kzol2+kzol20 
      kzol2l=kzol2*kzl/kz 

      if (kri2.lt.0) then
      kpsix2=log(kz/kz0)-(psim_unstable(kzol2)-psim_unstable(kzol20)-PSIM_hat)
      kpsih2=log(0.4*ust*kz/xka  +kz/kzl)-(psih_unstable(kzol2)-psih_unstable(kzol2l)-PSIH_hat)
      else

      kpsix2=log(kz/kz0)-(psim_stable(kzol2)-psim_stable(kzol20)-PSIM_hat)
      kpsih2=log(0.4*ust*kz/xka  +kz/kzl)-(psih_stable(kzol2)-psih_stable(kzol2l)-PSIH_hat)
      endif

      zolri4=kzol2*kpsih2/kpsix2**2-kri2

      return
      end function




      function psim_stable_full(zolf)
        psim_stable_full=-6.1*log(zolf+(1+zolf**2.5)**(1./2.5))
      return
      end function

      function psih_stable_full(zolf)
        psih_stable_full=-5.3*log(zolf+(1+zolf**1.1)**(1./1.1))
      return
      end function
      
      function psim_unstable_full(zolf)
        x=(1.-16.*zolf)**.25
        psimk=2*ALOG(0.5*(1+X))+ALOG(0.5*(1+X*X))-2.*ATAN(X)+2.*ATAN(1.)

        ym=(1.-10.*zolf)**0.33
        psimc=(3./2.)*log((ym**2.+ym+1.)/3.)-sqrt(3.)*ATAN((2.*ym+1)/sqrt(3.))+4.*ATAN(1.)/sqrt(3.)

        psim_unstable_full=(psimk+zolf**2*(psimc))/(1+zolf**2.)

      return
      end function



      function psih_unstable_full(zolf)
        y=(1.-16.*zolf)**.5
        psihk=2.*log((1+y)/2.)

        yh=(1.-34.*zolf)**0.33
        psihc=(3./2.)*log((yh**2.+yh+1.)/3.)-sqrt(3.)*ATAN((2.*yh+1)/sqrt(3.))+4.*ATAN(1.)/sqrt(3.)

        psih_unstable_full=(psihk+zolf**2*(psihc))/(1+zolf**2.)

      return
      end function


      function psim_stable(zolf)
      integer :: nzol
      real    :: rzol
        nzol = int(zolf*100.)
        rzol = zolf*100. - nzol
        if(nzol+1 .le. 1000)then
           psim_stable = psim_stab(nzol) + rzol*(psim_stab(nzol+1)-psim_stab(nzol))
        else
           psim_stable = psim_stable_full(zolf)
        endif
      return
      end function

      function psih_stable(zolf)
      integer :: nzol
      real    :: rzol
        nzol = int(zolf*100.)
        rzol = zolf*100. - nzol
        if(nzol+1 .le. 1000)then
           psih_stable = psih_stab(nzol) + rzol*(psih_stab(nzol+1)-psih_stab(nzol))
        else
           psih_stable = psih_stable_full(zolf)
        endif
      return
      end function
      
      function psim_unstable(zolf)
      integer :: nzol
      real    :: rzol
        nzol = int(-zolf*100.)
        rzol = -zolf*100. - nzol
        if(nzol+1 .le. 1000)then
           psim_unstable = psim_unstab(nzol) + rzol*(psim_unstab(nzol+1)-psim_unstab(nzol))
        else
           psim_unstable = psim_unstable_full(zolf)
        endif
      return
      end function

      function psih_unstable(zolf)
      integer :: nzol
      real    :: rzol
        nzol = int(-zolf*100.)
        rzol = -zolf*100. - nzol
        if(nzol+1 .le. 1000)then
           psih_unstable = psih_unstab(nzol) + rzol*(psih_unstab(nzol+1)-psih_unstab(nzol))
        else
           psih_unstable = psih_unstable_full(zolf)
        endif
      return
      end function

END MODULE module_sf_ysl


