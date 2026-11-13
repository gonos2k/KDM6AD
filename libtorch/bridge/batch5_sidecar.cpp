// Research-only bounded copy-out. No graph tensor or internal pointer escapes.
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include "kdm6_c_api.h"
#include "kdm6_batch5_sidecar.h"
#include "kdm6/batch5_capture.h"
#include "kdm6/batch5_intermediate_ad.h"
#include <cmath>
#include <vector>
#include <cstring>
#include <cstdint>
#include <string>
namespace {
template<std::size_t N> bool copy_string(char (&dst)[N],const std::string& src){
    if(src.size()>=N)return false;
    std::memcpy(dst,src.data(),src.size());dst[src.size()]='\0';return true;
}
}
extern "C" KDM6_C_API int kdm6_batch5_begin_c(const char* input,const char* mode,std::uint64_t call){
    try { if(!input || !mode)return -1; kdm6::batch5::begin(input,mode,call);return 0; } catch (...) {return -1;}
}
extern "C" KDM6_C_API std::uint64_t kdm6_batch5_count_c(){return kdm6::batch5::records().size();}
extern "C" KDM6_C_API int kdm6_batch5_metadata_c(std::uint64_t n,kdm6_batch5_meta* out,std::size_t size){
    try {
        const auto& records=kdm6::batch5::records();if(!out || size<sizeof(*out) || n>=records.size())return -1;
        if(out->abi_version!=KDM6_BATCH5_META_VERSION || out->struct_size!=sizeof(*out))return -1;
        const auto& r=records[n];kdm6_batch5_meta m{};
        m.abi_version=KDM6_BATCH5_META_VERSION;m.struct_size=sizeof(m);
        if(!copy_string(m.input_id,r.input_id) || !copy_string(m.mode,r.mode) || !copy_string(m.family,r.family) ||
           !copy_string(m.scope,r.scope) || !copy_string(m.stage,r.stage) || !copy_string(m.field,r.field) ||
           !copy_string(m.record_kind,r.record_kind) || !copy_string(m.derivative_mode,r.derivative_mode) ||
           !copy_string(m.direction_id,r.direction_id) || !copy_string(m.seed_sha256,r.seed_sha256) ||
           !copy_string(m.cotangent_id,r.cotangent_id))return -1;
        m.runtime_call=r.runtime_call;m.one_step_call=r.one_step_call;m.outer_loop=r.outer_loop;
        m.substep_n=r.substep_n;m.event_ordinal=r.event_ordinal;m.b_zero=r.b_zero;m.k_zero=r.k_zero;
        m.native_level_bottom_first=r.native_level_bottom_first;m.B=r.B;m.K=r.K;*out=m;return 0;
    } catch (...) {return -1;}
}
extern "C" KDM6_C_API int kdm6_batch5_value_word_c(std::uint64_t n,std::uint64_t* out,int* kind){
    try {
        const auto& records=kdm6::batch5::records();if(!out || !kind || n>=records.size())return -1;
        const auto& r=records[n];const auto& t=r.tensor;
        // Explicitly value-only, after forward; never read/detach a graph value here.
        if(r.mode!="capture_on_value" || !t.defined() || !t.device().is_cpu() || t.numel()!=1 || !t.is_contiguous())return -1;
        std::uint64_t bits=0;int type=0;
        if(t.scalar_type()==torch::kFloat64){double v=*t.data_ptr<double>();std::memcpy(&bits,&v,sizeof(v));type=2;}
        else if(t.scalar_type()==torch::kFloat32){float v=*t.data_ptr<float>();std::uint32_t u;std::memcpy(&u,&v,sizeof(v));bits=u;type=1;}
        else if(t.scalar_type()==torch::kBool){bits=*t.data_ptr<bool>()?1:0;type=3;}
        else return -1;
        *out=bits;*kind=type;return 0;
    } catch (...) {return -1;}
}
extern "C" KDM6_C_API int kdm6_batch5_binding_token_c(const void* handle,std::uint64_t* output) {
    try { if(!output)return -1; auto token=kdm6::batch5::binding_token(handle); *output=token; return 0; } catch (...) { return -1; }
}
extern "C" KDM6_C_API int kdm6_batch5_intermediate_jvp_c(const void* handle,std::uint64_t token,std::uint64_t n,const double* direction,std::size_t count,double* output,int* status) {
    try {
        if (!direction || !output || !status || count!=624) return -1;
        auto lock=kdm6::batch5::lock_bound_handle(handle,token);
        const auto& records=kdm6::batch5::records();
        const auto& inputs=kdm6::batch5::inputs();
        if (n>=records.size() || records[n].mode!="center_joint_graph" || records[n].record_kind!="value" || inputs.state.size()!=12 || inputs.forcing.size()!=4) return -1;
        std::vector<torch::Tensor> leaves, seeds; leaves.reserve(16);seeds.reserve(16);
        for (const auto& t:inputs.state) leaves.push_back(t);
        for (const auto& t:inputs.forcing) leaves.push_back(t);
        for (std::size_t i=0;i<16;++i) {
            if (!leaves[i].defined() || leaves[i].sizes()!=torch::IntArrayRef({1,39})) return -1;
            for(std::size_t k=0;k<39;++k) if(!std::isfinite(direction[i*39+k])) return -1;
            seeds.push_back(torch::from_blob(const_cast<double*>(direction+i*39), {1,39}, torch::TensorOptions().dtype(torch::kFloat64)).clone());
        }
        auto result=kdm6::batch5::intermediate_jvp({records[n].tensor},leaves,seeds);
        if(result.size()!=1 || !result[0].tangent.defined() || !result[0].tangent.device().is_cpu() || result[0].tangent.numel()!=1) return -1;
        double v=*result[0].tangent.data_ptr<double>();
        if(!std::isfinite(v)) return -1;
        int code=static_cast<int>(result[0].status); *output=v; *status=code; return 0;
    } catch (...) { return -1; }
}
extern "C" KDM6_C_API void kdm6_batch5_clear_c(){kdm6::batch5::clear();}
#endif
