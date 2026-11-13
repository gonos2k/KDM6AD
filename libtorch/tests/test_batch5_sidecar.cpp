// Synthetic sidecar copy-out contract only; not a model run.
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include "kdm6/batch5_capture.h"
#include "kdm6_batch5_sidecar.h"
#include <cassert>
#include <cstdint>
#include <cstring>
#include <thread>
#include <atomic>
#include <stdexcept>
#include <vector>
#include <limits>

int main(){
    assert(kdm6_batch5_begin_c("synthetic", "capture_on_value", 1)==0);
    assert(kdm6_batch5_begin_c("duplicate", "capture_on_value", 1)!=0);
    kdm6::batch5::enter_runtime(true);
    auto value=torch::full({1,39},1.0,torch::TensorOptions().dtype(torch::kFloat64));
    kdm6::batch5::full("synthetic","sample",value,false);
    assert(kdm6_batch5_count_c()==39);
    bool bad_shape_rejected=false;
    try { kdm6::batch5::full("synthetic","bad_shape",torch::full({1,1},1.0),false); }
    catch (const std::runtime_error&) { bad_shape_rejected=true; }
    assert(bad_shape_rejected && kdm6_batch5_count_c()==39);
    bool other_thread_has_no_context=false;
    std::thread other([&] { other_thread_has_no_context = kdm6_batch5_count_c()==0; });
    other.join();assert(other_thread_has_no_context);
    kdm6_batch5_meta meta{};meta.abi_version=KDM6_BATCH5_META_VERSION;meta.struct_size=sizeof(meta);
    auto before=meta;
    assert(kdm6_batch5_metadata_c(0,&meta,sizeof(meta)-1)!=0);
    assert(std::memcmp(&meta,&before,sizeof(meta))==0);
    assert(kdm6_batch5_metadata_c(39,&meta,sizeof(meta))!=0);
    assert(std::memcmp(&meta,&before,sizeof(meta))==0);
    meta.abi_version=2;before=meta;
    assert(kdm6_batch5_metadata_c(0,&meta,sizeof(meta))!=0);
    assert(std::memcmp(&meta,&before,sizeof(meta))==0);
    meta.abi_version=KDM6_BATCH5_META_VERSION;meta.struct_size=sizeof(meta)-1;before=meta;
    assert(kdm6_batch5_metadata_c(0,&meta,sizeof(meta))!=0);
    assert(std::memcmp(&meta,&before,sizeof(meta))==0);
    meta.struct_size=sizeof(meta);
    assert(kdm6_batch5_metadata_c(0,&meta,sizeof(meta))==0);
    assert(meta.abi_version==KDM6_BATCH5_META_VERSION && meta.struct_size==sizeof(meta));
    assert(meta.runtime_call==1 && meta.b_zero==0 && meta.k_zero==0 && meta.native_level_bottom_first==39);
    assert(std::strcmp(meta.derivative_mode,"none")==0 && std::strcmp(meta.direction_id,"none")==0 && std::strcmp(meta.seed_sha256,"none")==0);
    std::uint64_t bits=0;int kind=0;
    assert(kdm6_batch5_value_word_c(0,&bits,&kind)==0 && bits==UINT64_C(0x3ff0000000000000) && kind==2);
    assert(kdm6_batch5_value_word_c(0,nullptr,&kind)!=0 && kdm6_batch5_value_word_c(0,&bits,nullptr)!=0);
    bits=UINT64_C(0x1122334455667788);
    assert(kdm6_batch5_value_word_c(0,&bits,reinterpret_cast<int*>(&bits))!=0 && bits==UINT64_C(0x1122334455667788));
    bits=123;kind=77;assert(kdm6_batch5_value_word_c(39,&bits,&kind)!=0 && bits==123 && kind==77);
    // Distinguish storage orientation using all 39 nonconstant source levels.
    auto vertical=torch::arange(1,40,torch::TensorOptions().dtype(torch::kFloat64)).reshape({1,39});
    kdm6::batch5::full("orientation","bottom_first",vertical,false);
    kdm6::batch5::full("orientation","top_first",vertical,true);
    assert(kdm6_batch5_count_c()==117);
    auto check_level = [&](std::uint64_t index,std::int64_t k,std::int64_t native,double expected) {
        kdm6_batch5_meta m{};m.abi_version=KDM6_BATCH5_META_VERSION;m.struct_size=sizeof(m);
        assert(kdm6_batch5_metadata_c(index,&m,sizeof(m))==0);
        assert(m.k_zero==k && m.native_level_bottom_first==native && m.B==1 && m.K==39);
        std::uint64_t observed=0,expected_bits=0;int type=0;
        std::memcpy(&expected_bits,&expected,sizeof(expected));
        assert(kdm6_batch5_value_word_c(index,&observed,&type)==0 && type==2 && observed==expected_bits);
    };
    check_level(39,0,39,39.0);check_level(77,38,1,1.0);  // bottom-first storage
    check_level(78,0,39,1.0);check_level(116,38,1,39.0); // top-first storage
    kdm6_batch5_clear_c();
    assert(kdm6_batch5_begin_c("synthetic_graph", "center_joint_graph", 2)==0);
    kdm6::batch5::enter_runtime(false);
    auto leaf=torch::full({1,39},1.0,torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true));
    std::vector<torch::Tensor> sx, fx;
    for(int i=0;i<12;++i) sx.push_back(i==0 ? leaf : torch::ones({1,39},torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true)));
    for(int i=0;i<4;++i) fx.push_back(torch::ones({1,39},torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true)));
    kdm6::batch5::retain_inputs(sx,fx);
    kdm6::batch5::full("synthetic","graph",leaf*2.0,false);
    auto joint=leaf*leaf+3.0*fx[0];
    kdm6::batch5::full("synthetic","joint",joint,false);
    kdm6::batch5::full("synthetic","constant",torch::ones({1,39},torch::kFloat64),false);
    auto unrelated=torch::ones({1,39},torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true))*2.0;
    kdm6::batch5::full("synthetic","unrelated",unrelated,false);
    kdm6::batch5::full("synthetic","mask",torch::ones({1,39},torch::kBool),false);
    kdm6::batch5::full("synthetic","infinite_grad",leaf*std::numeric_limits<double>::infinity(),false);
    const int synthetic_handle=1; kdm6::batch5::bind_handle(&synthetic_handle);
    std::uint64_t token=0; assert(kdm6_batch5_binding_token_c(&synthetic_handle,&token)==0 && token!=0);
    const int wrong_handle=2; std::uint64_t untouched_token=77;
    assert(kdm6_batch5_binding_token_c(&wrong_handle,&untouched_token)!=0 && untouched_token==77);
    bool wrong_thread_token_rejected=false;
    std::thread getter([&] { std::uint64_t z=77;wrong_thread_token_rejected=kdm6_batch5_binding_token_c(&synthetic_handle,&z)!=0 && z==77; });getter.join();assert(wrong_thread_token_rejected);
    double seed[624]{}; seed[38]=1.; double tangent=99.;int derivative_status=99;
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&tangent,&derivative_status)==0 && tangent==2. && derivative_status==0);
    double joint_seed[624]{}; joint_seed[38]=1.;joint_seed[12*39+38]=2.;
    double joint_jvp=0.;int joint_status=-1;
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,39,joint_seed,624,&joint_jvp,&joint_status)==0 && joint_jvp==8. && joint_status==0);
    double grad[624];for(double& x:grad)x=99.;std::uint16_t mask=0;int vstatus=-1;
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,2.,grad,624,&mask,&vstatus)==0 && vstatus==0 && mask==0x1001);
    assert(grad[38]==4. && grad[12*39+38]==6. && grad[39]==0.);
    double dot=0.;for(int i=0;i<624;++i)dot+=grad[i]*joint_seed[i];assert(dot==joint_jvp*2.);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,0.,grad,624,&mask,&vstatus)==0 && vstatus==0 && mask==0x1001 && grad[38]==0.);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,78,1.,grad,624,&mask,&vstatus)==0 && vstatus==1 && mask==0);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,117,1.,grad,624,&mask,&vstatus)==0 && vstatus==2 && mask==0);
    for(double& x:grad)x=99.;mask=77;vstatus=77;
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,156,1.,grad,624,&mask,&vstatus)!=0 && grad[0]==99. && mask==77 && vstatus==77);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token+1,39,1.,grad,624,&mask,&vstatus)!=0 && grad[0]==99. && mask==77 && vstatus==77);
    assert(kdm6_batch5_intermediate_vjp_c(&wrong_handle,token,39,1.,grad,624,&mask,&vstatus)!=0 && grad[0]==99. && mask==77 && vstatus==77);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,195,1.,grad,624,&mask,&vstatus)!=0 && grad[0]==99. && mask==77 && vstatus==77);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,1.,grad,623,&mask,&vstatus)!=0 && grad[0]==99. && mask==77 && vstatus==77);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,1.,grad,624,reinterpret_cast<std::uint16_t*>(&grad[0]),&vstatus)!=0 && grad[0]==99. && vstatus==77);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,1.,grad,624,&mask,reinterpret_cast<int*>(&grad[1]))!=0 && grad[1]==99. && mask==77);
    int overlap=77;
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,1.,grad,624,reinterpret_cast<std::uint16_t*>(&overlap),&overlap)!=0 && overlap==77 && grad[0]==99.);
    assert(kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,std::numeric_limits<double>::infinity(),grad,624,&mask,&vstatus)!=0 && grad[0]==99. && mask==77 && vstatus==77);
    bool foreign_vjp_rejected=false;
    std::thread wrong_vjp([&] { double a[624];for(double& z:a)z=42.;std::uint16_t b=42;int c=42;foreign_vjp_rejected=kdm6_batch5_intermediate_vjp_c(&synthetic_handle,token,39,1.,a,624,&b,&c)!=0 && a[0]==42. && b==42 && c==42; });wrong_vjp.join();assert(foreign_vjp_rejected);
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,39,joint_seed,624,&joint_jvp,&joint_status)==0 && joint_jvp==8.);
    tangent=99.;derivative_status=99;
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token+1,0,seed,624,&tangent,&derivative_status)!=0 && tangent==99. && derivative_status==99);
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,623,&tangent,&derivative_status)!=0 && tangent==99. && derivative_status==99);
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&seed[0],&derivative_status)!=0 && seed[0]==0. && derivative_status==99);
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&tangent,reinterpret_cast<int*>(&tangent))!=0 && tangent==99.);
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&tangent,reinterpret_cast<int*>(&seed[0]))!=0 && tangent==99. && seed[0]==0.);
    seed[0]=std::numeric_limits<double>::quiet_NaN();
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&tangent,&derivative_status)!=0 && tangent==99. && derivative_status==99); seed[0]=0.;
    bool foreign_thread_rejected=false;
    std::thread wrong([&] { double a=42.;int b=42;foreign_thread_rejected=kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&a,&b)!=0 && a==42. && b==42; });wrong.join();assert(foreign_thread_rejected);
    kdm6::batch5::invalidate_handle(&synthetic_handle);
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&tangent,&derivative_status)!=0 && tangent==99. && derivative_status==99);
    bits=123;kind=77;
    assert(kdm6_batch5_value_word_c(0,&bits,&kind)!=0 && bits==123 && kind==77);
    kdm6_batch5_clear_c();
    assert(kdm6_batch5_count_c()==0);
    assert(kdm6_batch5_begin_c("reused_address", "center_joint_graph", 3)==0);
    kdm6::batch5::enter_runtime(false);
    kdm6::batch5::retain_inputs(sx,fx);
    kdm6::batch5::full("synthetic","graph",leaf*2.0,false);
    kdm6::batch5::bind_handle(&synthetic_handle);
    std::uint64_t new_token=0; assert(kdm6_batch5_binding_token_c(&synthetic_handle,&new_token)==0 && new_token!=token);
    tangent=99.; derivative_status=99;
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,token,0,seed,624,&tangent,&derivative_status)!=0 && tangent==99. && derivative_status==99);
    assert(kdm6_batch5_intermediate_jvp_c(&synthetic_handle,new_token,0,seed,624,&tangent,&derivative_status)==0 && tangent==2. && derivative_status==0);
    kdm6_batch5_clear_c();
    assert(kdm6_batch5_begin_c("wrong_sequence", "capture_on_value", 5)==0);
    bool sequence_rejected=false;
    try { kdm6::batch5::enter_runtime(true); }
    catch (const std::runtime_error&) { sequence_rejected=true; }
    assert(sequence_rejected);kdm6_batch5_clear_c();
    // Cross-thread close, same-address rebinding, then stale owner's clear.
    const int reused_handle=3; std::atomic<int> stage{0};
    std::atomic<std::uint64_t> old_token{0}; bool survived=false;
    std::thread old_owner([&] {
        assert(kdm6_batch5_begin_c("old", "center_joint_graph", 1)==0);
        kdm6::batch5::enter_runtime(false); kdm6::batch5::bind_handle(&reused_handle);
        std::uint64_t t=0; assert(kdm6_batch5_binding_token_c(&reused_handle,&t)==0); old_token.store(t);
        stage.store(1); while(stage.load()<2) std::this_thread::yield();
        kdm6_batch5_clear_c(); stage.store(3);
    });
    while(stage.load()<1) std::this_thread::yield();
    kdm6::batch5::invalidate_handle(&reused_handle);
    std::thread new_owner([&] {
        assert(kdm6_batch5_begin_c("new", "center_joint_graph", 1)==0);
        kdm6::batch5::enter_runtime(false);
        auto x=torch::full({1,39},2.0,torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true));
        std::vector<torch::Tensor> state(12),forcing(4);
        for(auto& t:state)t=torch::ones({1,39},torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true));
        for(auto& t:forcing)t=torch::ones({1,39},torch::TensorOptions().dtype(torch::kFloat64).requires_grad(true));
        state[0]=x;kdm6::batch5::retain_inputs(state,forcing);
        kdm6::batch5::full("synthetic","graph",x*2.0,false);
        kdm6::batch5::bind_handle(&reused_handle);
        std::uint64_t t=0;assert(kdm6_batch5_binding_token_c(&reused_handle,&t)==0 && t!=old_token.load());
        stage.store(2);while(stage.load()<3)std::this_thread::yield();
        double v[624]{};v[38]=1.;double out=91.;int status=91;
        assert(kdm6_batch5_intermediate_jvp_c(&reused_handle,old_token.load(),0,v,624,&out,&status)!=0 && out==91. && status==91);
        survived=kdm6_batch5_intermediate_jvp_c(&reused_handle,t,0,v,624,&out,&status)==0 && out==2. && status==0;
        double g[624];for(double& a:g)a=91.;std::uint16_t cm=91;int st=91;
        assert(kdm6_batch5_intermediate_vjp_c(&reused_handle,old_token.load(),0,1.,g,624,&cm,&st)!=0 && g[0]==91. && cm==91 && st==91);
        assert(kdm6_batch5_intermediate_vjp_c(&reused_handle,t,0,1.,g,624,&cm,&st)==0 && cm==1 && st==0 && g[38]==2.);
        kdm6_batch5_clear_c();
    });
    old_owner.join();new_owner.join();assert(survived);
}

#endif
