#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <dlfcn.h>
#include <unistd.h>
/* Portable source view: the executed copy used an absolute installed-DSO path.
 * Its exact SHA is recorded in raw/producer_source_hashes.json and the private
 * source is retained outside the public repository. */
#include "../../../../libtorch/bridge/kdm6_c_api.h"
int kdm6_step_c(const float *th, const float *qv, const float *qc, const float *qr, const float *qi, const float *qs, const float *qg, const float *nccn, const float *nc, const float *ni, const float *nr, const float *bg, const float *rho, const float *pii, const float *p, const float *delz, int im, int km, int jm, double dt, int flags, int value, float *th_out, float *qv_out, float *qc_out, float *qr_out, float *qi_out, float *qs_out, float *qg_out, float *nccn_out, float *nc_out, float *ni_out, float *nr_out, float *bg_out, kdm6_handle_t **handle, const float *xland, double land, double sea, float *rain, float *snow, float *graupel, float *rhog) {
 static int ncall=0; int callindex=++ncall;
 typedef int (*fn_t)(const float *th, const float *qv, const float *qc, const float *qr, const float *qi, const float *qs, const float *qg, const float *nccn, const float *nc, const float *ni, const float *nr, const float *bg, const float *rho, const float *pii, const float *p, const float *delz, int im, int km, int jm, double dt, int flags, int value, float *th_out, float *qv_out, float *qc_out, float *qr_out, float *qi_out, float *qs_out, float *qg_out, float *nccn_out, float *nc_out, float *ni_out, float *nr_out, float *bg_out, kdm6_handle_t **handle, const float *xland, double land, double sea, float *rain, float *snow, float *graupel, float *rhog);
 static fn_t real; if(!real) { const char *path=getenv("KDM6_ORIGINAL_DSO_PATH"); if(!path) _exit(90); void *h=dlopen(path,RTLD_NOW|RTLD_FIRST); if(!h) _exit(90); real=(fn_t)dlsym(h,"kdm6_step_c"); if ((void *)real == (void *)kdm6_step_c) _exit(94); }
 if(!real){fprintf(stderr,"CAPTURE: dlsym failed %s\n",dlerror()); _exit(91);}
 FILE *f=NULL; size_t n=(size_t)im*km*jm, m=(size_t)im*jm;
 fprintf(stderr,"CAPTURE call=%d dimensions=%d,%d,%d dt=%.17g\n",callindex,im,km,jm,dt);
 if(callindex==2){f=fopen(getenv("KDM_CAPTURE_PATH"),"wb"); if(!f) _exit(92); int hdr[]={im,km,jm,flags,value,callindex}; fwrite(hdr,sizeof(int),6,f); fwrite(&dt,sizeof(dt),1,f); fwrite(&land,sizeof(land),1,f); fwrite(&sea,sizeof(sea),1,f);
 fwrite(th,sizeof(float),n,f);
 fwrite(qv,sizeof(float),n,f);
 fwrite(qc,sizeof(float),n,f);
 fwrite(qr,sizeof(float),n,f);
 fwrite(qi,sizeof(float),n,f);
 fwrite(qs,sizeof(float),n,f);
 fwrite(qg,sizeof(float),n,f);
 fwrite(nccn,sizeof(float),n,f);
 fwrite(nc,sizeof(float),n,f);
 fwrite(ni,sizeof(float),n,f);
 fwrite(nr,sizeof(float),n,f);
 fwrite(bg,sizeof(float),n,f);
 fwrite(rho,sizeof(float),n,f);
 fwrite(pii,sizeof(float),n,f);
 fwrite(p,sizeof(float),n,f);
 fwrite(delz,sizeof(float),n,f);
 fwrite(xland,sizeof(float),m,f); fflush(f); }
 int rc=real(th, qv, qc, qr, qi, qs, qg, nccn, nc, ni, nr, bg, rho, pii, p, delz, im, km, jm, dt, flags, value, th_out, qv_out, qc_out, qr_out, qi_out, qs_out, qg_out, nccn_out, nc_out, ni_out, nr_out, bg_out, handle, xland, land, sea, rain, snow, graupel, rhog);
 if(f){ fwrite(&rc,sizeof(rc),1,f);
 fwrite(th_out,sizeof(float),n,f);
 fwrite(qv_out,sizeof(float),n,f);
 fwrite(qc_out,sizeof(float),n,f);
 fwrite(qr_out,sizeof(float),n,f);
 fwrite(qi_out,sizeof(float),n,f);
 fwrite(qs_out,sizeof(float),n,f);
 fwrite(qg_out,sizeof(float),n,f);
 fwrite(nccn_out,sizeof(float),n,f);
 fwrite(nc_out,sizeof(float),n,f);
 fwrite(ni_out,sizeof(float),n,f);
 fwrite(nr_out,sizeof(float),n,f);
 fwrite(bg_out,sizeof(float),n,f);
 fwrite(rain,sizeof(float),m,f); fwrite(snow,sizeof(float),m,f); fwrite(graupel,sizeof(float),m,f); fwrite(rhog,sizeof(float),n,f); if(fclose(f)) _exit(93); fprintf(stderr,"CAPTURE complete dimensions=%d,%d,%d call=%d rc=%d\n",im,km,jm,callindex,rc); } return rc; }
