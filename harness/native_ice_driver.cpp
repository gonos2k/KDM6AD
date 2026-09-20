#include "kdm6/sedimentation.h"
#include "kdm6/sedimentation_conservative.h"

#include <torch/torch.h>

#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <type_traits>
#include <vector>

namespace {

struct Row {
    double qi;
    double ni;
    double work1;
    double workn;
    double rho;
    double dz;
    double fall_qi;
    double fall_ni;
};

template <typename Scalar>
torch::Tensor column(const std::vector<double>& values) {
    std::vector<Scalar> casted;
    casted.reserve(values.size());
    for (double value : values) {
        casted.push_back(static_cast<Scalar>(value));
    }
    return torch::tensor(casted, torch::TensorOptions().dtype(
        std::is_same<Scalar, float>::value ? torch::kFloat32 : torch::kFloat64))
        .reshape({1, static_cast<int64_t>(values.size())});
}

template <typename Scalar>
void print_field(const char* name, const torch::Tensor& tensor) {
    const auto flat = tensor.to(torch::kCPU).contiguous().reshape({-1});
    const Scalar* values = flat.data_ptr<Scalar>();
    std::cout << name;
    for (int64_t k = 0; k < flat.numel(); ++k) {
        std::cout << ' ' << std::hexfloat << std::setprecision(
            std::numeric_limits<Scalar>::max_digits10) << values[k];
    }
    std::cout << '\n';
}

template <typename Scalar, bool Conservative>
void run_case(const char* label, const std::vector<Row>& rows, double dt,
              int mstep, int n) {
    std::vector<double> qi, ni, work1, workn, rho, dz, fall_qi, fall_ni;
    qi.reserve(rows.size());
    ni.reserve(rows.size());
    work1.reserve(rows.size());
    workn.reserve(rows.size());
    rho.reserve(rows.size());
    dz.reserve(rows.size());
    fall_qi.reserve(rows.size());
    fall_ni.reserve(rows.size());
    for (const Row& row : rows) {
        qi.push_back(row.qi);
        ni.push_back(row.ni);
        work1.push_back(row.work1);
        workn.push_back(row.workn);
        rho.push_back(row.rho);
        dz.push_back(row.dz);
        fall_qi.push_back(row.fall_qi);
        fall_ni.push_back(row.fall_ni);
    }

    // Native Fortran keeps prognostics/rho/dz/fall in REAL(4), but work1/workn
    // are DOUBLE PRECISION.  Preserve that mixed boundary in the f32 run.
    const auto mstep_col = column<Scalar>({static_cast<double>(mstep)}).reshape({1});
    kdm6::sed::IceSubstepInputs inputs{
        /*state=*/{column<Scalar>(qi), column<Scalar>(ni)},
        column<Scalar>(fall_qi), column<Scalar>(fall_ni),
        column<double>(work1), column<double>(workn),
        column<Scalar>(dz), column<Scalar>(rho),
    };
    const auto params = kdm6::sed::default_substep_advection_params();
    // dtcld is a Fortran REAL in the native boundary.  Keep the promoted f64
    // path as the independent comparison while making f32 use the exact input
    // REAL(4) value before it enters tensor arithmetic.
    const double call_dt = std::is_same<Scalar, float>::value
        ? static_cast<double>(static_cast<float>(dt)) : dt;
    const auto output = [&]() {
        if constexpr (Conservative) {
            return kdm6::sed::ice_substep_advection_conservative(
                inputs, mstep_col, mstep, n, call_dt, params);
        } else {
            return kdm6::sed::ice_substep_advection_torch(
                inputs, mstep_col, mstep, n, call_dt, params);
        }
    }();

    std::cout << "RUN " << label << '\n';
    print_field<Scalar>("qi", output.state.qi);
    print_field<Scalar>("ni", output.state.ni);
    print_field<Scalar>("fall_qi", output.fall_qi);
    print_field<Scalar>("fall_ni", output.fall_ni);
}

}  // namespace

int main() {
    int K = 0;
    double dt = 0.0;
    int mstep = 0;
    int n = 0;
    if (!(std::cin >> K >> dt >> mstep >> n) || K <= 0 || mstep <= 0 || n <= 0) {
        std::cerr << "expected: K dt mstep n followed by K rows of 8 values\n";
        return 2;
    }

    std::vector<Row> rows;
    rows.reserve(static_cast<size_t>(K));
    for (int k = 0; k < K; ++k) {
        Row row{};
        if (!(std::cin >> row.qi >> row.ni >> row.work1 >> row.workn
              >> row.rho >> row.dz >> row.fall_qi >> row.fall_ni)) {
            std::cerr << "expected 8 values for row " << k << '\n';
            return 2;
        }
        rows.push_back(row);
    }

    try {
        torch::set_num_threads(1);
        torch::set_num_interop_threads(1);
        torch::NoGradGuard no_grad;
        run_case<float, false>("legacy f32", rows, dt, mstep, n);
        run_case<float, true>("conservative f32", rows, dt, mstep, n);
        run_case<double, false>("legacy f64", rows, dt, mstep, n);
        run_case<double, true>("conservative f64", rows, dt, mstep, n);
    } catch (const c10::Error& error) {
        std::cerr << "torch error: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
