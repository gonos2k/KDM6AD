# Stage A Re-architecture Blueprint — sequential melt/freeze flow

Re-architect `kdm62d_one_step{,_torch}` so melt(D1)+freeze(D2-D4) are INLINE pre-rate mutations of a working state, with full preamble+aux rebuild on the mutated state, before warm/cold rates + budgets. Restores Fortran's sequential flow + autodiff sensitivity. Generated 2026-05-31 from design workflow w7l9ybfcd.

> **Single biggest risk:** the 806× aux-staleness — the rebuild MUST replace BOTH `pre` (slopes/work2/ProgB) AND `aux` (n0*/work1*/rslopec*) together; and the D1-D4 terms MUST be stripped from `state_update` or melt/freeze is applied twice.

## Fortran ground-truth flow (module_mp_kdm6.f90:1222-1643)

Stage-A ground-truth order from module_mp_kdm6.f90:1222-1643. After per-substep sedimentation and BEFORE the warm rate loop (1643), Fortran executes a strict SEQUENTIAL chain on the working state (qrs, qci, t, nrs, nci, brs): (1) D1 MELT block (1222-1295) — snow-melt psmlt, graupel-melt pgmlt, and instantaneous ice->cloud pimlt, each applied INLINE to qrs/qci/t/nrs/brs as it is computed; (2) a DSD re-slope refresh #2 = ProgB_param + slope_kdm6 on the post-melt snapshot (qrs_tmp/qci_tmp/nrs_tmp seeded at 1331-1340, calls 1342-1349), followed by a per-cell cloud-DSD + n0r/n0c/n0i + lamdr/lamdc/lamdi snap block (1372-1430); (3) homogeneous freeze (1360-1370, LATER STAGE — record only) sits at the TOP of that same k-loop BEFORE the cloud-DSD recompute, so the lamda snap reads post-homog-freeze qci; (4) the FREEZE block D2 contact (pinuc/ninuc 1435-1457), D3 Bigg-cloud (pfrzdtc/nfrzdtc 1462-1487), D4 Bigg-rain (pfrzdtr/nfrzdtr 1492-1511), all applied INLINE and SEQUENTIALLY with caps reading the running (already-depleted) qci(1)/qrs(1); (5) a nonneg clamp (1515-1521) then re-slope refresh #3 = ProgB_param + slope_kdm6 on the post-freeze snapshot (seed 1526-1535, calls 1537-1544) + cloud-DSD/n0*/lamda-snap recompute (1546-1615) + avedia/sigma (1620-1623) + work1/work2 diffac/venfac rebuild (1627-1632). Only THEN does the warm rate loop start at 1643. Stage A must reproduce: D1 melt inline -> reslope#2 -> [homog freeze: later] -> D2->D3->D4 freeze inline with sequential caps -> reslope#3 -> warm/cold. The reslope is two FULL ProgB+slope passes plus per-cell n0/lamda snap recomputes, NOT just a single aux rebuild — under-rebuilding aux is exactly what caused the 806x regression.

<details><summary>Detailed Fortran flow</summary>

```
All line numbers from /Users/yhlee/KDM6AD/KIM-meso_v1.0/phys/module_mp_kdm6.f90. Entry context: the WHOLE chain below sits inside the per-substep loop; melt runs in a k=kte..kts (top-down) loop (1222), all later blocks in k=kts..kte loops. t0c=273.15. xlf=xls-xl, reset to xlf0 when supcol<0.

==================================================================
D1 MELT — inline pre-rate mutations (loop 1222-1295, top-down)
==================================================================
Per-cell preamble (1224-1228): supcol=t0c-t; if supcol<0 xlf=xlf0; n0so=(n0s)/g1pms/rslopemu(:,2); n0go=(n0g)/g1pmg/rslopemu(:,3); n0sfac=max(min(exp(alpha*supcol),n0smax/n0s),1.). NOTE n0so/n0go/n0sfac are recomputed here from the CURRENT (post-sediment) rslopemu — they feed psmlt/pgmlt below.

Melt only fires where t>t0c (gate at 1229). work2=venfac(p,t,den) recomputed at 1234.

D1a snow melt psmlt (1235-1254), gated qrs(:,2)>0:
  coeres (1237-1238) = rslope2(:,2)*sqrt(rslope(:,2)*rslopeb(:,2))*rslopemu(:,2)
  psmlt (1239-1241) = xka(t,den)/xlf*(t0c-t)*n0sfac*pi/2.*((precs1)*n0so*rslope2(:,2)*rslopemu(:,2)+(precs2)*n0so*work2*coeres)/den
  psmlt (1242) = min(max(psmlt*dtcld, -qrs(:,2)), 0.)   [cap against current qs, sign<=0]
  MUTATIONS:
    if qrs(:,2)>qcrmin (1247): sfac=rslope(:,2)*n0so*n0sfac/qrs(:,2); nrs(:,1) -= sfac*psmlt   (1248-1249)  [rain number GAINS]
    qrs(:,2) += psmlt    (1251)  [snow loses]
    qrs(:,1) -= psmlt    (1252)  [rain gains]
    t        += xlf/cpm*psmlt  (1253)  [cooling, psmlt<=0]

D1b graupel melt pgmlt (1259-1279), gated qrs(:,3)>0:
  coeres (1261-1262) = rslope2(:,3)*sqrt(rslope(:,3)*rslopeb(:,3))*rslopemu(:,3)
  pgmlt (1263-1265) = xka(t,den)/xlf*(t0c-t)*pi/2.*((precg1)*n0go*rslope2(:,3)*rslopemu(:,3)+(precg2)*n0go*work2*coeres)/den   [NOTE: no n0sfac factor, precg2 is the per-cell array]
  pgmlt (1266) = min(max(pgmlt*dtcld, -qrs(:,3)), 0.)
  MUTATIONS:
    if qrs(:,3)>qcrmin (1271): gfac=rslope(:,3)*n0go/qrs(:,3); nrs(:,1) -= gfac*pgmlt   (1272-1273)
    qrs(:,3) += pgmlt   (1275)  [graupel loses]
    qrs(:,1) -= pgmlt   (1276)  [rain gains]
    t        += xlf/cpm*pgmlt   (1277)
    brs(:)   += pgmlt/rhox      (1278)  [graupel rime-volume mutated — easy to miss]

D1c instantaneous ice->cloud pimlt (1286-1292), STILL inside t>t0c, gated qci(:,2)>0:
  This is NOT a /dtcld rate — it is a total instantaneous transfer of all cloud ice to cloud water:
    qci(:,1) += qci(:,2)   (1287)  [cloud water gains all ice mass]
    nci(:,1) += nci(:,2)   (1288)  [cloud water number gains all ice number]
    t        -= xlf/cpm*qci(:,2)  (1289)  [cooling by melting all ice; note MINUS]
    qci(:,2) = 0.   (1290)
    nci(:,2) = 0.   (1291)
  (endif 1292 closes qci(2)>0; endif 1293 closes the t>t0c gate.)

Surface accumulation (1299-1328) runs between melt and reslope#2 (rainncv/snowncv/graupelncv/sr from fall(:,kts,:)) — not a state mutation of qrs/qci, sedimentation bookkeeping; record but not part of the DSD chain.

==================================================================
RE-SLOPE REFRESH #2 — ProgB + slope on POST-MELT state (1331-1430)
==================================================================
Seed temp arrays from the MUTATED state (1331-1340):
  qrs_tmp(:,1..3)=qrs(:,1..3); qci_tmp=qci(:,2); nci_tmp=nci(:,2); nrs_tmp=nrs(:,1)
  [NOTE: slope's qci/nci inputs are the ICE channel qci(:,2)/nci(:,2), NOT cloud water.]
ProgB_param(brs,qrs_tmp,rhox,...) (1342-1345): rebuilds graupel-density-dependent params from post-melt brs+qg: n0g, precg2, bvtg/bvtg1..4, rslopegbmax/rslopegmax, pidn0g, g1p* graupel gammas, avtg/pvtg.
slope_kdm6(qrs_tmp,qci_tmp,nrs_tmp,nci_tmp,den_tmp,...) (1347-1349): full DSD reslope — see slope body below. Recomputes for species 1=rain,2=snow,3=graupel,4=ice: n0sfac, rslope, rslopeb, rslopemu, rsloped, rslope2, rslope3, and fall speeds vt(1..4)/vtn(1..2). Each species gated qcrmin/qmin/nrmin with the *max snap fallbacks.

Per-cell CLOUD-DSD + n0/lamda snap block (1351-1430), k=kts..kte:
  recompute supcol, xlf (1353-1355).
  [HOMOG FREEZE 1360-1370 lives HERE at top of loop — see next section.]
  Cloud-water DSD (1372-1384): if qci(:,1)<=qmin OR nci(:,1)<=ncmin -> rslopecmu/rslopec/rslopec2/rslopec3/rslopecd = *max constants; else rslopec=1./lamdac(qci(:,1),den,nci(:,1)); rslopec2=rslopec^2; rslopec3=rslopec^3; rslopecmu=rslopec^muc; rslopecd=rslopec^dmc.
  Intercepts (1385-1387): n0r=nrs(:,1)/(rslope(:,1)*rslopemu(:,1)*g1pmr); n0c=(muc+1)*nci(:,1)/(rslopec*rslopecmu); n0i=nci(:,2)/(rslope(:,4)*rslopemu(:,4)*g1pmi).
  Rain lamda snap (1389-1402): if qrs(:,1)>=qcrmin & nrs(:,1)>=nrmin -> lamdr_tmp=exp(log(pidnr*nrs(:,1)/(den*qrs(:,1)))/dmr); n0r recompute; if lamdr<=lamdarmin or >=lamdarmax: clamp lamdr, MUTATE nrs(:,1)=den*qrs(:,1)*lamdr^dmr/pidnr, recompute n0r. (nrs MUTATED here.)
  Cloud lamda snap (1403-1416): symmetric, MUTATES nci(:,1) at the clamps.
  Ice lamda snap (1417-1430): gate qci(:,2)>=1.e-14; MUTATES nci(:,2) at the clamps. (Note 1e-14 ice gate, distinct from qmin.)

==================================================================
HOMOG FREEZE (1360-1370) — LATER STAGE, record only
==================================================================
At top of the 1351 k-loop, BEFORE the cloud-DSD recompute:
  if supcol>40. AND qci(:,1)>0. :
    qci(:,2) += qci(:,1)   (1361)  [all cloud water -> ice mass]
    nci(:,2) += nci(:,1)   (1362)
    t        += xlf/cpm*qci(:,1)  (1367)  [PLUS: freezing release]
    qci(:,1) = 0.   (1368)
    nci(:,1) = 0.   (1369)
  Consequence: the cloud-DSD/n0c/lamda-snap recompute at 1372-1430 reads the POST-homog-freeze qci(:,1)=0/qci(:,2)+=, so n0c falls to the *max fallback and n0i rises. This is the in-loop reslope that makes deep-cold deposition see frozen ice — the staleness this guards against is exactly the 806x class. Stage A does NOT implement this (it is the later homog-freeze stage), but the ordering note is: homog-freeze precedes the cloud-DSD recompute and precedes D2/D3/D4.

==================================================================
FREEZE D2/D3/D4 — inline sequential mutations w/ running caps (1435-1511)
==================================================================
Same k-loop (1351-1513). supcol/xlf already set (1353-1355).

D2 CONTACT nucleation pinuc/ninuc (1435-1457), gate supcol>2. AND qci(:,1)>qmin:
  supcolt=min(supcol,70.) (1436); Nic=exp(-2.80+0.262*supcolt)*1000 (1437)
  ele1=7.37*t/(288.*10.*p)/100 (1438); ele2=4.*pi*1.38e-23/(6.*pi*Rcn) (1439)
  difa=ele2*t*(1.+ele1/Rcn)/(viscos(t,den)*den) (1441)
  pinuc = min(cmc*difa*2.*pi*Nic*n0c/den/(muc+1)*g4pmc*rslopecmu*rslopec3*rslopec2*dtcld, qci(:,1))  (1442-1443) [cap vs CURRENT qc]
  MUTATIONS:
    if nci(:,1)>ncmin (1448): ninuc=min(difa*2.*pi*Nic*n0c/(muc+1)*g1pmc*rslopecmu*rslopec2*dtcld, nci(:,1)); nci(:,1)-=ninuc; nci(:,2)+=ninuc  (1449-1452)
    qci(:,1) -= pinuc   (1454)  [cloud water depleted]
    qci(:,2) += pinuc   (1455)  [ice gains]
    t        += xlf/cpm*pinuc  (1456)

D3 Bigg CLOUD freeze pfrzdtc/nfrzdtc (1462-1487), gate supcol>0. AND qci(:,1)>qmin:
  supcolt=min(supcol,70.) (1463)
  pfrzdtc = min(cmc*cmc*pfrz1*n0c/den/denr/(muc+1)*(exp(pfrz2*supcolt)-1.)*g1p2dcomuc1*rslopecmu*rslopecd*rslopecd*rslopec*dtcld, qci(:,1))  (1464-1469)
  ** SEQUENTIAL CAP: the min(...,qci(:,1)) at 1469 reads qci(:,1) ALREADY DEPLETED by pinuc at 1454. This is the exact sequential-cap the ports break (they cap both D2 and D3 against entry qc).**
  MUTATIONS:
    if nci(:,1)>ncmin (1474): nfrzdtc=min(cmc*pfrz1*n0c/denr/(muc+1)*(exp(pfrz2*supcolt)-1.)*g1pdcomuc1*rslopecmu*rslopec*rslopecd*dtcld, nci(:,1)); nci(:,1)-=nfrzdtc; nci(:,2)+=nfrzdtc  (1476-1482)
    qci(:,1) -= pfrzdtc   (1484)
    qci(:,2) += pfrzdtc   (1485)
    t        += xlf/cpm*pfrzdtc  (1486)

D4 Bigg RAIN freeze pfrzdtr/nfrzdtr (1492-1511), gate supcol>0. AND qrs(:,1)>0.:
  supcolt=min(supcol,70.) (1493)
  pfrzdtr = min(cmr*cmr*pfrz1*n0r/den/denr*(exp(pfrz2*supcolt)-1.)*rsloped(:,1)*rsloped(:,1)*rslopemu(:,1)*rslope(:,1)*g1p2drmr*dtcld, qrs(:,1))  (1494-1496) [cap vs CURRENT qr; note qr was already mutated by D1 melt at 1252/1276]
  MUTATIONS:
    if nrs(:,1)>nrmin (1501): nfrzdtr=min(cmr/denr*pfrz1*n0r*(exp(pfrz2*supcolt)-1.)*g1pdrmr*rslope(:,1)*rsloped(:,1)*rslopemu(:,1)*dtcld, nrs(:,1)); nrs(:,1)-=nfrzdtr  (1502-1505)
    qrs(:,3) += pfrzdtr   (1507)  [graupel gains frozen rain]
    brs(:)   += pfrzdtr/denr  (1508)  [graupel rime-volume]
    t        += xlf/cpm*pfrzdtr  (1509)
    qrs(:,1) -= pfrzdtr   (1510)  [rain depleted]
  (endif 1511, enddo 1512-1513.)

Nonneg clamp (1515-1521): nrs(:,1)=max(.,0); nci(:,1)=max(.,0); nci(:,2)=max(.,0).

==================================================================
RE-SLOPE REFRESH #3 — ProgB + slope on POST-FREEZE state (1526-1633)
==================================================================
Re-seed temp arrays from the post-freeze MUTATED state (1526-1535): qrs_tmp(1..3), qci_tmp=qci(:,2), nci_tmp=nci(:,2), nrs_tmp=nrs(:,1).
ProgB_param (1537-1540): graupel-density params rebuilt from post-freeze brs+qg (D4 changed both qrs(:,3) and brs).
slope_kdm6 (1542-1544): full DSD reslope on post-freeze qrs_tmp/qci_tmp/nrs_tmp/nci_tmp.

Per-cell recompute (1546-1623), k=kts..kte:
  Cloud-water DSD (1553-1565): identical structure to 1372-1384 (rslopec/2/3/mu/d from lamdac(qci(:,1),den,nci(:,1)) on post-freeze cloud water; note D3 may have depleted qc to <=qmin -> *max fallback). NOTE ORDER of the *max assignments differs cosmetically (1554-1558 vs 1373-1377) but values identical.
  Intercepts (1568-1572): n0r, n0c, n0i AS 1385-1387, PLUS here it also recomputes n0so=(n0s)/g1pms/rslopemu(:,2) (1571) and n0go=(n0g)/g1pmg/rslopemu(:,3) (1572) — the melt-block recomputed these at 1226-1227, so they are refreshed again here on the post-freeze rslopemu.
  Rain lamda snap (1574-1587): MUTATES nrs(:,1) at clamps.
  Cloud lamda snap (1588-1601): MUTATES nci(:,1) at clamps.
  Ice lamda snap (1602-1615): gate qci(:,2)>=1.e-14; MUTATES nci(:,2) at clamps.
  avedia/sigma (1620-1623): avedia(:,1)=rslopec*(g3pmc)^(1/3); avedia(:,2)=rslope(:,1)*(g4pmr/g1pmr)^(1/3); avedia(:,3)=rslope(:,4)*(g4pmi/g1pmi)^(1/3); sigma(:,1)=rslopec*(g6pmc-g3pmc^2)^(1/6).
  work1/work2 rebuild (1627-1632, separate k-loop): work1(:,1)=diffac(xl,p,t,den,qs(:,1)); work1(:,2)=diffac(xls,p,t,den,qs(:,2)); work2=venfac(p,t,den). These read the post-freeze t (D2/D3/D4 all added latent heat) — the warm/cold deposition rates at 1643+ consume work1/work2.

ONLY AFTER all of the above does the warm rate loop begin (1643). supsat=max(q,qmin)-qs(:,1); satdt=supsat/dtcld (1645-1646).

==================================================================
slope_kdm6 body (3377-3507) — what reslope#2/#3 recompute
==================================================================
For each cell, n0sfac=max(min(exp(alpha*supcol),n0smax/n0s),1.) (3431). Then per species with gate->*max fallback else lamda-based:
  rain(1) gate qrs(1)<=qcrmin OR nrs<=nrmin (3432); else rslope=min(1./lamdar(qrs1,den,nrs),1.e-3) (3440), rslopeb=rslope^bvtr, rslopemu=rslope^mur, rsloped=rslope^dmr, rslope2=rslope^2, rslope3=rslope^3.
  snow(2) gate qrs(2)<=qcrmin (3447); else rslope=1./lamdas(qrs2,den,n0sfac) (3455) [uses n0sfac, dms+1 exponent], then b/mu/d/2/3.
  graupel(3) gate qrs(3)<=qcrmin (3462); else rslope=1./lamdag(qrs3,den) (3470) [pidn0g per-cell, dmg+1 exponent], rslopeb=rslope^bvtg(i,k) (per-cell bvtg).
  ice(4) gate qci<=qmin (3477); else rslope=max(min(1./lamdai(qci,den,nci),1./lamdaimin),1./lamdaimax) (3485) [note ice rslope itself clamped to lamdaimin/max].
  Fall speeds (3493-3504): vt(1)=pvtr*rslopeb1*denfac, vt(2)=pvts*rslopeb2*denfac, vt(3)=pvtg*rslopeb3*denfac, vt(4)=pvti*rslopeb4*denfac (zeroed if q<=0); vtn(1)=pvtrn*rslopeb1*denfac, vtn(2)=pvtin*rslopeb4*denfac.
  lamda funcs (3417-3423): lamdar=exp(log(pidnr*z/(x*y))/dmr); lamdas=exp(log(pidn0s*z/(x*y))/(dms+1)); lamdag=exp(log(pidn0g/(x*y))/(dmg+1)); lamdai=exp(log(pidni*z/(x*y))/dmi).

==================================================================
STAGE-A ORDER SUMMARY (what to reproduce, in order)
==================================================================
1) D1 melt INLINE on working state: n0so/n0go/n0sfac recompute -> psmlt(snow,1239,cap-qs) [mut nrs,qs,qr,t] -> pgmlt(graupel,1263,cap-qg) [mut nrs,qg,qr,t,brs] -> pimlt(ice->cloud,1287, instantaneous total) [mut qc,nc,t,zero qi/ni]. All gated t>t0c.
2) RESLOPE #2 = ProgB_param(1342) + slope_kdm6(1347) on post-melt qrs_tmp/qci2_tmp/nrs/nci2, THEN per-cell cloud-DSD(rslopec*), n0r/n0c/n0i, and rain/cloud/ice lamda-snaps that MUTATE nrs/nci(1)/nci(2) (1372-1430).
   [LATER STAGE marker: homog-freeze 1360-1370 inserts at top of this loop before the cloud-DSD recompute — do not implement in Stage A, but its slot is here.]
3) FREEZE D2(pinuc/ninuc 1442, cap-qc) -> D3(pfrzdtc/nfrzdtc 1464, cap vs ALREADY-DEPLETED qc at 1469) -> D4(pfrzdtr/nfrzdtr 1494, cap-qr), all INLINE+SEQUENTIAL, mutating qc/nc/qi/ni/qr/nr/qg/brs/t. Nonneg clamp 1515.
4) RESLOPE #3 = ProgB_param(1537) + slope_kdm6(1542) on post-freeze state, THEN per-cell cloud-DSD + n0r/n0c/n0i + n0so/n0go + lamda-snaps(mut nrs/nci) + avedia/sigma + work1/work2 diffac/venfac rebuild on post-freeze t (1546-1632).
5) warm loop 1643 reads the post-melt/post-freeze/post-reslope#3 state.

Conservation-limiter implication: the limiter reservoirs (value=max(floor,reservoir)) must read qrs/qci/nrs reflecting steps 1+3 (melt+freeze already applied), not the entry snapshot. Two FULL ProgB+slope passes + the per-cell n0/lamda-snap recomputes are mandatory between melt->freeze and freeze->warm; doing the freeze without rebuilding n0c/n0i/rslopec (reslope#3) reproduces the 806x over-deposition regression.
```
</details>

## Aux-rebuild mechanism (feasibility crux)

FEASIBLE. STAGE A aux-rebuild is self-contained + autodiff-safe in both ports. RECOMMENDED MECHANISM: add kdm6::rebuild_aux(working_state, forcing, full_params, sea_mask?) in coordinator.cpp that re-runs preamble() + diag_cloud_slope_torch() + build_default_aux() on the post-melt/freeze working state, called inside kdm62d_one_step AFTER inline melt(D1)+freeze(D2/D3/D4) and BEFORE warm_phase/cold_phase/scale_rates. build_default_aux (runtime.cpp:103) and preamble (coordinator.cpp:328) are both pure tensor functions re-callable on arbitrary state; preamble is ALREADY re-run mid-step at runtime.cpp:288 for sedimentation, so the pattern is proven. Minimal set = whole preamble + whole build_default_aux (NOT a subset) since melt/freeze touch t/qc/qr/qs/qg/qi/nc/nr/ni. Autodiff-safe: torch ops only, NO .item()/NoGradGuard in either function.

<details><summary>Aux-rebuild findings + risks</summary>

=== Q4: CLEANEST INLINE REBUILD MECHANISM (recommendation) ===
Do NOT use the staging-fix localized inline recompute (the partial recompute that caused the 806x regression — it rebuilt some n0 numerators without the matching slope/work1 denominators and without progb/work2, leaving cold deposition reading a self-inconsistent aux). Do NOT re-call the full runtime kdm6_fn (it owns state<->coord conversion, xland plumbing, sedimentation, ABI).

RECOMMENDED — a single dedicated helper, identical in shape both ports:
C++ (in coordinator.cpp, declared in coordinator.h):
  CoordinatorAuxDiagnostics rebuild_aux(const CoordinatorState& s, const CoordinatorForcing& f, const CoordinatorParams& p, const c10::optional<torch::Tensor>& qcr_override) {
     auto pre = preamble(s, f, p);                              // refresh ALL slopes + work2 + progb
     auto rslopec = pre.rslopec;                                // already built by preamble (coordinator.cpp:346)
     auto aux = build_default_aux(s, f, rslopec, p.thermo);     // n0r/n0i/n0c/work1*/avedia_i/rslopec*
     if (qcr_override) aux.qcr = *qcr_override;                 // qcr is sea_mask-only, carry forward
     return aux; }   // also return pre so warm/cold/mf consume the SAME refreshed slopes
Practically: have rebuild return BOTH the refreshed PreambleOutputs and the aux, because warm_phase/cold_phase/melt_freeze consume pre.slope.* + pre.work2 + pre.rslopec (coordinator.cpp:450-472 via pre_warm_view/pre_cold_view/pre_mf_view). If you rebuild aux but keep the stale `pre`, cold/mf still read entry-state slopes — the same stale-aux class. So the rebuild must replace BOTH `pre` and `aux` for the post-freeze working state. The single line `auto pre = preamble(working_state, forcing, full_params);` already does the slope half; build_default_aux does the n0/work1 half. Promote build_default_aux out of runtime.cpp's anonymous namespace (declare in coordinator.h, move def to coordinator.cpp) so kdm62d_one_step can call it.

Restructured kdm62d_one_step (STAGE A target):
  state_pre = state
  pre0 = preamble(state_pre, forcing, full_params)              // for D1 melt + D2/D3/D4 freeze rates (entry slopes)
  aux0 = rebuild_aux(state_pre, ...)                            // OR reuse the caller-supplied aux for the freeze rates
  working = apply_melt_inline(state_pre, ...)                   // D1 mutates qs/qg/qi/ni/t/qr/qc  (NEW)
  working = apply_freeze_inline(working, ...)                   // D2->D3->D4 sequential caps on running qc/qr (NEW)
  pre = preamble(working, forcing, full_params)                // RE-SLOPE #2/#3
  aux = build_default_aux(working, forcing, pre.rslopec, thermo); aux.qcr = carried
  warm_out = warm_phase(working, forcing, pre_warm_view(pre), aux.n0r, aux.work1_r, aux.qcr, ...)
  cold_out = cold_phase(working, forcing, pre_cold_view(pre), warm_out.prevp, aux.n0i, ...)
  // D5 enhanced-melt still computed here (reads cold_out HM-adj); D1-D4 already applied to `working`
  scaled = scale_rates_for_conservation(working, pre.supcol, warm_out, cold_out, mf_remainder, dtcld)  // reservoirs now post-melt/freeze
  new_state = state_update(working, pre_core_view(pre), scaled..., ...)   // and REMOVE the D1-D4 terms from state_update (they're already in `working`)
  ... reclass/satadj/cleanup/DSD tail unchanged

KEY STATE-UPDATE CHANGE: once melt/freeze are applied to `working` inline, their mass/number/T deltas MUST be removed from state_update's dqc/dqr/dqs/dqg/dqi/dnc/dnr/dni/brs/T expressions (coordinator.cpp:853,869,889,905,908,920,931,947,959,981-986,1010-1025) to avoid DOUBLE-COUNTING — this is the trap. Fortran does not re-apply psmlt/pimlt/pinuc/pfrzdtc/pfrzdtr after f90:2395 precisely because they were applied inline; the ports currently DO re-apply them (FORTRAN_FLOW_ORDER_CHECKLIST.md:150,173).

PYTHON: identical shape. Python preamble_torch (coordinator.py:112) is already pure + re-callable; Python has NO build_default_aux equivalent (aux is built only in tests, coordinator.py CoordinatorAuxDiagnostics:1369 + test_coordinator.py). Python runtime.py is a STUB (_kdm6_pure raises NotImplementedError, runtime.py:217), so the differentiable operational path is C++-only; Python is the oracle. Add a Python rebuild_aux mirroring the C++ one (re-run preamble_torch + a new build_default_aux_torch) so the oracle parity test exercises the same rebuild.

**Risks:** CORRECTNESS RISKS (aux-rebuild is paramount per the 806x history):
1. DOUBLE-COUNT trap: if melt/freeze become inline mutations of `working` but state_update still adds psmlt/pgmlt/pimlt/pinuc/pfrzdtc/pfrzdtr/their T+brs terms (coordinator.cpp:853-1025), every melt/freeze is applied twice. Must strip those from state_update. (FORTRAN_FLOW_ORDER_CHECKLIST.md:150,173.)
2. STALE-pre trap (the 806x class): rebuilding `aux` but NOT `pre` leaves cold_phase/melt_freeze reading entry-state pre.slope.*/pre.work2 (coordinator.cpp:457-472). The rebuild MUST replace BOTH preamble outputs AND aux for the working state. The 806x regression came from a partial recompute that refreshed n0i numerator but not the slope/work1 denominators+progb — self-inconsistent aux.
3. build_default_aux is in an ANONYMOUS namespace in runtime.cpp (line 103-165), invisible to coordinator.cpp. Must be promoted (decl in coordinator.h + def moved/duplicated to coordinator.cpp). It also OMITS the Fortran lamda-snap number back-mutation of nr/nci (runtime.cpp:84-90 header note); the rebuild inherits that approximation. For STAGE A parity this is probably acceptable (matches current entry-state behavior) but is a known divergence vs f90:1393-1428.
4. n0so/n0go (constants) and qcr (sea_mask-only) are state-INDEPENDENT — carry them forward, don't recompute from a possibly-changed sea path.
5. work2 lives in PreambleOutputs, not aux — easy to forget; re-running preamble covers it.
6. Autodiff: confirmed clean — build_default_aux + preamble are pure torch ops, no .item()/NoGradGuard (the only NoGradGuard+.item() is runtime.cpp:300-310 mstep, sedimentation, untouched by this refactor). Re-invoking threads grad through melt/freeze deltas as required.
7. STAGE A scope guard: sedimentation-per-substep (runtime.cpp:255-317) and homogeneous-freeze (coordinator.cpp:430-441, apply_homogeneous_freeze_supercold) are LATER stages — but note homog-freeze sits at the SAME insertion point (top of cold block, f90:1359-1370) and shares the identical aux-rebuild dependency, so the rebuild_aux helper built now will also unblock it.
</details>

## Port structure

Both ports (C++ coordinator.cpp + Python coordinator.py) are exact 1:1 mirrors. kdm62d_one_step runs preamble, then warm_phase, cold_phase, melt_freeze_phase ALL from the same entry snapshot state_pre, then scale_rates_for_conservation, then state_update sums every rate at once. Stage A must convert D1 (melt) and D2/D3/D4 (freeze) into INLINE pre-rate mutations of a working state, rebuild DSD slopes + aux on that mutated state, and feed it to warm_phase + cold_phase + the conservation budgets. D5 (enhanced melt) MUST stay post-cold because it reads cold_out rates. melt_freeze_phase as written interleaves D1-D4 (state-only) with D5 (cold-dependent), so the function must be split. aux is built once upstream by build_default_aux (runtime.cpp:103) from the ORIGINAL state and never rebuilt - this is the 806x-regression hazard the rebuild must fix.

## IMPLEMENTATION BLUEPRINT

**Headline:** STAGE-A headline: split kdm62d_one_step into a SEQUENTIAL working-state chain — preamble(entry) → apply D1 melt inline (mutate qs/qg/qi/ni/qr/nr/brs/t) → REBUILD pre+aux on post-melt state → apply D2/D3/D4 freeze inline with caps threaded through the RUNNING qc/qr/nr (D3 caps against post-D2 qc) → REBUILD pre+aux a 2nd time on post-freeze state → warm_phase(working,pre2,aux2) → cold_phase(working,pre2,aux2) → D5 enhanced-melt(working,cold_out) → scale_rates_for_conservation(working) → state_update(working) WITH all D1-D4 mf.* terms removed → reclass/satadj/cleanup/dsd unchanged. The rebuild = re-run preamble() (refreshes ALL slopes+work2+ProgB on mutated brs/qg) + build_default_aux() (refreshes n0r/n0i/n0c/work1_*/avedia_i/rslopec*) on the working state, returning BOTH a fresh PreambleOutputs AND fresh aux. SINGLE BIGGEST RISK: the 806× regression — rebuilding aux but leaving the stale `pre` (or rebuilding only n0 numerators without the matching slope/work1 denominators+ProgB) makes cold/mf deposition read a self-inconsistent intercept on frozen hydrometeors; the rebuild MUST replace pre AND aux together, and the D1-D4 mf.* terms MUST be stripped from state_update or every melt/freeze is double-applied.

```
STAGE-A IMPLEMENTATION BLUEPRINT (C++ kdm6_libtorch + Python kdm6_torch). All C++ line refs verified live against coordinator.cpp/runtime.cpp/coordinator.h/melt_freeze.h this session.

=====================================================================
0. KEY STRUCTURAL FACTS VERIFIED (so the plan is concrete)
=====================================================================
- kdm62d_one_step (coordinator.cpp:419-517) currently: state_pre=state(442) → pre=preamble(445) → warm_phase(state_pre,…)(450) → cold_phase(state_pre,…)(457) → mf=melt_freeze_phase(state_pre,…,cold_out,…)(467) → scaled=scale_rates_for_conservation(state_pre,…)(480) → state_update(state_pre,…)(487) → reclass(493,496)/satadj(505)/cleanup(513)/dsd(516). ALL phases read state_pre; only RATES cross between phases.
- build_default_aux (runtime.cpp:103-163) is in an ANONYMOUS namespace; computes from a CoordinatorState: rslope_r/rslope_i via diag_species_slope_torch(120-125), n0r=nr/(rslope_r·rslopemu_r·g1pmr)(135), n0i(136), n0c(137), work1_water/work1_ice via compute_diffac (T-dependent)(140-145), avedia_i=rslope_i·(g4pmi/g1pmi)^(1/3)(159), rslopecmu=rslopec^MUC(131), rslopecd=rslopec^DMC(161). n0so/n0go are CONSTANTS (153-154), qcr is xland-derived(158). rslopec is computed by the CALLER (runtime.cpp:201 diag_cloud_slope_torch) and passed in.
- melt::* output structs (melt_freeze.h:30-35,68-70,99-101,128-131,161-164) ALREADY carry every delta the inline-apply needs: D1 MeltingOutputs{psmlt,pgmlt,pimlt_qi,pimlt_ni,sfac,gfac,delta_brs}; D2 ContactFreezing{pinuc,ninuc}; D3 BiggCloud{pfrzdtc,nfrzdtc}; D4 BiggRain{pfrzdtr,nfrzdtr,delta_brs}; D5 Enhanced{pseml,nseml,pgeml,ngeml}.
- state_update (coordinator.cpp:815-1049) currently applies the D1-D4 mf.* amounts inline as dqc_amount(853), dqr_amount(869)+rate(862-863,867), dqs(889 mf.psmlt), dqg_amount(908)+rate(905), dqi_amount(920), dnc_amount(931), dnr_amount(947), dni_amount(959), dbrs(982-983), dT_freeze_rate(1011 psmlt/pgmlt), dT_freeze_amount(1022-1024). These are EXACTLY the terms to remove for D1-D4 (D5 pseml/pgeml/pgmlt-via-D5 + cold rates STAY).
- PreambleOutputs (coordinator.h:359-371) holds rslopec/work2/slope/progb/supcol/cpm/xl etc. PreambleMf (coordinator.h:300-309) is the subset D1-D5 consume; pre_warm_view/pre_cold_view/pre_mf_view/pre_core_view slice PreambleOutputs.
- Python: kdm62d_one_step_torch (coordinator.py:1425-1495) is a 1:1 mirror; preamble_torch(112) is pure+re-callable; Python has NO build_default_aux (aux only built in tests). Python runtime.py is a STUB (_kdm6_pure raises NotImplementedError); Python is the ORACLE, so the rebuild must exist in coordinator.py for the parity test to exercise it.

=====================================================================
1. NEW kdm62d_one_step SEQUENCE (the target order)
=====================================================================
state_pre = state
pre0  = preamble(state_pre, forcing, full_params)          // entry slopes/ProgB/work2 — feeds D1 melt rates
aux0  = rebuild_aux(state_pre, forcing, full_params, qcr_carry=aux.qcr)   // OR reuse caller `aux` for D1 rates (identical at entry)
// ── D1 MELT (apply inline, top-down semantics; tensorized so order-independent across k) ──
d1 = melt::melting_torch(MeltingInputs from state_pre + pre0.slope/work2/precg2/rhox + aux0.n0so/n0go + pre0.slope.n0sfac_field, melting_params, dtcld)
working = apply_melt_inline(state_pre, d1, dtcld):          // SEE §1A
// [homog-freeze supcol>40 slot — LATER STAGE, NOT here; insertion point is BEFORE the post-melt cloud-DSD recompute]
pre1  = preamble(working, forcing, full_params)             // RE-SLOPE #2 (Fortran f90:1342-1349 ProgB+slope on post-melt brs/qg/qrs/qci)
aux1  = rebuild_aux(working, forcing, full_params, pre1.rslopec, qcr_carry=aux.qcr)   // n0c/n0r/n0i/rslopec*/work1* on post-melt state
// ── D2/D3/D4 FREEZE (apply inline, SEQUENTIAL caps on running qc/qr/nr) ──
working = apply_freeze_inline(working, forcing, pre1, aux1, mf_params, dtcld):   // SEE §1B — D2→D3→D4, each capped vs the ALREADY-DEPLETED running reservoir
pre2  = preamble(working, forcing, full_params)             // RE-SLOPE #3 (Fortran f90:1537-1632 ProgB+slope+n0/lamda-snap+work1/work2 on post-freeze state)
aux2  = rebuild_aux(working, forcing, full_params, pre2.rslopec, qcr_carry=aux.qcr)
// ── WARM + COLD read the FULLY-MUTATED working state and the post-freeze pre2/aux2 ──
warm_out = warm_phase(working, forcing, pre_warm_view(pre2), aux2.n0r, aux2.work1_r, aux2.qcr, warm_params, dtcld, thermo)
cold_out = cold_phase(working, forcing, pre_cold_view(pre2), warm_out.prevp, aux2.n0i, aux2.n0r, aux2.n0so, aux2.n0go, aux2.n0c, aux2.rslopecmu, aux2.rslopecd, aux2.avedia_i, aux2.work1_ice, aux2.work1_water, cold_params, dtcld)
// ── D5 enhanced-melt: STILL here (reads cold_out HM-adj), pre-rate wrt its own qs/qg on `working` ──
d5 = melt::enhanced_melting_torch(EnhancedMeltingInputs from working.qs/qg + cold_out.paacw_adj/psacr_adj/pgacr_adj + aux2.n0so/n0go + pre2.slope.n0sfac_field/rslope_s/rslope_g + pre2.supcol, enhanced_melt_params, dtcld)
// ── budgets + state_update on the WORKING reservoirs ──
scaled = scale_rates_for_conservation(working, pre_core_view(pre2).supcol, warm_out, cold_out, mf_remainder, dtcld)   // mf_remainder = D5-only + the freeze T/brs/number bookkeeping that state_update still owns; SEE §5
new_state = state_update(working, pre_core_view(pre2), scaled.warm, scaled.cold, scaled.mf_remainder, dtcld, xls)      // D1-D4 amount terms REMOVED (already in `working`)
new_state = reclassify_large_ice_to_snow(new_state, forcing.den)   // unchanged
new_state = reclassify_small_rain_to_cloud(new_state, forcing.den) // unchanged
new_state = apply_satadj_step(new_state, forcing, pre2.xl, pre2.cpm, warm_params.satadj, thermo, dtcld)   // use pre2.xl/cpm (post-melt/freeze T)
new_state = apply_threshold_cleanup(new_state)
return apply_dsd_number_limiters(new_state, forcing.den)

DESIGN NOTE on “apply”: because the port is tensorized over the whole grid (not a top-down k-loop), each apply is a pure functional rebuild of the CoordinatorState struct — `working = CoordinatorState{ … qs - psmlt … }` — NOT in-place mutation. This preserves the autograd graph (no in-place on leaf tensors that need grad). The Fortran top-down/bottom-up loop direction is irrelevant in Stage A because none of D1-D4 has a vertical-neighbor dependency (sedimentation, which does, is a LATER stage).

§1A apply_melt_inline(state_pre, d1, dtcld) — mutate (Fortran f90:1247-1291):
  qs  -= d1.psmlt                          (psmlt<=0 ⇒ qs grows back toward 0; matches f90:1251 qrs(:,2)+=psmlt with psmlt sign<=0 → here psmlt stored as the C++ rate; APPLY WITH THE SAME SIGN the current state_update uses at qs dqs:889 `+mf.psmlt`)  ** Verify sign vs current state_update: dqs adds +mf.psmlt·dtcld and dqr subtracts (mf.psmlt+mf.pgmlt)·warm_mask. Reuse those EXACT signed expressions so apply == old state_update contribution. **
  qr  += (psmlt + pgmlt)·(per current dqr_rate:862-863 sign)        // rain GAINS melt
  qg  -= pgmlt  (mirror qs)                                          // graupel loses (current dqg adds +mf.pgmlt at :905)
  nr  -= sfac·psmlt + gfac·pgmlt   (current code: these are folded into mf.sfac/gfac; replicate the nr melt-number term — CONFIRM where current state_update puts sfac/gfac; if absent, this is a pre-existing gap to preserve, not introduce)
  qc  += pimlt_qi ; nc += pimlt_ni ; qi -= pimlt_qi ; ni -= pimlt_ni    // instantaneous ice→cloud (f90:1287-1291); current dqc_amount:853 +mf.pimlt_qi, dqi_amount:920 -mf.pimlt_qi, dnc_amount:931 +mf.pimlt_ni, dni_amount:959 -mf.pimlt_ni
  brs += d1.delta_brs·dtcld   (current dbrs:982 `dtcld*mf.delta_brs_melt`)
  t   += xlf/cpm·psmlt  +  xlf/cpm·pgmlt  -  xlf/cpm·pimlt_qi   (current dT_freeze_rate:1011 has psmlt+pgmlt; dT_freeze_amount:1024 has -mf.pimlt_qi). Use pre0.cpm, xlf=xls-pre0.xl.
  CRITICAL: copy the SIGNED arithmetic verbatim from state_update’s existing mf terms so “apply inline” + “remove from state_update” is a provable algebraic identity (sum unchanged when D5/cold paths untouched). This is the audit lever that lets §6 prove zero-diff.

§1B apply_freeze_inline(working, forcing, pre1, aux1, params, dtcld) — D2→D3→D4 SEQUENTIAL (Fortran f90:1442-1510):
  D2 contact: d2 = contact_freezing_torch(qc=working.qc, nc=working.nc, …, n0c=aux1.n0c, rslopec=pre1.rslopec, rslopecmu=aux1.rslopecmu, supcol=pre1.supcol). pinuc already min(…, qc) in the kernel against the CURRENT working.qc. Apply: qc-=pinuc; qi+=pinuc; nc-=ninuc; ni+=ninuc; t+=xlf/cpm·pinuc. → working_d2.
  D3 Bigg-cloud: d3 = bigg_cloud_freezing_torch(qc=working_d2.qc, nc=working_d2.nc, … aux1.n0c/rslopecd/rslopecmu, pre1.rslopec, pre1.supcol). ** THE FIDELITY POINT: pfrzdtc’s internal min(…, qc) now reads working_d2.qc — the post-D2-depleted cloud water (Fortran f90:1469). Current port caps D2 and D3 against the SAME entry qc (over-draw bug, FORTRAN_FLOW_ORDER_CHECKLIST.md item 1). Threading working_d2.qc into D3 is the fix. ** Apply: qc-=pfrzdtc; qi+=pfrzdtc; nc-=nfrzdtc; ni+=nfrzdtc; t+=xlf/cpm·pfrzdtc. → working_d3.
  D4 Bigg-rain: d4 = bigg_rain_freezing_torch(qr=working_d3.qr (note: qr already changed by D1 melt), nr=working_d3.nr, … aux1.n0r, pre1.slope.rslope_r/rsloped_r/rslopemu_r, pre1.supcol). pfrzdtr min(…, qr) vs current qr. Apply: qg+=pfrzdtr; brs+=pfrzdtr/denr (=d4.delta_brs); nr-=nfrzdtr; qr-=pfrzdtr; t+=xlf/cpm·pfrzdtr. → working (final).
  nonneg clamp on nr/ni/nc after D4 (f90:1515).
  Each kernel must take its q/n inputs by argument so the running reservoir threads through (D2 and D3 share the qc-min cap; the structs in melt_freeze.h:72-78,103-109,133-139 already take qc/nc/qr/nr as fields — just pass the running working state, no signature change needed).

=====================================================================
2. melt_freeze_phase SPLIT (D1-D4 pre-rate vs D5 post-cold)
=====================================================================
melt_freeze_phase currently runs D1-D5 from state_pre (coordinator.cpp:577-660). Split into THREE callables; D5 stays where it is:

(a) NEW: melt::melting_torch is already standalone — call it directly in kdm62d_one_step for D1 (no new function needed; just lift the d1_in construction out of melt_freeze_phase). Inputs use pre0/aux0.

(b) NEW: apply_freeze_inline (free function in coordinator.cpp, declared in coordinator.h) wrapping the D2/D3/D4 calls + the running-reservoir threading + the inline state apply. Signature:
    CoordinatorState apply_freeze_inline(
        const CoordinatorState& working, const CoordinatorForcing& forcing,
        const PreambleOutputs& pre, const CoordinatorAuxDiagnostics& aux,
        const MeltFreezePhaseParams& params, double dtcld,
        ContactFreezingOutputs* d2_out=nullptr, BiggCloudOutputs* d3_out=nullptr, BiggRainOutputs* d4_out=nullptr);  // optional out-params so scale_rates can still see the freeze rates if it needs them for T/brs budgets (see §5)
   Returns the post-freeze working state. The D2/D3/D4 rate tensors are emitted via out-params for the conservation limiter + any residual state_update bookkeeping.

(c) KEEP D5: melt::enhanced_melting_torch called AFTER cold_phase, reading working.qs/qg + cold_out. It is the ONLY user of cold_out — verified (coordinator.cpp:638-646). Its outputs pseml/nseml/pgeml/ngeml + the pgmlt-independent terms flow into scale_rates + state_update as the “mf_remainder”.

(d) DELETE/REPURPOSE melt_freeze_phase: it no longer runs as a single block. Either (i) delete it and inline D1/freeze/D5 in kdm62d_one_step, or (ii) keep a thin melt_freeze_d5_only(working, cold_out, …) wrapper returning just the D5 outputs. Option (ii) keeps the MeltFreezePhaseOutputs struct (coordinator.h:153-177) usable by scale_rates/state_update with D1-D4 fields left at their applied values for the limiter — but cleaner is to introduce a small MeltFreezeRates bundle that scale_rates/state_update consume (D5 rates + the freeze rates already applied, needed only for the conservation budgets and T/brs/number bookkeeping that state_update still owns; see §5).

NOTE the gate: melting fires t>t0c, freeze fires supcol>0 — they are MUTUALLY EXCLUSIVE per cell, so D1 and D2-D4 never both mutate the same cell. This means the two rebuilds (post-melt, post-freeze) are each only “active” in their arm; but you must STILL run both rebuilds over the full grid (the inactive arm’s state is unchanged ⇒ rebuild is a no-op there, but the tensor op must run for shape/graph consistency).

=====================================================================
3. AUX-REBUILD MECHANISM (the paramount correctness piece)
=====================================================================
Add a single helper, identical shape both ports:
C++ (coordinator.cpp, declared coordinator.h), returning BOTH fresh preamble AND aux:
    struct RebuiltDiagnostics { PreambleOutputs pre; CoordinatorAuxDiagnostics aux; };
    RebuiltDiagnostics rebuild_aux(
        const CoordinatorState& s, const CoordinatorForcing& f,
        const CoordinatorParams& p, const torch::Tensor& qcr_carry) {
        auto pre = preamble(s, f, p);                       // refreshes ALL slopes + work2 + ProgB on mutated brs/qg/q*/n*
        auto aux = build_default_aux(s, f, pre.rslopec, p.thermo);   // refreshes n0r/n0i/n0c/work1_*/avedia_i/rslopec*
        aux.qcr  = qcr_carry;                               // qcr is xland/sea-mask-derived & state-independent — carry, don't recompute
        return {pre, aux};
    }
PREREQUISITE: PROMOTE build_default_aux out of runtime.cpp’s anonymous namespace — declare it in coordinator.h and move the definition to coordinator.cpp (or expose a coordinator-layer copy). The test wrapper build_default_aux_for_test (runtime.cpp:169-177) already proves it is callable from a CoordinatorState; rebuild_aux is the production analog. n0so/n0go stay constants (mus=mug=0, runtime.cpp:153-154) — build_default_aux already hardcodes them, so no special carry needed.

WHERE invoked: TWICE — (1) after apply_melt_inline → (pre1,aux1) feed apply_freeze_inline; (2) after apply_freeze_inline → (pre2,aux2) feed warm_phase/cold_phase/D5/scale_rates/state_update. The entry pre0/aux0 (for D1 rates) can REUSE the caller-supplied `aux` (it was built from the same entry state upstream at runtime.cpp:202) — only qcr must be carried; or call rebuild_aux a third time at entry for symmetry (a no-op vs the supplied aux, costs one extra preamble — acceptable, and removes the “is the caller aux really entry-consistent?” question).

WHAT each rebuild recomputes (state-DEPENDENT, MUST refresh): n0r(needs nr), n0i(needs ni), n0c(needs nc), avedia_i(needs qi/ni via rslope_i), rslopec/rslopecmu/rslopecd(need qc/nc), work1_water/work1_ice(T-dependent, T mutated by melt+freeze), ALL pre.slope.rslope_*/rslopeb_*/rslope2_*/rslopemu_*/rsloped_*/vt_*/n0sfac_field (needs q*/n*), pre.work2(venfac, T-dependent), pre.rhox/precg2 via ProgB (needs brs+qg — brs mutated by pgmlt §1A and pfrzdtr §1B). State-INDEPENDENT (carry/constant): n0so, n0go (constants), qcr (sea_mask).
Fortran’s lamda-snap number BACK-mutation of nr/nci at the clamps (f90:1389-1430, 1574-1615) is OMITTED by build_default_aux (runtime.cpp header note) — Stage A INHERITS this approximation (matches current entry-state behavior). This is a KNOWN divergence vs Fortran but is NOT the 806× class (it is a number-conservation refinement, flag it as Stage-A-deferred, see §7 risk).

=====================================================================
4. STATE-THREADING
=====================================================================
working : CoordinatorState flows state_pre → (D1 apply) → working_melt → (rebuild→pre1/aux1) → (D2/D3/D4 apply) → working_freeze → (rebuild→pre2/aux2) → warm/cold/D5 read working_freeze + pre2/aux2 → scale_rates(working_freeze reservoirs) → state_update(working_freeze base + scaled rates) → new_state.
- The conservation-limiter reservoirs (scale_rates_for_conservation, coordinator.cpp:680-) take `state` as the reservoir source (value=max(floor, reservoir)). PASS working_freeze, NOT state_pre — so the limiter sees melt+freeze already drawn down. The delta2/delta3 routing flags (state_update:873-874, computed from qr/qs<1e-4) ALSO re-evaluate against working_freeze.qr/qs (post-melt qr is larger, post-freeze qr smaller — both correct vs Fortran which computes them at f90:2516 on the mutated state).
- state_update base state = working_freeze (its struct `state` arg): qc_new=working.qc + dqc_rate + (D5/cold amounts only), etc.

=====================================================================
5. DOUBLE-COUNT GUARD — exact terms to REMOVE from state_update
=====================================================================
Because D1 (melt) and D2/D3/D4 (freeze) are now applied to `working` BEFORE state_update, their amount/number/T/brs contributions MUST be stripped from state_update (else applied twice — the #1 regression trap, FORTRAN_FLOW_ORDER_CHECKLIST.md:150,173: Fortran does NOT re-apply psmlt/pimlt/pinuc/pfrzdtc/pfrzdtr after f90:2395 precisely because they were applied inline). REMOVE these specific lines (coordinator.cpp):
  qc: dqc_amount(853) drop `-mf.pinuc - mf.pfrzdtc + mf.pimlt_qi` ENTIRELY (all D1+D2+D3).
  qr: dqr_rate(862-863) drop `-(mf.psmlt+mf.pgmlt)*warm_mask` (D1 melt-to-rain); dqr_amount(869) drop `-mf.pfrzdtr` (D4). KEEP `-mf.pseml-mf.pgeml`(863, D5) and the cold/warm rate terms.
  qs: dqs(889) drop `+mf.psmlt` (D1). KEEP `+mf.pseml`(891, D5) and cold rates.
  qg: dqg_rate(905) drop `+mf.pgmlt` (D1); dqg_amount(908) drop `mf.pfrzdtr` (D4). KEEP `+mf.pgeml`(906, D5) and cold rates.
  qi: dqi_amount(920) drop `mf.pinuc + mf.pfrzdtc - mf.pimlt_qi` ENTIRELY (D2+D3+D1).
  nc: dnc_amount(931) drop `-mf.ninuc - mf.nfrzdtc + mf.pimlt_ni` ENTIRELY (D2+D3+D1).
  nr: dnr_rate(945) KEEP `+mf.nseml+mf.ngeml` (D5); dnr_amount(947) drop `-mf.nfrzdtr` (D4). (D1 melt nr term sfac·psmlt/gfac·pgmlt → move to §1A apply.)
  ni: dni_amount(959) drop `mf.ninuc + mf.nfrzdtc - mf.pimlt_ni` ENTIRELY (D2+D3+D1).
  brs: dbrs(982-983) drop `dtcld*mf.delta_brs_melt`(D1) + `mf.delta_brs_freeze`(D4). KEEP dbrs_warm_evap `+mf.pgeml/rhox_safe`(979, D5) and the cold_riming block.
  T: dT_freeze_rate(1011) drop `mf.psmlt + mf.pgmlt` (D1) — KEEP `mf.pseml+mf.pgeml`(1012, D5) and the cold_mask freeze block(1013-1020). dT_freeze_amount(1022-1024) drop `mf.pinuc + mf.pfrzdtc + mf.pfrzdtr - mf.pimlt_qi` ENTIRELY (D2+D3+D4+D1).
KEEP in state_update (these are NOT melt/freeze inline): all warm.*, all cold.* rates, D5 (pseml/nseml/pgeml/ngeml), and the dbrs_cold_riming/dbrs_warm_evap cold-derived volume terms, the qv/dqv deposition+evap block, and the deferred pcact/pcond (still in apply_satadj_step).
PROOF OBLIGATION: the sum [apply_melt_inline Δ + apply_freeze_inline Δ + reduced-state_update Δ] must equal the OLD [full state_update Δ] when (a) the two rebuilds are forced to return the entry-state aux/pre and (b) the D3 sequential cap is forced to use entry qc. This algebraic identity is the §6 step-1 regression gate.

=====================================================================
6. INCREMENTAL SUB-STEPS, each with a checkpoint (least-risky first)
=====================================================================
Validation harness per step: (i) C++ unit tests (test_coordinator / test_thermo in kdm6_libtorch/build_miniforge) + C++↔Python parity test; (ii) autograd end-to-end (test_autograd_endtoend.cpp — all 8 state leaves finite nonzero grad); (iii) em_quarter_ss dt=6 WRF sanity via run/run_kdm6ad.sh (NEVER ./wrf.exe direct; require KDM6AD_DIAG rc=0 evidence). Validation case is em_convrad/em_quarter_ss, NOT em_b_wave (b_wave does not call KDM6AD). Mirror every C++ change in coordinator.py in the SAME step or parity passes falsely.

  STEP 0 (zero-risk plumbing): Promote build_default_aux to coordinator.h/.cpp; add rebuild_aux + Python build_default_aux_torch + rebuild_aux_torch. NO call-site change yet. CHECKPOINT: build green, build_default_aux_for_test still passes, new rebuild_aux unit test (rebuild on entry state == supplied aux bit-for-bit).
  STEP 1 (identity refactor — should be ZERO numerical change): split melt_freeze_phase; apply D1+D2/D3/D4 inline; REMOVE the §5 terms from state_update; but FORCE rebuild to reuse entry pre/aux AND force D3 cap vs entry qc (i.e. behavior-preserving). CHECKPOINT: parity test bit-identical to pre-refactor; em_quarter_ss dt=6 diff < roundoff. This proves the double-count guard algebra (§5 proof obligation).
  STEP 2 (enable rebuild #2, post-freeze, for warm/cold/D5): switch warm/cold/D5/scale/state_update to consume pre2/aux2 instead of entry pre/aux. Keep D3-cap-vs-entry-qc still off. CHECKPOINT: parity C++↔Python; autograd finite; em_quarter_ss dt=6 stable ≥ the current clean horizon (mp=37 runs 30 min clean; ensure no early QC overshoot regression). THIS is the 806×-risk step — watch ice deposition (cold.pidep/psdep/pgdep) for over-deposition; if it blows up, the rebuild is self-inconsistent (pre vs aux mismatch) — see §7.
  STEP 3 (enable rebuild #1, post-melt, feeding D2/D3/D4 rates): freeze rates now read post-melt n0c/rslopec/pre1.slope. CHECKPOINT: same suite; check D2/D3/D4 magnitudes vs a Fortran single-cell dump.
  STEP 4 (enable the D3 sequential cap vs post-D2 qc): thread working_d2.qc into D3. CHECKPOINT: confirm combined D2+D3 no longer over-draws qc (compare qc after freeze vs Fortran f90 post-1487 dump); parity will now LEGITIMATELY differ from the old port — update the golden to the Fortran-faithful value, document the delta.
  STEP 5 (full em_quarter_ss dt=6 + a 6-hour stability run): confirm no triangular rainfall blow-up (RAINNCV must zero at entry per memory), KDM6AD_DIAG rc=0.

=====================================================================
7. AUTODIFF-SAFETY + EXPLICIT RISKS
=====================================================================
AUTODIFF: rebuild_aux/preamble/build_default_aux are PURE torch ops — verified no .item()/NoGradGuard (the only NoGradGuard+.item() is runtime.cpp mstep/sedimentation, untouched). “apply inline” must be FUNCTIONAL (build a new CoordinatorState via out-of-place arithmetic: working = {qs - psmlt, …}); NO in-place mutation of grad-requiring tensors (no working.qs -= …) or you break the graph / hit an in-place autograd error. Re-invoking preamble on `working` correctly threads grad through the melt/freeze deltas (this is the WHOLE POINT of Stage A — restoring the sensitivity Fortran’s inline mutation implies).
RISKS:
 R1 (806× class, paramount): rebuild aux but leave stale `pre` → cold/mf read entry-state slopes/work2 (the partial-recompute that refreshed n0 numerators but not slope/work1 denominators+ProgB caused 806× ice over-deposition). MITIGATION: rebuild returns BOTH pre AND aux; never split them. Step 2 is the canary.
 R2 (double-count): §5 strip incomplete → melt/freeze applied twice. MITIGATION: Step 1 identity gate proves the algebra before any rebuild is enabled.
 R3 (brs): mutated by BOTH pgmlt(/rhox, §1A) and pfrzdtr(/denr, §1B) and feeds ProgB in BOTH rebuilds — wrong brs silently corrupts graupel DSD (n0g/precg2/bvtg/rslopegbmax). MITIGATION: apply brs deltas in the inline steps, NOT in state_update; verify ProgB precg2 in pre1/pre2 changes when brs changes (unit assert).
 R4 (D3 sequential cap): the Stage-A fidelity point (f90:1469 vs entry). Threading working_d2.qc legitimately changes results — Step 4 gates it separately and updates the golden to the Fortran value.
 R5 (pimlt sign): instantaneous total transfer, COOLS with MINUS (f90:1289), opposite to freeze PLUS. The current state_update already encodes this (dT_freeze_amount: -mf.pimlt_qi); copy verbatim into §1A.
 R6 (lamda-snap number back-mutation OMITTED): build_default_aux skips the nr/nci clamp back-mutation (f90:1389-1430,1574-1615). Stage A inherits this — DOCUMENT as deferred; it is a number-conservation refinement, not the deposition-staleness 806× class. Revisit when porting the in-loop lamda snap.
 R7 (qcr carry): qcr is sea_mask-derived; recomputing from a possibly-changed path is wrong — always carry the caller’s aux.qcr through rebuild_aux.
 R8 (work2/work1 T-coupling): both T-dependent and T is mutated by melt+freeze; re-running preamble (work2) + build_default_aux (work1) on `working` covers this — skipping it leaves stale diffac/venfac (part of the 806× over-deposition class).
 R9 (Python oracle): coordinator.py runtime is a stub; the differentiable op path is C++, Python is the parity oracle. EVERY change (split, rebuild, §5 strip, D3 cap) must land in coordinator.py the same session or the parity test passes falsely (memory: python oracle must mirror cpp fixes).
SCOPE GUARDS (NOT Stage A): sedimentation-per-substep (runtime.cpp mstep) and homogeneous-freeze supcol>40 (apply_homogeneous_freeze_supercold, coordinator.cpp:430-441) — but homog-freeze’s insertion slot is the TOP of the post-melt cloud-DSD recompute (before rebuild #2 finalizes), and it shares the identical rebuild_aux dependency, so rebuild_aux built now also unblocks it later.
```

## Risks
```
SINGLE BIGGEST: the 806× aux-staleness — rebuild MUST replace pre AND aux together (returning RebuiltDiagnostics{pre,aux}); rebuilding only n0 numerators or only aux-without-pre makes cold/mf deposition read self-inconsistent intercepts on frozen hydrometeors. SECOND: double-count — the §5 D1-D4 mf.* terms MUST be stripped from state_update (qc:853, qr:862-863/869, qs:889, qg:905/908, qi:920, nc:931, nr:947, ni:959, brs:982-983, T:1011/1022-1024) or every melt/freeze is applied twice. Both ports must change in the same session (Python is the parity oracle; runtime.py is a stub). Validate on em_quarter_ss/em_convrad dt=6 via run/run_kdm6ad.sh with KDM6AD_DIAG rc=0 evidence (NOT em_b_wave, NOT direct ./wrf.exe). build_default_aux must be promoted out of runtime.cpp's anonymous namespace first. Deferred/known divergences: lamda-snap nr/nci back-mutation (R6) and homogeneous-freeze + sedimentation-per-substep are LATER stages.
```
