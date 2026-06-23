#include "kdm6/satadj.h"

namespace kdm6 {
namespace satadj {

SatAdjParams default_satadj_params(double rv) {
    return SatAdjParams{
        /*rv=*/rv,
        /*qmin=*/constants::EPS,      // Fortran qmin=epsilon=1e-15 (driver QMIN). satadj uses it as the
                                      // q_eff=max(q,qmin) floor (F:2927) — same #1 issue, same fix as ThermoParams.
                                      // A pure floor (no div-safety), inactive in warm cells where q>>floor.
    };
}

SatAdjOutputs saturation_adjustment_torch(
    const torch::Tensor& t,
    const torch::Tensor& q,
    const torch::Tensor& qc,
    const torch::Tensor& qs1,
    const torch::Tensor& xl,
    const torch::Tensor& cpm,
    const SatAdjParams& params,
    double dtcld
) {
    // work1 = (max(q, qmin) - qs1) / (1 + xl² · qs1 / (rv · cpm · t²))
    auto t_safe = torch::clamp(t, /*min=*/1.0);
    // Fortran conden stmt-fn (module_mp_kdm6.F:781, used at F:2927):
    //   denom = 1.+ d*d/(rv*e)*c/(a*a)   with d=xl, e=cpm, c=qs1, a=t.
    // Fortran `*` and `/` are equal-precedence, left-associative, so the term is
    //   ((((xl*xl)/(rv*cpm))*qs1)/(t*t)) — divide by (rv*cpm) FIRST, then *qs1,
    // then /(t*t). gfortran (-O2, no -ffast-math: configure.wrf:150) does NOT
    // reassociate division, so this left-to-right grouping is what mp37 generates.
    // Mirror that grouping here (NOT (xl*xl*qs1)/(rv*cpm*t*t)) so the float32
    // operational path bit-matches mp37 in this saturation-adjustment kernel — the
    // condensate-onset seed the prior FMA/libm sweep could not reach (division
    // reassociation is not an FMA contraction). Tensor-ops only ⇒ autograd-safe.
    // (f64-activation experiment 2026-06-10: upcasting this conden to f64 left the
    // QCLOUD divergence vs mp37 BYTE-UNCHANGED — the residual is NOT the conden
    // cancellation floor; it is already present in the t/q/qs1 ENTERING satadj, i.e.
    // upstream. Reverted to native f32.)
    auto denom = 1.0 + xl * xl / (params.rv * cpm) * qs1 / (t_safe * t_safe);
    auto qmin_t = torch::full_like(q, params.qmin);
    auto q_eff = torch::maximum(q, qmin_t);
    auto work1 = (q_eff - qs1) / denom;

    // Branch on sign:
    //   work1 > 0          → cond_path = min(work1, max(q, 0)) / dtcld
    //   work1 < 0 and qc>0 → evap_path = max(work1, -qc) / dtcld
    //   else               → 0
    auto zero = torch::zeros_like(q);
    // §44 DOUBLE-internal-narrowed-once: Fortran work1 is DOUBLE (F:660), dtcld REAL(4) →
    // work1/dtcld + the min/max run in DOUBLE, narrowing to the REAL(4) pcond ONCE at the
    // store (F:3020/3022). C++ ran the whole chain in f32, rounding at every op. Mirror Fortran:
    // promote work1/q/qc to f64, do /dtcld + min/max in f64, narrow at op dtype (q.scalar_type():
    // f32 operational = Fortran-faithful; f64 DA = no-op, VJP preserved). work1 itself stays
    // native f32 (F:3018 conden is REAL(4); 2026-06-10 f64-conden experiment was byte-neutral).
    // The complete-evap RHS below stays PURE f32 (-qc/dtcld): Fortran F:3027 compares the
    // f32-narrowed pcond against an f32 -qci/dtcld (qci,dtcld both REAL(4)) — do NOT upcast it.
    auto rdt = q.scalar_type();
    auto wd = work1.to(torch::kFloat64);
    auto qd = q.to(torch::kFloat64);
    auto qcd = qc.to(torch::kFloat64);
    auto cond_path = (torch::minimum(wd, torch::maximum(qd, torch::zeros_like(qd))) / dtcld).to(rdt);
    auto evap_path = (torch::maximum(wd, -qcd) / dtcld).to(rdt);

    auto is_super = work1 > 0;
    auto is_sub_with_cloud = torch::logical_and(work1 < 0, qc > 0);

    auto pcond = torch::where(
        is_super, cond_path,
        torch::where(is_sub_with_cloud, evap_path, zero)
    );
    // Fortran F:2966 is a BARE equality gate `if(pcond.eq.-qci(i,k,1)/dtcld)` — no
    // qc>0 / sub-saturation conjunct. At an entry-clamped qc==0 cell with pcond==0
    // it fires (0.0 == -0.0), transferring nc -> nccn (the step-46 nn seed when the
    // old is_sub_with_cloud gate blocked it). pcond>=0 with qc>0 makes -qc/dt<0
    // unreachable, so the bare gate is exactly the evap-exhausted + qc==0 set.
    auto cloud_complete_evap = (pcond == (-qc / dtcld));
    return SatAdjOutputs{/*pcond=*/pcond, /*cloud_complete_evap=*/cloud_complete_evap};
}

}  // namespace satadj
}  // namespace kdm6
