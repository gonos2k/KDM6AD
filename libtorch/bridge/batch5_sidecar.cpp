// Research-only bounded copy-out. No graph tensor or internal pointer escapes.
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include "kdm6_c_api.h"
#include "kdm6_batch5_sidecar.h"
#include "kdm6/batch5_capture.h"
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
extern "C" KDM6_C_API void kdm6_batch5_clear_c(){kdm6::batch5::clear();}
#endif
