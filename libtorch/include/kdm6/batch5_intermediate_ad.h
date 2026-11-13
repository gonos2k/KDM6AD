#pragma once
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include <torch/torch.h>
#include <vector>
namespace kdm6::batch5 {
enum class IntermediateStatus { CONNECTED, NO_GRAPH_PATH, UNCONNECTED };
struct IntermediateJvp { IntermediateStatus status; torch::Tensor tangent; };
// Undefined gradient slots remain undefined: caller must preserve connectivity separately.
struct IntermediateVjp { IntermediateStatus status; std::vector<torch::Tensor> gradients; };
// Internal research kernel: returned tangent remains a tensor, no ABI or model call.
// The caller owns graph/record lifecycle and must authenticate context separately.
std::vector<IntermediateJvp> intermediate_jvp(
    const std::vector<torch::Tensor>& scalars,
    const std::vector<torch::Tensor>& leaves,
    const std::vector<torch::Tensor>& directions);
IntermediateVjp intermediate_vjp(const torch::Tensor& scalar,
    const std::vector<torch::Tensor>& leaves, const torch::Tensor& cotangent);
}
#endif
