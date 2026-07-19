// G3.3-M op-provenance diagnostic writer + RAII context — OVERLAY-ONLY skeleton.
//
// protocol: docs/C4_G3_3_OP_PROVENANCE_PROTOCOL.md (§5, §7). This header lives in
// harness/ and is included ONLY by the temporary diagnostic source OVERLAY of
// sedimentation*.cpp (steps 7/9) — never by the canonical libtorch tree, so the
// public production source SHA is unchanged.
//
// EVERYTHING is inside #ifdef KDM6_G33_OP_DUMP: when the macro is undefined the
// preprocessor emits nothing, so a macro-off overlay build is byte-identical to
// the production build (the 3-way A==B==C non-invasiveness gate, §10).
//
// The byte layout matches harness/g33_dump.py exactly (magic, u32-LE lengths,
// utf-8 JSON header/keys, raw big-endian native-width payloads, COMPLETE footer
// with sha256 over the concatenated payloads). The writer is torch-free — the
// overlay extracts per-cell native values and passes raw pointers here.

#ifndef KDM6_G33_OP_DUMP_H_
#define KDM6_G33_OP_DUMP_H_

#ifdef KDM6_G33_OP_DUMP

#include <cstdint>
#include <cstring>
#include <cstdio>
#include <string>
#include <vector>
#include <fstream>
#include <stdexcept>

namespace kdm6 { namespace g33 {

// ── signature-neutral context (P0-3): carried in a thread_local, NEVER as a
// function argument, so no public/internal symbol or function-pointer type
// changes. Set/cleared by RAII at each outer sub-cycle boundary. ─────────────
struct DumpContext {
    int         outer_loop_1based = 0;
    const char* case_id   = "";
    const char* pair_id   = "";
    const char* algorithm = "";   // "legacy" | "conservative"
    const char* backend   = "cpp";
};
inline thread_local DumpContext* g_context = nullptr;

struct ScopedDumpContext {
    DumpContext ctx;
    DumpContext* prev = nullptr;
    ScopedDumpContext(int loop, const char* case_id, const char* pair_id,
                      const char* algorithm) {
        ctx.outer_loop_1based = loop; ctx.case_id = case_id;
        ctx.pair_id = pair_id; ctx.algorithm = algorithm;
        prev = g_context; g_context = &ctx;
    }
    ~ScopedDumpContext() { g_context = prev; }
    ScopedDumpContext(const ScopedDumpContext&) = delete;
    ScopedDumpContext& operator=(const ScopedDumpContext&) = delete;
};

// ── compact SHA-256 (matches Python hashlib.sha256 over the raw payload bytes) ─
class Sha256 {
public:
    Sha256() { reset(); }
    void reset() {
        len_ = 0; buflen_ = 0;
        static const uint32_t iv[8] = {0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                                       0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
        std::memcpy(h_, iv, sizeof h_);
    }
    void update(const uint8_t* p, size_t n) {
        len_ += n;
        while (n) {
            size_t take = 64 - buflen_; if (take > n) take = n;
            std::memcpy(buf_ + buflen_, p, take);
            buflen_ += take; p += take; n -= take;
            if (buflen_ == 64) { block(buf_); buflen_ = 0; }
        }
    }
    std::string hexdigest() {
        uint64_t bits = len_ * 8;
        uint8_t pad = 0x80; update(&pad, 1);
        uint8_t z = 0; while (buflen_ != 56) update(&z, 1);
        uint8_t be[8]; for (int i = 0; i < 8; ++i) be[i] = uint8_t(bits >> (56 - 8*i));
        update(be, 8);
        char out[65];
        for (int i = 0; i < 8; ++i) std::snprintf(out + i*8, 9, "%08x", h_[i]);
        return std::string(out, 64);
    }
private:
    static uint32_t ror(uint32_t x, int n) { return (x >> n) | (x << (32 - n)); }
    void block(const uint8_t* q) {
        static const uint32_t k[64] = {
            0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
            0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
            0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
            0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
            0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
            0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
            0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
            0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2};
        uint32_t w[64];
        for (int i = 0; i < 16; ++i)
            w[i] = (uint32_t(q[i*4])<<24)|(uint32_t(q[i*4+1])<<16)|(uint32_t(q[i*4+2])<<8)|q[i*4+3];
        for (int i = 16; i < 64; ++i) {
            uint32_t s0 = ror(w[i-15],7)^ror(w[i-15],18)^(w[i-15]>>3);
            uint32_t s1 = ror(w[i-2],17)^ror(w[i-2],19)^(w[i-2]>>10);
            w[i] = w[i-16] + s0 + w[i-7] + s1;
        }
        uint32_t a=h_[0],b=h_[1],c=h_[2],d=h_[3],e=h_[4],f=h_[5],g=h_[6],hh=h_[7];
        for (int i = 0; i < 64; ++i) {
            uint32_t S1 = ror(e,6)^ror(e,11)^ror(e,25);
            uint32_t ch = (e&f)^(~e&g);
            uint32_t t1 = hh + S1 + ch + k[i] + w[i];
            uint32_t S0 = ror(a,2)^ror(a,13)^ror(a,22);
            uint32_t maj = (a&b)^(a&c)^(b&c);
            uint32_t t2 = S0 + maj;
            hh=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
        }
        h_[0]+=a; h_[1]+=b; h_[2]+=c; h_[3]+=d; h_[4]+=e; h_[5]+=f; h_[6]+=g; h_[7]+=hh;
    }
    uint32_t h_[8]; uint8_t buf_[64]; size_t buflen_; uint64_t len_;
};

// ── native-width big-endian payload packing (matches g33_dump.pack_payload) ──
inline void be_f32(std::vector<uint8_t>& out, float v) {
    uint32_t u; std::memcpy(&u, &v, 4);
    for (int i = 3; i >= 0; --i) out.push_back(uint8_t(u >> (8*i)));
}
inline void be_f64(std::vector<uint8_t>& out, double v) {
    uint64_t u; std::memcpy(&u, &v, 8);
    for (int i = 7; i >= 0; --i) out.push_back(uint8_t(u >> (8*i)));
}
inline void be_i32(std::vector<uint8_t>& out, int32_t v) {
    uint32_t u = uint32_t(v);
    for (int i = 3; i >= 0; --i) out.push_back(uint8_t(u >> (8*i)));
}
inline void be_u8(std::vector<uint8_t>& out, uint8_t v) { out.push_back(v); }

// ── fail-closed container writer (matches the Python reader) ─────────────────
class Writer {
public:
    Writer(const std::string& path, const std::string& header_json)
        : path_(path), tmp_(path + ".tmp") {
        if (std::ifstream(path_).good())
            throw std::runtime_error("g33: refuse to overwrite " + path_);
        if (std::ifstream(tmp_).good())
            throw std::runtime_error("g33: stale .tmp " + tmp_);
        f_.open(tmp_, std::ios::binary);
        if (!f_) throw std::runtime_error("g33: cannot open " + tmp_);
        f_.write("KDG33OP\n", 8);
        put_u32(1);                       // format_version
        put_u32(uint32_t(header_json.size())); f_.write(header_json.data(), header_json.size());
    }
    // key_json must contain seq_no,outer_loop,chain,n,cell_role,species,op_id,
    // stage,field,dtype,shape,payload_size (the overlay builds it; helper below).
    void record(const std::string& key_json, const std::vector<uint8_t>& payload) {
        f_.write("REC1", 4);
        put_u32(uint32_t(key_json.size())); f_.write(key_json.data(), key_json.size());
        put_u32(uint32_t(payload.size()));  f_.write(reinterpret_cast<const char*>(payload.data()), payload.size());
        sha_.update(payload.data(), payload.size());
        ++n_;
    }
    void finalize() {                     // explicit ONLY — never atexit/destructor
        std::string footer = "{\"complete\":true,\"payload_sha256\":\"" + sha_.hexdigest()
                           + "\",\"record_count_actual\":" + std::to_string(n_) + "}";
        f_.write("FOOT", 4);
        put_u32(uint32_t(footer.size())); f_.write(footer.data(), footer.size());
        f_.flush(); f_.close();
        std::remove(path_.c_str());
        if (std::rename(tmp_.c_str(), path_.c_str()) != 0)
            throw std::runtime_error("g33: atomic rename failed for " + path_);
        finalized_ = true;
    }
    ~Writer() { if (!finalized_ && f_.is_open()) f_.close(); }  // no footer on abort
private:
    void put_u32(uint32_t v) {
        uint8_t b[4] = {uint8_t(v), uint8_t(v>>8), uint8_t(v>>16), uint8_t(v>>24)};  // LE
        f_.write(reinterpret_cast<const char*>(b), 4);
    }
    std::string path_, tmp_; std::ofstream f_; Sha256 sha_; uint32_t n_ = 0; bool finalized_ = false;
};

}}  // namespace kdm6::g33

#endif  // KDM6_G33_OP_DUMP
#endif  // KDM6_G33_OP_DUMP_H_
