#include "kdm6/batch5_intermediate_ad.h"
#include <cassert>
#include <cmath>
#include <stdexcept>
#include <vector>
int main() {
    using namespace kdm6::batch5;
    auto opts=torch::TensorOptions().dtype(torch::kFloat64);
    std::vector<torch::Tensor> x,v;
    for (int i=0;i<16;++i) { x.push_back(torch::full({1,2},2.0,opts.requires_grad(true))); v.push_back(torch::full({1,2},0.0,opts)); }
    v[0]=torch::full({1,2},1.0,opts); v[12]=torch::full({1,2},2.0,opts);
    auto y=(x[0]*x[0]+3*x[12]).select(0,0).select(0,1);
    auto unrelated=torch::ones({},opts.requires_grad(true))*2;
    auto constant=torch::ones({},opts);
    auto result=intermediate_jvp({y,constant,unrelated},x,v);
    assert(result.size()==3 && result[0].status==IntermediateStatus::CONNECTED);
    // Test-only numeric inspection after AD; the internal graph path performs no scalar extraction.
    assert(std::abs(result[0].tangent.item<double>()-10.0)<1e-12);
    assert(result[1].status==IntermediateStatus::NO_GRAPH_PATH && result[2].status==IntermediateStatus::UNCONNECTED);
    auto again=intermediate_jvp({y},x,v); assert(std::abs(again[0].tangent.item<double>()-10.0)<1e-12);
    auto zero=v; zero[0]=torch::zeros_like(v[0]);zero[12]=torch::zeros_like(v[12]);
    auto z=intermediate_jvp({y},x,zero);assert(z[0].status==IntermediateStatus::CONNECTED && z[0].tangent.item<double>()==0.0);
    bool rejected=false;try { intermediate_jvp({y},x,std::vector<torch::Tensor>(15)); } catch (const c10::Error&) { rejected=true; } assert(rejected);
    auto bad=v; bad[0]=torch::zeros({1,3},opts);
    rejected=false;try { intermediate_jvp({y},x,bad); } catch (const c10::Error&) { rejected=true; } assert(rejected);
    bad=v; bad[0]=torch::zeros({1,2},torch::kFloat32);
    rejected=false;try { intermediate_jvp({y},x,bad); } catch (const c10::Error&) { rejected=true; } assert(rejected);
    rejected=false;try { intermediate_jvp({torch::ones({},torch::kBool)},x,v); } catch (const c10::Error&) { rejected=true; } assert(rejected);
}
