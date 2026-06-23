#include "kdm6/progb.h"
#include "kdm6/ops.h"

#include <array>
#include <cmath>

namespace kdm6 {
namespace progb {
namespace {

constexpr double PI = 3.14159265358979323846;

// 9-point graupel density → terminal-velocity coefficient lookup
constexpr std::array<double, 9> DENSITY_TABLE = {
    100.0, 200.0, 300.0, 400.0, 500.0, 600.0, 700.0, 800.0, 900.0
};
constexpr std::array<double, 9> AVTG_TABLE = {
    54.9153, 74.2262, 88.8313, 101.0411, 111.7359, 121.3625, 130.1841, 138.3714, 146.0422
};
constexpr std::array<double, 9> BVTG_TABLE = {
    0.5446, 0.5375, 0.5339, 0.5316, 0.5299, 0.5286, 0.5275, 0.5266, 0.5258
};


torch::Tensor scalar_like(double value, const torch::Tensor& ref) {
    return torch::full_like(ref, value);
}

// 9-element array → ref와 같은 dtype/device의 1D tensor
torch::Tensor make_table(const std::array<double, 9>& values, const torch::Tensor& ref) {
    auto cpu_opts = torch::TensorOptions().dtype(torch::kFloat64);
    // const_cast: from_blob 시그니처는 non-const void*; clone()으로 별도 메모리 확보.
    auto t = torch::from_blob(
        const_cast<double*>(values.data()),
        {static_cast<int64_t>(values.size())},
        cpu_opts
    ).clone();
    return t.to(ref.options().requires_grad(false));
}

}  // namespace

torch::Tensor rgmma_tensor(const torch::Tensor& x) {
    // Fortran rgmma = Γ(x) (review6 audit fix; 이전 -torch::lgamma 부호 잘못).
    // (A) transcendental: rgmma = EXP(GAMMLN(x)) (F:3051) → libm exp for gfortran bit-match.
    // STEP-final (Codex stop-review): the per-cell ProgB gamma must route through
    // the Fortran GAMMLN mirror on the f32 path (torch::lgamma = Sleef lgammaf
    // differs); ops::rgmma_t = elementwise fconst::rgmma_f (f64 path unchanged).
    return ops::rgmma_t(torch::clamp(x, /*min=*/constants::EPS));
}

ProgBParams default_progb_params() {
    // Fortran rgmma = Γ(x) (review6 audit fix).
    const auto rgmma_scalar = [](double v) { return std::exp(std::lgamma(v)); };
    const double dmg = constants::DMG;
    const double mug = constants::MUG;

    const double g1pdgmg = rgmma_scalar(1.0 + dmg + mug);
    // Fortran kdm6init: mug==0 → g1pmg=1 short-circuit
    const double g1pmg = (mug == 0.0) ? 1.0 : rgmma_scalar(1.0 + mug);
    const double rslopegmax = 1.0 / constants::LAMDAGMAX;

    return ProgBParams{
        /*qcrmin=*/constants::QCRMIN,
        /*dmg=*/dmg,
        /*mug=*/mug,
        /*n0g=*/constants::N0G,
        /*g1pdgmg=*/g1pdgmg,
        /*g1pmg=*/g1pmg,
        /*rslopegmax=*/rslopegmax,
    };
}

ProgBOutputs progb_param_torch(
    const torch::Tensor& qg,
    const torch::Tensor& bg,
    const ProgBParams& params,
    c10::optional<c10::ScalarType> op_dtype
) {
    TORCH_CHECK(qg.sizes() == bg.sizes(),
                "qg shape ", qg.sizes(), " != bg shape ", bg.sizes());
    const auto odt = op_dtype.value_or(bg.scalar_type());

    auto Tbl = make_table(DENSITY_TABLE, qg);
    auto aTbl = make_table(AVTG_TABLE, qg);
    auto bTbl = make_table(BVTG_TABLE, qg);

    // ── 외부 게이트 ──────────────────────────────────────────────────────
    auto active = torch::logical_or(qg > params.qcrmin, bg > BRS_MIN);
    auto zero = torch::zeros_like(qg);

    // ── rhox 진단 + clamp ───────────────────────────────────────────────
    // DTYPE-CONDITIONAL (the brs AD-limit fix): compute rhox/bg in op_dtype. On the OP path
    // (f32) this is Fortran's REAL(4) rhox=qg/brs, so the [100,900] clamp tips IDENTICALLY
    // (entry-brs clamp-tipping residual → 0). On the DA path (f64) op_dtype=f64 ⇒ smooth f64,
    // NO f32 staircase, so the VJP/FD adjoint + the ABI fp64 value_only==graph determinism
    // (test_c_abi.cpp:526) are untouched — dodging both prior failure modes (unconditional f32
    // staircase / grad-mode split). Outputs cast back to qg's dtype (no downstream dtype ripple).
    auto qg_op = qg.to(odt);
    auto bg_safe = torch::clamp(bg.to(odt), /*min=*/BRS_MIN);
    auto rhox_op = qg_op / bg_safe;
    auto rhox_c = torch::clamp(rhox_op, /*min=*/RHO_MIN, /*max=*/RHO_MAX);
    auto bg_new_op = qg_op / rhox_c;
    auto rhox = torch::where(active, rhox_c.to(qg.scalar_type()), scalar_like(RHO_MID, qg));
    auto bg_new = torch::where(active, bg_new_op.to(qg.scalar_type()), bg);

    // ── cmg, pidn0g ─────────────────────────────────────────────────────
    auto cmg_raw = PI * rhox / 6.0;
    auto cmg = torch::where(active, cmg_raw, zero);
    auto pidn0g = cmg * params.n0g * params.g1pdgmg / params.g1pmg;

    // ── 9-point linear interpolation: rhox → (avtg, bvtg) ──────────────
    // searchsorted(right=true): Tbl[i-1] <= rhox < Tbl[i]; rhox==RHO_MAX gives
    // idx_right==9 (out-of-bounds) so clamp to [1, 8]; the rhox==Tbl(9)
    // endpoint itself is handled by the explicit where() below (Fortran's
    // `else if (rhox==Tbl(9))` branch, F:3404).
    auto rhox_contig = rhox.contiguous();
    auto idx_right = torch::searchsorted(Tbl, rhox_contig, /*out_int32=*/false, /*right=*/true);
    idx_right = torch::clamp(idx_right, /*min=*/1, /*max=*/static_cast<int64_t>(Tbl.numel()) - 1);
    auto idx_left = idx_right - 1;

    const auto out_shape = qg.sizes();
    auto Tbl_left   = torch::index_select(Tbl,  0, idx_left.flatten()).reshape(out_shape);
    auto Tbl_right  = torch::index_select(Tbl,  0, idx_right.flatten()).reshape(out_shape);
    auto aTbl_left  = torch::index_select(aTbl, 0, idx_left.flatten()).reshape(out_shape);
    auto aTbl_right = torch::index_select(aTbl, 0, idx_right.flatten()).reshape(out_shape);
    auto bTbl_left  = torch::index_select(bTbl, 0, idx_left.flatten()).reshape(out_shape);
    auto bTbl_right = torch::index_select(bTbl, 0, idx_right.flatten()).reshape(out_shape);

    auto width = Tbl_right - Tbl_left;
    // Fortran F:3385-3387: tmp2 = 1./(Tbl(sy+1)-Tbl(sy)) — ONE rounded
    // reciprocal reused for avtg AND bvtg — then
    //   aTbl(sy) + ((rhox-Tbl(sy))*(aTbl(sy+1)-aTbl(sy)))*tmp2
    // with every op individually rounded left-to-right (-ffp-contract=off).
    // A direct (rhox-Tbl_left)/width division is NOT bit-equal (fl(1/100) is
    // inexact; ~2.3% of f32 rhox samples differ by 1 ulp — IEEE sweep finding).
    auto tmp2 = 1.0 / width;
    auto d1 = rhox - Tbl_left;
    auto avtg_raw = ops::fma_acc(aTbl_left, d1 * (aTbl_right - aTbl_left), tmp2);
    auto bvtg_raw = ops::fma_acc(bTbl_left, d1 * (bTbl_right - bTbl_left), tmp2);
    // Exact-endpoint branch (Fortran F:3404 `else if (rhox==Tbl(9))`):
    // mirrored by construction rather than relying on the lerp round-tripping
    // bit-exactly at rhox==Tbl(9) for the current table constants.
    const auto last = Tbl.numel() - 1;
    avtg_raw = torch::where(rhox == Tbl[last], aTbl[last], avtg_raw);
    bvtg_raw = torch::where(rhox == Tbl[last], bTbl[last], bvtg_raw);

    auto avtg = torch::where(active, avtg_raw, zero);
    auto bvtg = torch::where(active, bvtg_raw, zero);

    // ── derived sums ────────────────────────────────────────────────────
    auto bvtg1 = 1.0 + bvtg;
    // Fortran F:3389 `2.5+.5*bvtg+mug` — .5*bvtg rounds, then 2.5+(.) rounds, then
    // +mug rounds (strict IEEE source order); fma_acc(2.5, bvtg, 0.5) + mug.
    auto bvtg2 = ops::fma_acc(scalar_like(2.5, bvtg), bvtg, scalar_like(0.5, bvtg)) + params.mug;
    auto bvtg3 = 3.0 + bvtg + params.mug;
    auto bvtg4 = 4.0 + bvtg;
    auto dgbgmug1 = 1.0 + params.dmg + bvtg + params.mug;

    // rgmma family — safety EPS clamp (bvtg=0 inactive case 대비)
    auto g1pbg     = rgmma_tensor(bvtg1);
    auto g3pbg     = rgmma_tensor(bvtg3);
    auto g4pbg     = rgmma_tensor(bvtg4);
    auto g5pbgo2   = rgmma_tensor(bvtg2);
    auto g1pdgbgmg = rgmma_tensor(dgbgmug1);

    // rslopegbmax = rslopegmax ** bvtg  (per-cell, since bvtg is a tensor)
    // (A) transcendental: Fortran F:3398 `rslopegmax ** bvtg` → route pow through ops::safe_pow
    // (libm pow). Base rslopegmax = 1/LAMDAGMAX > 0, so the EPS clamp is harmless (no value change).
    auto rslopegmax_t = scalar_like(params.rslopegmax, qg);
    auto rslopegbmax_raw = ops::safe_pow(rslopegmax_t, bvtg);
    auto rslopegbmax = torch::where(active, rslopegbmax_raw, zero);

    // pvtg, precg2 ─ sqrt(0)의 backward는 inf → EPS clamp + mask zero
    auto pvtg_raw = avtg * g1pdgbgmg / params.g1pdgmg;
    auto pvtg = torch::where(active, pvtg_raw, zero);

    // (A) transcendental: Fortran F:3400 `4.*.31*avtg**.5*g5pbgo2`. `avtg**.5` compiles to libm
    // pow(avtg,0.5); route through ops::safe_pow (libm pow, base already EPS-clamped) instead of
    // torch::sqrt (Sleef) for gfortran bit-match. Pure multiply chain, each op individually
    // rounded (nothing is fused under -ffp-contract=off).
    auto precg2_raw = 4.0 * 0.31 * ops::safe_pow(avtg, 0.5) * g5pbgo2;
    auto precg2 = torch::where(active, precg2_raw, zero);

    // 비활성 셀의 derived 출력은 zero로 mask (downstream graupel mask와 일관)
    g1pbg     = torch::where(active, g1pbg,     zero);
    g3pbg     = torch::where(active, g3pbg,     zero);
    g4pbg     = torch::where(active, g4pbg,     zero);
    g5pbgo2   = torch::where(active, g5pbgo2,   zero);
    g1pdgbgmg = torch::where(active, g1pdgbgmg, zero);
    bvtg1     = torch::where(active, bvtg1,     zero);
    bvtg2     = torch::where(active, bvtg2,     zero);
    bvtg3     = torch::where(active, bvtg3,     zero);
    bvtg4     = torch::where(active, bvtg4,     zero);
    dgbgmug1  = torch::where(active, dgbgmug1,  zero);

    return ProgBOutputs{
        /*rhox=*/rhox, /*bg=*/bg_new, /*cmg=*/cmg, /*pidn0g=*/pidn0g,
        /*avtg=*/avtg, /*bvtg=*/bvtg, /*bvtg1=*/bvtg1, /*bvtg2=*/bvtg2, /*bvtg3=*/bvtg3, /*bvtg4=*/bvtg4,
        /*g1pbg=*/g1pbg, /*g3pbg=*/g3pbg, /*g4pbg=*/g4pbg, /*g5pbgo2=*/g5pbgo2, /*g1pdgbgmg=*/g1pdgbgmg,
        /*dgbgmug1=*/dgbgmug1, /*rslopegbmax=*/rslopegbmax, /*pvtg=*/pvtg, /*precg2=*/precg2
    };
}

}  // namespace progb
}  // namespace kdm6
