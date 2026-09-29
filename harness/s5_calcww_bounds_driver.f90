program probe
  implicit none
  real, allocatable :: u(:,:,:), v(:,:,:), ww(:,:,:)
  real, allocatable :: mup(:,:), mub(:,:), msftx(:,:), msfty(:,:)
  real, allocatable :: msfux(:,:), msfuy(:,:), msfvx(:,:), msfvx_inv(:,:), msfvy(:,:)
  real :: c1h(1:40), c2h(1:40), dnw(1:40), rdx, rdy
  integer :: unit, c, target, its, ite, jts, jte
  character(len=256) :: path

  allocate(u(-4:240,1:40,-4:288), v(-4:240,1:40,-4:288))
  allocate(ww(-4:240,1:40,-4:288))
  allocate(mup(-4:240,-4:288), mub(-4:240,-4:288))
  allocate(msftx(-4:240,-4:288), msfuy(-4:240,-4:288))
  allocate(msfty(-4:240,-4:288), msfux(-4:240,-4:288))
  allocate(msfvx(-4:240,-4:288), msfvx_inv(-4:240,-4:288))
  allocate(msfvy(-4:240,-4:288))
  call get_command_argument(1,path)
  open(newunit=unit,file=trim(path),access='stream',form='unformatted',status='old')
  read(unit) u,v,mup,mub,c1h,c2h,msftx,msfty,msfux,msfuy, &
       msfvx,msfvx_inv,msfvy,dnw,rdx,rdy
  close(unit)

  do c=1,8
     target=117
     if (c>4) target=234
     its=1
     ite=235
     if (c==2 .or. c==4) ite=117
     if (c==6 .or. c==8) its=118
     jts=1
     jte=142
     if (mod((c-1)/2,2)==1) then
        jts=143
        jte=283
     endif
     ww=0.0
     call calc_ww_cp(u,v,mup,mub,c1h,c2h,ww,rdx,rdy, &
          msftx,msfty,msfux,msfuy,msfvx,msfvx_inv,msfvy,dnw, &
          1,235,1,283,1,40,-4,240,-4,288,1,40, &
          its,ite,jts,jte,1,40)
     write(path,'("out",i0,".bin")') c
     open(newunit=unit,file=trim(path),access='stream',form='unformatted',status='replace')
     write(unit) ww(target,1:40,1:283)
     close(unit)
  enddo
end program probe
