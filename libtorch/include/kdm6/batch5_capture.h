#pragma once
// Private research-only tensor sidecar. This is not an ABI for operational use.
// Retained tensors, including scalar views, stay attached to their original graph.
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include <torch/torch.h>
#include <cstdint>
#include <string>
#include <vector>

namespace kdm6::batch5 {
struct Record {
    std::string input_id, mode, family, scope, stage, field;
    // Forward observations are not derivative results. A later JVP/VJP reader
    // must attach its own exact direction, seed hash and cotangent identity.
    std::string record_kind, derivative_mode, direction_id, seed_sha256, cotangent_id;
    std::uint64_t runtime_call, one_step_call, outer_loop, substep_n, event_ordinal;
    std::int64_t b_zero, k_zero, native_level_bottom_first, B, K;
    torch::Tensor tensor;
};
struct InputLeaves { std::vector<torch::Tensor> state, forcing; };
// Narrow prototype: full() requires rank-2 B=1,K=39 and rejects broadcasts;
// layer/column likewise require B=1 and layer K=39. No general host API.
// Thread-local ownership: begin/call/read/AD/clear must run on the same OS thread.
// Internal vector references are invalidated by growth or clear and must not
// escape the DSO. The test-only C bridge offers bounded POD copy-out only.
void begin(const std::string& input_id, const std::string& mode, std::uint64_t runtime_call);
void clear();
bool enabled();
// Counts all actual runtime entries in this OS thread, even if capture is off.
// If a context is active it must match the caller-supplied expected sequence.
void enter_runtime(bool value_only);
void retain_inputs(const std::vector<torch::Tensor>& state, const std::vector<torch::Tensor>& forcing);
const InputLeaves& inputs();
const std::vector<Record>& records();
void outer(std::uint64_t outer_loop);
void micro_step();
void phase(const char* family, std::uint64_t substep_n);
void orientation(bool top_first);
bool top_first();
void site(const char* name);
const std::string& site();
void full(const char* stage, const char* field, const torch::Tensor& tensor, bool top_first);
void column(const char* stage, const char* field, const torch::Tensor& tensor);
void layer(const char* stage, const char* field, const torch::Tensor& tensor,
           std::int64_t k_top, std::int64_t levels);
}
#endif
