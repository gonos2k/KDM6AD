// Synthetic sidecar copy-out contract only; not a model run.
#ifdef KDM6_BATCH5_RESEARCH_CAPTURE
#include "kdm6/batch5_capture.h"
#include "kdm6_batch5_sidecar.h"
#include <cassert>
#include <cstdint>
#include <cstring>
#include <thread>
#include <stdexcept>

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
    kdm6::batch5::full("synthetic","graph",leaf*2.0,false);
    bits=123;kind=77;
    assert(kdm6_batch5_value_word_c(0,&bits,&kind)!=0 && bits==123 && kind==77);
    kdm6_batch5_clear_c();
    assert(kdm6_batch5_count_c()==0);
    assert(kdm6_batch5_begin_c("wrong_sequence", "capture_on_value", 4)==0);
    bool sequence_rejected=false;
    try { kdm6::batch5::enter_runtime(true); }
    catch (const std::runtime_error&) { sequence_rejected=true; }
    assert(sequence_rejected);kdm6_batch5_clear_c();
}

#endif
