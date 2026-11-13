#include "kdm6/batch5_intermediate_ad.h"
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include <torch/csrc/autograd/autograd.h>
namespace kdm6::batch5 {
std::vector<IntermediateJvp> intermediate_jvp(
    const std::vector<torch::Tensor>& scalars,
    const std::vector<torch::Tensor>& leaves,
    const std::vector<torch::Tensor>& directions) {
    TORCH_CHECK(!scalars.empty() && scalars.size() <= 64, "batch5: scalar count must be 1..64");
    TORCH_CHECK(leaves.size() == 16 && directions.size() == 16, "batch5: 16 leaves and directions required");
    for (size_t i = 0; i < leaves.size(); ++i) {
        const auto& x = leaves[i]; const auto& v = directions[i];
        TORCH_CHECK(x.defined() && x.is_leaf() && x.requires_grad() && x.device().is_cpu() && x.scalar_type() == torch::kFloat64,
                    "batch5: CPU f64 differentiable leaf required");
        TORCH_CHECK(v.defined() && v.device() == x.device() && v.scalar_type() == x.scalar_type() && v.sizes() == x.sizes(),
                    "batch5: direction metadata mismatch");
    }
    std::vector<IntermediateJvp> out; out.reserve(scalars.size());
    for (const auto& y : scalars) {
        TORCH_CHECK(y.defined() && y.numel() == 1 && y.device().is_cpu() && y.scalar_type() == torch::kFloat64,
                    "batch5: CPU f64 scalar required");
        if (!y.requires_grad()) { out.push_back({IntermediateStatus::NO_GRAPH_PATH, torch::zeros_like(y)}); continue; }
        auto u = torch::zeros_like(y).requires_grad_(true);
        auto weighted = (y * u).sum();
        auto grads = torch::autograd::grad({weighted}, leaves, {}, true, true, true);
        auto inner = torch::zeros({}, y.options()); bool connected = false;
        for (size_t i = 0; i < grads.size(); ++i) {
            if (grads[i].defined()) { inner = inner + (grads[i] * directions[i]).sum(); connected = true; }
        }
        if (!connected) { out.push_back({IntermediateStatus::UNCONNECTED, torch::zeros_like(y)}); continue; }
        TORCH_CHECK(inner.requires_grad(), "batch5: connected reverse graph is not differentiable in cotangent");
        auto tangent = torch::autograd::grad({inner}, {u}, {}, true, false, true);
        TORCH_CHECK(tangent.size() == 1 && tangent[0].defined(), "batch5: missing scalar tangent");
        out.push_back({IntermediateStatus::CONNECTED, tangent[0]});
    }
    return out;
}
IntermediateVjp intermediate_vjp(const torch::Tensor& y,
    const std::vector<torch::Tensor>& leaves, const torch::Tensor& u) {
    TORCH_CHECK(leaves.size()==16, "batch5: 16 leaves required");
    for (const auto& x : leaves) {
        TORCH_CHECK(x.defined() && x.is_leaf() && x.requires_grad() && x.device().is_cpu() && x.scalar_type()==torch::kFloat64,
                    "batch5: CPU f64 differentiable leaf required");
    }
    TORCH_CHECK(y.defined() && y.numel()==1 && y.device().is_cpu() && y.scalar_type()==torch::kFloat64,
                "batch5: CPU f64 scalar required");
    TORCH_CHECK(u.defined() && u.numel()==1 && u.device()==y.device() && u.scalar_type()==y.scalar_type() && u.sizes()==y.sizes(),
                "batch5: scalar cotangent metadata mismatch");
    if (!y.requires_grad()) return {IntermediateStatus::NO_GRAPH_PATH, std::vector<torch::Tensor>(16)};
    auto grads=torch::autograd::grad({y},leaves,{u},true,false,true);
    bool connected=false;
    for (const auto& g:grads) if (g.defined()) connected=true;
    return {connected ? IntermediateStatus::CONNECTED : IntermediateStatus::UNCONNECTED, std::move(grads)};
}

}
#endif
