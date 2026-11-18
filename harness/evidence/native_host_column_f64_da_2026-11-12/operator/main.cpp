#include <torch/torch.h>
#include <torch/csrc/autograd/autograd.h>
#include <ATen/ops/_make_dual.h>
#include <ATen/ops/_unpack_dual.h>
#include <cmath>
#include <iomanip>
#include <iostream>
#include <stdexcept>
int main() {
  auto opt=torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);
  const double h=1e-6;
  std::cout<<std::setprecision(17)<<"case,raw,cap,d_raw,d_cap,value,jvp,vjp_raw,vjp_cap,forward_difference,backward_difference\n";
  for (int c=0;c<3;c++) for (auto dir : {std::pair<double,double>{1.,0.}, {0.,1.}, {2.,-1.}}) {
    double a=c==0?1.:c==1?2.:3., b=2.;
    auto x=torch::tensor(a,opt.requires_grad(true)), y=torch::tensor(b,opt.requires_grad(true));
    auto out=torch::minimum(x,y);
    auto grad=torch::autograd::grad({out},{x,y});
    auto level=torch::autograd::forward_ad::enter_dual_level();
    auto dx=at::_make_dual(torch::tensor(a,opt),torch::tensor(dir.first,opt),level);
    auto dy=at::_make_dual(torch::tensor(b,opt),torch::tensor(dir.second,opt),level);
    auto parts=at::_unpack_dual(torch::minimum(dx,dy),level);
    double jvp=std::get<1>(parts).item<double>();
    torch::autograd::forward_ad::exit_dual_level(level);
    double ga=grad[0].item<double>(),gb=grad[1].item<double>(),v=out.item<double>();
    double fp=(std::min(a+h*dir.first,b+h*dir.second)-v)/h;
    double fm=(v-std::min(a-h*dir.first,b-h*dir.second))/h;
    double ea=c==0?1.:c==1?.5:0., eb=1.-ea;
    if (ga!=ea || gb!=eb || jvp!=ea*dir.first+eb*dir.second || v!=std::min(a,b)) throw std::runtime_error("operator gradient contract failed");
    std::cout<<(c==0?"raw_lt_cap":c==1?"raw_eq_cap":"raw_gt_cap")<<','<<a<<','<<b<<','<<dir.first<<','<<dir.second<<','<<v<<','<<jvp<<','<<ga<<','<<gb<<','<<fp<<','<<fm<<'\n';
  }
}
