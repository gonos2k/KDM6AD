#include "kdm6/runtime.h"

#include <array>
#include <cerrno>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

namespace {
constexpr std::array<char, 8> kIn{{'K','6','B','A','T','I','1','\0'}};
constexpr std::array<char, 8> kOut{{'K','6','B','A','T','O','1','\0'}};
constexpr uint32_t kVersion=1, kNS=12, kNF=4, kNP=3, kMaxB=4096, kMaxL=256;
constexpr size_t kIH=44, kOH=20;
static_assert(sizeof(double)==8 && std::numeric_limits<double>::is_iec559, "requires IEEE binary64");
[[noreturn]] void fail(const std::string& s) { throw std::runtime_error(s); }
bool little() { uint16_t x=1; return *reinterpret_cast<unsigned char*>(&x)==1; }
uint32_t u32(const unsigned char* p) { uint32_t x; std::memcpy(&x,p,4); return x; }
double f64(const unsigned char* p) { double x; std::memcpy(&x,p,8); return x; }
void put32(std::vector<unsigned char>& b,uint32_t x) { auto p=reinterpret_cast<unsigned char*>(&x); b.insert(b.end(),p,p+4); }
void put64(std::vector<unsigned char>& b,double x) { auto p=reinterpret_cast<unsigned char*>(&x); b.insert(b.end(),p,p+8); }

std::vector<unsigned char> read(const std::filesystem::path& p) {
  struct stat st{}; if (::stat(p.c_str(),&st)||!S_ISREG(st.st_mode)||st.st_size<static_cast<off_t>(kIH)) fail("request must be a regular file with a complete header");
  std::ifstream in(p,std::ios::binary); std::array<unsigned char,kIH> h{}; in.read((char*)h.data(),h.size());
  if(in.gcount()!=static_cast<std::streamsize>(h.size())||std::memcmp(h.data(),kIn.data(),8)) fail("bad or truncated request header");
  uint32_t v=u32(h.data()+8), B=u32(h.data()+12), L=u32(h.data()+16);
  if(v!=kVersion) fail("unsupported request version"); if(!B||B>kMaxB||!L||L>kMaxL) fail("B or L outside supported bounds");
  uint64_t n=uint64_t(kNS+kNF)*B*L+B; uint64_t size=kIH+n*8;
  if(uint64_t(st.st_size)!=size) fail("request length does not match declared B,L");
  std::vector<unsigned char> b(size); std::memcpy(b.data(),h.data(),kIH); in.read((char*)b.data()+kIH,size-kIH);
  if(in.gcount()!=static_cast<std::streamsize>(size-kIH)) fail("truncated payload"); char extra; if(in.get(extra)) fail("trailing bytes"); return b;
}
void write_all(int fd,const unsigned char* p,size_t n) { size_t i=0; while(i<n){ssize_t k=::write(fd,p+i,n-i); if(k<0&&errno==EINTR)continue; if(k<=0)fail("failed writing output"); i+=k;} }
void publish(const std::filesystem::path& p,const std::vector<unsigned char>& b) {
  auto dir=p.parent_path(); if(dir.empty())dir="."; if(!std::filesystem::is_directory(dir))fail("output directory does not exist");
  std::filesystem::path tmp; int fd=-1;
  for(int n=0;n<100;n++){tmp=dir/("."+p.filename().string()+".tmp."+std::to_string(getpid())+"."+std::to_string(n)); fd=::open(tmp.c_str(),O_WRONLY|O_CREAT|O_EXCL,0600); if(fd>=0)break; if(errno!=EEXIST)fail("cannot create temporary output");}
  if(fd<0)fail("cannot reserve temporary output"); bool exists=true;
  try { write_all(fd,b.data(),b.size()); if(fsync(fd))fail("cannot sync output"); if(close(fd))fail("cannot close output"); fd=-1; if(link(tmp.c_str(),p.c_str()))fail("cannot publish output without clobbering"); if(unlink(tmp.c_str()))fail("published output but temporary cleanup failed"); exists=false; }
  catch(...){if(fd>=0)close(fd); if(exists)unlink(tmp.c_str()); throw;}
}
void run(const std::filesystem::path& ip,const std::filesystem::path& op) {
  if(!little())fail("protocol requires little-endian host"); auto b=read(ip); uint32_t B=u32(b.data()+12),L=u32(b.data()+16);
  double dt=f64(b.data()+20), nl=f64(b.data()+28), ns=f64(b.data()+36);
  if(!std::isfinite(dt)||!std::isfinite(nl)||!std::isfinite(ns)||dt<=0||nl<0||ns<0)fail("invalid dt or ncmin metadata");
  size_t per=size_t(B)*L, sn=size_t(kNS)*per, fn=size_t(kNF)*per; std::vector<double> sv(sn),fv(fn),xl(B);
  size_t pos=kIH; auto take=[&](std::vector<double>& a){for(auto& x:a){x=f64(b.data()+pos);pos+=8;if(!std::isfinite(x))fail("nonfinite request payload");}}; take(sv); take(fv); take(xl);
  for(size_t i=0;i<B;i++) if(xl[i]!=1.0&&xl[i]!=2.0)fail("xland must be 1 (land) or 2 (sea)");
  for(uint32_t q=0;q<kNF;q++)for(uint32_t i=0;i<B;i++)for(uint32_t k=0;k<L;k++) if(fv[(size_t(q)*B+i)*L+k]<=0)fail("rho, pii, p, delz must be positive");
  auto opt=torch::TensorOptions().dtype(torch::kFloat64).device(torch::kCPU);
  auto field=[&](const std::vector<double>& a,size_t off){return torch::from_blob(const_cast<double*>(a.data()+off),{(int64_t)B,(int64_t)L},opt).clone();};
  kdm6::State s; auto sf=s.fields(); for(size_t q=0;q<sf.size();q++)*sf[q]=field(sv,q*per);
  kdm6::Forcing f; auto ff=f.fields(); for(size_t q=0;q<ff.size();q++)*ff[q]=field(fv,q*per);
  auto xland=torch::from_blob(xl.data(),{(int64_t)B},opt).clone(); auto params=kdm6::make_parameters(0,torch::kCPU,torch::kFloat64);
  kdm6::FnResult r; {torch::NoGradGuard guard; r=kdm6::kdm6_fn(s,f,params,dt,xland,nl,ns);}
  auto check=[&](const auto& fields,const std::vector<double>& in,const char* name){for(size_t q=0;q<fields.size();q++){auto t=fields[q]->contiguous().view({-1}); if(t.numel()!=(int64_t)per||std::memcmp(t.template data_ptr<double>(),in.data()+q*per,per*8))fail(std::string("runtime mutated ")+name);}};
  check(s.fields(),sv,"state"); check(f.fields(),fv,"forcing");
  std::vector<unsigned char> out; size_t total=sn+fn+sn+size_t(kNP)*B; out.reserve(kOH+total*8); out.insert(out.end(),kOut.begin(),kOut.end()); put32(out,kVersion);put32(out,B);put32(out,L);
  for(double x:sv)put64(out,x);for(double x:fv)put64(out,x);
  for(auto t:r.state_out.fields()){auto v=t->contiguous().view({-1});if(v.numel()!=(int64_t)per)fail("wrong output state shape");for(int64_t i=0;i<v.numel();i++){double x=v.data_ptr<double>()[i];if(!std::isfinite(x))fail("nonfinite output state");put64(out,x);}}
  std::array<torch::Tensor,3> precip{{r.rain_increment,r.snow_increment,r.graupel_increment}};
  for(auto& t:precip){auto v=t.contiguous().view({-1});if(v.numel()!=B)fail("wrong precipitation shape");for(int64_t i=0;i<v.numel();i++){double x=v.data_ptr<double>()[i];if(!std::isfinite(x))fail("nonfinite precipitation");put64(out,x);}}
  publish(op,out);
}
}
int main(int argc,char**argv){try{if(argc!=5||std::string(argv[1])!="--input"||std::string(argv[3])!="--output"){std::cerr<<"usage: ice_factorial_batch --input REQUEST --output RESULT\n";return 2;}run(argv[2],argv[4]);return 0;}catch(const std::exception&e){std::cerr<<"ice_factorial_batch: "<<e.what()<<'\n';return 1;}catch(...){std::cerr<<"ice_factorial_batch: unknown failure\n";return 1;}}
