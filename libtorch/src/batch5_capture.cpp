#include "kdm6/batch5_capture.h"
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include <map>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace kdm6::batch5 {
namespace {
struct Context {
    bool on = false;
    bool entered = false;
    bool outer_set = false;
    bool is_top_first = false;
    std::string input_id, mode, family = "runtime", source_site;
    std::uint64_t observed_one_steps = 0;
    std::uint64_t runtime_call = 0, one_step_call = 0, outer_loop = 0, substep_n = 0;
    std::vector<Record> data;
    InputLeaves leaves;
    std::map<std::tuple<std::uint64_t,std::uint64_t,std::string,std::uint64_t,std::string,std::string,std::string,std::string,std::int64_t,std::int64_t>,std::uint64_t> ordinals;
};
thread_local Context ctx;
thread_local std::uint64_t runtime_sequence = 0;
void add(const char* stage, const char* field, const char* scope,
         std::int64_t b, std::int64_t k, std::int64_t level, std::int64_t B, std::int64_t K, const torch::Tensor& t) {
    if (!ctx.on) return;
    if (!t.defined() || ctx.data.size() >= 2000000) throw std::runtime_error("batch5 capture undefined tensor or record limit");
    const std::string kind = t.scalar_type() == torch::kBool ? "mask" : "value";
    auto key=std::make_tuple(ctx.one_step_call,ctx.outer_loop,ctx.family,ctx.substep_n,std::string(scope),std::string(stage),std::string(field),kind,b,k);
    auto ordinal=ctx.ordinals[key]++;
    ctx.data.push_back(Record{ctx.input_id,ctx.mode,ctx.family,scope,stage,field,
        kind,"none","none","none","none",ctx.runtime_call,ctx.one_step_call,
        ctx.outer_loop,ctx.substep_n,ordinal,b,k,level,B,K,t});
}
}
void begin(const std::string& input_id,const std::string& mode,std::uint64_t runtime_call) {
    if (input_id.empty() || input_id.size()>=128 || (mode!="capture_on_value" && mode!="center_joint_graph") || runtime_call==0)
        throw std::invalid_argument("batch5 capture context invalid");
    if (ctx.on) throw std::runtime_error("batch5 prior context must be explicitly cleared");
    ctx=Context{}; ctx.on=true;ctx.input_id=input_id;ctx.mode=mode;ctx.runtime_call=runtime_call;
}
void clear(){ctx=Context{};}
bool enabled(){return ctx.on;}
void enter_runtime(bool value_only){
    const auto observed=++runtime_sequence;
    if(ctx.on) {
        if(ctx.entered || observed!=ctx.runtime_call || value_only!=(ctx.mode=="capture_on_value"))
            throw std::runtime_error("batch5 actual runtime sequence, lifecycle or mode mismatch");
        ctx.entered=true;
    }
}
void retain_inputs(const std::vector<torch::Tensor>& state,const std::vector<torch::Tensor>& forcing){if(ctx.on)ctx.leaves={state,forcing};}
const InputLeaves& inputs(){return ctx.leaves;}
const std::vector<Record>& records(){return ctx.data;}
void outer(std::uint64_t i){if(ctx.on){if(!ctx.entered)throw std::runtime_error("batch5 runtime not entered");ctx.outer_set=true;ctx.outer_loop=i;ctx.one_step_call=0;ctx.family="outer";ctx.substep_n=0;}}
void micro_step(){if(ctx.on){if(!ctx.entered || !ctx.outer_set)throw std::runtime_error("batch5 missing runtime/outer context");ctx.is_top_first=false;ctx.family="microphysics";ctx.substep_n=0;ctx.one_step_call=++ctx.observed_one_steps;}}
void phase(const char* family,std::uint64_t n){if(ctx.on){ctx.family=family;ctx.substep_n=n;}}
void orientation(bool top){if(ctx.on)ctx.is_top_first=top;}
bool top_first(){return ctx.is_top_first;}
void site(const char* name){if(ctx.on)ctx.source_site=name ? name : "";}
const std::string& site(){return ctx.source_site;}
void full(const char* stage,const char* field,const torch::Tensor& t,bool top_first){
    if(!ctx.on)return;
    if(t.dim()!=2 || t.size(0)!=1 || t.size(1)!=39)
        throw std::runtime_error("batch5 narrow capture requires rank-2 B=1 K=39");
    auto B=t.size(0),K=t.size(1);
    for(std::int64_t b=0;b<B;++b)for(std::int64_t k=0;k<K;++k){
        auto storage_k=top_first?k:K-1-k;
        add(stage,field,"layer",b,k,K-k,B,K,t.select(0,b).select(0,storage_k));
    }
}
void column(const char* stage,const char* field,const torch::Tensor& t){
    if(!ctx.on)return;
    if(t.dim()!=1 || t.size(0)!=1)throw std::runtime_error("batch5 narrow capture requires B=1 column tensor");
    for(std::int64_t b=0;b<t.size(0);++b)add(stage,field,"column",b,-1,-1,t.size(0),-1,t.select(0,b));
}
void layer(const char* stage,const char* field,const torch::Tensor& t,std::int64_t k,std::int64_t K){
    if(!ctx.on)return;
    if(t.dim()!=1 || t.size(0)!=1 || K!=39 || k<0 || k>=K)throw std::runtime_error("batch5 narrow capture requires B=1 K=39 layer tensor");
    for(std::int64_t b=0;b<t.size(0);++b)add(stage,field,"layer",b,k,K-k,t.size(0),K,t.select(0,b));
}
}
#endif
