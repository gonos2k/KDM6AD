// ── G3.3-M container trace, shared by every instrumented TU (OVERLAY ONLY) ───
// Torch-DEPENDENT: this header adapts tensors to the torch-free container
// writer in g33_op_dump.h. It exists because whole-K instrumentation spans
// three translation units (runtime.cpp: outer loop; coordinator.cpp: surface;
// sedimentation.cpp: substeps), and three private copies of the trace class
// would drift — the recurring failure mode this harness keeps re-learning.
//
// Each instrumented TU still supplies its OWN dladdr anchor (a symbol with
// internal linkage in that TU): an inline from this header could legitimately
// resolve to another image's copy of itself, which would defeat the
// loaded-binary binding (P0-5).
#pragma once
#ifdef KDM6_G33_OP_DUMP

#include "g33_op_dump.h"
#include <torch/torch.h>
#include <cstdlib>
#include <memory>
#include <fstream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include <unistd.h>

namespace kdm6 { namespace g33 { namespace trace {

// Minimal JSON string escaping. The header/key JSON is built by concatenation,
// so ANY unescaped value (env-supplied case_id/pair_id, or a field name) could
// close the string and inject a DUPLICATE key — and json.loads keeps the LAST
// occurrence, so an injected "producer_commit" would silently override the
// attested one. Escape everything, and reject control characters outright.
inline std::string jesc(const std::string& in) {
    std::string o;
    for (unsigned char c : in) {
        if (c == '"' || c == '\\') { o += '\\'; o += char(c); }
        else if (c < 0x20 || c == 0x7f)
            throw std::runtime_error("g33: control character in a JSON string value");
        else o += char(c);
    }
    return o;
}

inline std::string env_or_empty(const char* k) {
    const char* v = std::getenv(k);
    return v ? v : "";
}

inline bool safe_id(const char* v) {
    if (!v || !*v) return false;
    bool nondot = false;
    for (const char* p = v; *p; ++p) {
        const char c = *p;
        if (!(('A' <= c && c <= 'Z') || ('a' <= c && c <= 'z') ||
              ('0' <= c && c <= '9') || c == '_' || c == '.' || c == '-'))
            return false;
        if (c != '.') nondot = true;
    }
    return nondot;                       // "." / ".." are path segments
}

// KDM6_G33_OP_SEQ_MAP := "cid:first:last,..." and KDM6_G33_SCHEMA_SHA256 :=
// "cid:sha,..." emitted from run_index(). Flat on purpose — a JSON parser here
// would be more code to audit inside instrumentation that must stay trivially
// reviewable.
inline bool lookup_csv(const char* env, const std::string& cid, std::string& out) {
    const char* m = std::getenv(env);
    if (!m) return false;
    std::string s(m), tok;
    std::istringstream in(s);
    while (std::getline(in, tok, ',')) {
        auto a = tok.find(':');
        if (a == std::string::npos) continue;
        if (tok.substr(0, a) != cid) continue;
        out = tok.substr(a + 1);
        return true;
    }
    return false;
}

inline bool all_digits(const std::string& t) {
    if (t.empty()) return false;
    for (char c : t) if (c < '0' || c > '9') return false;
    return true;
}

// uint64_t to match g_op_seq — `long` is 32-bit on LLP64/32-bit targets, which
// would truncate a large window silently. And DIGITS ONLY before conversion:
// std::stoull accepts "-5" and wraps it to a huge unsigned value instead of
// rejecting it, so a corrupted map entry would parse "successfully" into a
// nonsense window rather than failing here.
inline bool lookup_op_seq(const std::string& cid, uint64_t& first, uint64_t& last) {
    std::string v;
    if (!lookup_csv("KDM6_G33_OP_SEQ_MAP", cid, v)) return false;
    auto b = v.find(':');
    if (b == std::string::npos) return false;
    const std::string a = v.substr(0, b), z = v.substr(b + 1);
    if (!all_digits(a) || !all_digits(z)) return false;
    first = std::stoull(a);
    last  = std::stoull(z);
    return true;
}

// One sealed container: opened at stage entry, EXPLICITLY finalized before the
// enclosing scope returns (COMPLETE footer only via finalize(), never atexit —
// §7e). `outer_tail == nullptr` names a per-substep container
// L{loop}_{chain}_n{n}; otherwise the container is L{loop}_{outer_tail}
// (outer_pre / outer_post) and chain/n are recorded as given ("-"/0).
class ContainerTrace {
public:
    ContainerTrace(const char* chain, int n, const char* outer_tail,
                   int B, int K, const ResolvedBinary& self)
        : chain_(chain), n_(n), B_(B), K_(K) {
        // ALL-OR-NOTHING configuration. Returning quietly when any single
        // variable was missing meant a run with DUMP_DIR and CASE_ID set but
        // PAIR_ID forgotten produced NO evidence and still exited 0 — a typo in
        // one export was indistinguishable from "diagnostics off". Absent =>
        // inert (production must not require the dump); partially present =>
        // the run is misconfigured and says so at the producer.
        static const char* kRequiredEnv[] = {
            "KDM6_G33_DUMP_DIR", "KDM6_G33_CASE_ID", "KDM6_G33_PAIR_ID",
            "KDM6_G33_RUN_UUID", "KDM6_G33_PRODUCER_COMMIT",
            "KDM6_G33_BINARY_SHA256", "KDM6_G33_COLUMN_LAYOUT_ID",
            "KDM6_G33_COLUMN_MAP", "KDM6_G33_OP_SEQ_MAP",
            "KDM6_G33_SCHEMA_DIR", "KDM6_G33_SCHEMA_SHA256",
        };
        std::string missing;
        int present = 0;
        for (const char* k : kRequiredEnv) {
            const char* v = std::getenv(k);
            if (v && *v) ++present;
            else missing += std::string(missing.empty() ? "" : ", ") + k;
        }
        if (present == 0) return;                       // diagnostics off
        if (!missing.empty())
            throw std::runtime_error(
                "g33: partial configuration — missing " + missing
                + " (set every G3.3 variable or none; a half-configured run "
                  "produces no evidence while still exiting 0)");
        auto* ctx = g_context;
        if (!ctx)
            throw std::runtime_error(
                "g33: configured but no ScopedDumpContext is active — the "
                "outer-loop wiring is missing, not the configuration");
        const char* dir = std::getenv("KDM6_G33_DUMP_DIR");
        const char* cas = std::getenv("KDM6_G33_CASE_ID");
        const char* pai = std::getenv("KDM6_G33_PAIR_ID");
        // case_id/pair_id flow into the container FILE NAME verbatim. The
        // producer must refuse unsafe ids itself — the Python validator only
        // sees the header after the path has already been opened.
        // The all-or-nothing env check above guarantees cas/pai are non-null
        // HERE — but concatenating a nullptr is UB, and a guard whose memory
        // safety depends on distant ordering is one refactor away from a crash
        // instead of a diagnostic.
        for (const char* v : {cas, pai})
            if (!safe_id(v))
                throw std::runtime_error(std::string("g33: unsafe id ")
                    + (v ? v : "<null>")
                    + " (allowed: [A-Za-z0-9_.-]+, not dot-only)");
        // §7c: the column map is DECLARED by the harness, never fabricated here.
        // Inventing it (e.g. fortran_j hardcoded to 0) would make the Fortran<->C++
        // column correspondence an unverified assumption dressed as evidence.
        const char* colmap = std::getenv("KDM6_G33_COLUMN_MAP");
        if (!colmap || !*colmap)
            throw std::runtime_error(
                "g33: KDM6_G33_COLUMN_MAP is required (declared Fortran(i,j)<->C++ "
                "flat-B map, protocol 7c) — refusing to fabricate one");
        cid_ = outer_tail
             ? "L" + std::to_string(ctx->outer_loop_1based) + "_" + outer_tail
             : "L" + std::to_string(ctx->outer_loop_1based) + "_" + chain_
               + "_n" + std::to_string(n);
        std::string path = std::string(dir) + "/cpp_" + ctx->algorithm + "_" + cas
                         + "_" + cid_ + ".g33";
        // §7 P0-2: the op_seq window for THIS container is DECLARED by the harness
        // (run_index.json, fixed before the run), never inferred here. Same reason
        // as the column map: a range the producer computes for itself cannot
        // falsify the producer. Absent declaration = invalid run, not a default.
        uint64_t first = 0, last = 0;
        if (!lookup_op_seq(cid_, first, last))
            throw std::runtime_error(
                "g33: KDM6_G33_OP_SEQ_MAP has no entry for container " + cid_
                + " (declared container set and actual execution disagree)");
        // §7d/P0-5: bind the evidence to the binary the process ACTUALLY loaded.
        // BINARY_SHA256 says which file the harness hashed on disk; dladdr says
        // which artifact the dynamic linker mapped this code from. Refuse when
        // they differ — the run is executing a binary the evidence does not
        // describe, and every downstream check would inherit that silently.
        {
            const std::string sealed_bin = env_or_empty("KDM6_G33_BINARY_SHA256");
            if (self.sha256 != sealed_bin)
                throw std::runtime_error(
                    "g33: the loaded binary is not the sealed one\n  sealed:   "
                    + sealed_bin + "\n  resolved: " + self.sha256 + " ("
                    + self.path + ")");
        }
        std::ostringstream tid; tid << std::this_thread::get_id();
        // §7 runtime expected-descriptor: the record stream this container may
        // emit was sealed BEFORE the run. Static analysis of the C++ expression
        // could not establish a tensor's runtime shape or dtype — nine rounds of
        // it were bypassed — so the check moved here, where the tensor is in hand.
        const char* sdir = std::getenv("KDM6_G33_SCHEMA_DIR");
        if (!sdir || !*sdir)
            throw std::runtime_error("g33: KDM6_G33_SCHEMA_DIR is required "
                                     "(sealed expected-record stream, protocol 7)");
        std::ifstream df(std::string(sdir) + "/" + cid_ + ".desc",
                         std::ios::binary);
        if (!df)
            throw std::runtime_error("g33: no sealed descriptor for container " + cid_);
        std::string blob((std::istreambuf_iterator<char>(df)),
                         std::istreambuf_iterator<char>());
        // Hash the descriptor bytes and check them against the digest the
        // HARNESS sealed, passed in by environment. Computing a digest from the
        // file just read and reporting it proves nothing: edit the descriptor
        // and the producer hashes the edited bytes and agrees with itself. The
        // reference has to arrive by a channel the same edit does not reach.
        // Hash and parse operate on the SAME in-memory bytes from one open —
        // there is no re-open between them for a swap to exploit.
        Sha256 dsha;
        dsha.update(reinterpret_cast<const uint8_t*>(blob.data()), blob.size());
        desc_sha_ = dsha.hexdigest();
        std::string want_sha;
        if (!lookup_csv("KDM6_G33_SCHEMA_SHA256", cid_, want_sha))
            throw std::runtime_error(
                "g33: KDM6_G33_SCHEMA_SHA256 has no sealed digest for container "
                + cid_);
        if (want_sha != desc_sha_)
            throw std::runtime_error(
                "g33: descriptor for " + cid_ + " does not match the sealed digest\n"
                "  sealed: " + want_sha + "\n  actual: " + desc_sha_);
        for (size_t i = 0, j; i < blob.size(); i = j + 1) {
            j = blob.find('\n', i);
            if (j == std::string::npos) j = blob.size();
            if (j > i) want_.push_back(blob.substr(i, j - i));
        }
        if (want_.empty())
            throw std::runtime_error("g33: empty descriptor for container " + cid_
                                     + " — an empty expectation accepts an empty dump");
        std::string hdr = std::string("{\"producer_commit\":\"") + jesc(env_or_empty("KDM6_G33_PRODUCER_COMMIT"))
            + "\",\"binary_sha256\":\"" + jesc(env_or_empty("KDM6_G33_BINARY_SHA256"))
            + "\",\"resolved_binary_path\":\"" + jesc(self.path)
            + "\",\"resolved_binary_sha256\":\"" + self.sha256
            + "\",\"case_id\":\"" + jesc(cas) + "\",\"pair_id\":\"" + jesc(pai)
            + "\",\"backend\":\"cpp\",\"algorithm\":\"" + jesc(ctx->algorithm)
            + "\",\"B\":" + std::to_string(B_) + ",\"K\":" + std::to_string(K_)
            + ",\"column_layout_id\":\"" + jesc(env_or_empty("KDM6_G33_COLUMN_LAYOUT_ID"))
            + "\",\"column_index_map\":" + colmap            // declared, verbatim JSON
            + ",\"canonical_k_order\":\"top-first\",\"run_uuid\":\"" + jesc(env_or_empty("KDM6_G33_RUN_UUID"))
            + "\",\"process_id\":" + std::to_string(long(::getpid()))
            + ",\"owner_thread_id\":\"" + jesc(tid.str())
            + "\",\"descriptor_sha256\":\"" + desc_sha_
            + "\",\"container_id\":\"" + jesc(cid_)
            + "\",\"global_op_seq_start\":" + std::to_string(first)
            + ",\"global_op_seq_end\":" + std::to_string(last)
            + ",\"record_count_expected\":0}";
        // NO catch here. A configured run whose container cannot be opened —
        // stale .tmp from a killed run, an existing completed container, an
        // unwritable dir — is an INVALID diagnostic run. Swallowing that turned
        // the one guard that makes a crashed prior run un-ignorable into a silent
        // disable: every G33_REC became a no-op, no container was written, and the
        // run still exited 0 with nothing for the fail-closed reader to reject.
        w_.reset(new Writer(path, hdr));
    }
    bool on() const { return w_ != nullptr; }
    // One record at the value's ACTUAL native width and ACTUAL shape.
    //
    // The dtype is DERIVED from t.scalar_type() — never passed in and never
    // converted: an earlier draft took a dtype string and did .to(kFloat64),
    // relabelling an f32-native rung as "f64" (a precision-PROVENANCE lie).
    // `k` is the CANONICAL level index and is part of the record identity;
    // without it every interior level collides and a dump could emit one cell
    // twice, skip another, and still look complete.
    void rec(const char* stage, const char* cell_role, int k, const char* species,
             const char* op_id, const char* field, const torch::Tensor& t) {
        if (!w_) return;
        auto c = t.detach().cpu().contiguous();
        const auto st = c.scalar_type();
        const char* dtype = nullptr;
        std::vector<uint8_t> pay;
        const int64_t n = c.numel();
        if (st == torch::kFloat64) {
            dtype = "f64";
            const double* p = c.data_ptr<double>();
            for (int64_t i = 0; i < n; ++i) be_f64(pay, p[i]);
        } else if (st == torch::kFloat32) {
            dtype = "f32";
            const float* p = c.data_ptr<float>();
            for (int64_t i = 0; i < n; ++i) be_f32(pay, p[i]);
        } else if (st == torch::kInt32) {
            dtype = "i32";
            const int32_t* p = c.data_ptr<int32_t>();
            for (int64_t i = 0; i < n; ++i) be_i32(pay, p[i]);
        } else if (st == torch::kUInt8 || st == torch::kBool) {
            dtype = "u8";                       // bool is exactly 0/1 — no loss
            auto b = c.to(torch::kUInt8);
            const uint8_t* p = b.data_ptr<uint8_t>();
            for (int64_t i = 0; i < n; ++i) be_u8(pay, p[i]);
        } else {
            throw std::runtime_error(std::string("g33: unsupported dtype for field ") + field);
        }
        // RUNTIME shape guard. Every record in this protocol is either a
        // whole-K field [B,K] or a per-column field [B]; nothing else has a
        // meaning the manifest can express. A static source check cannot certify
        // this — two rounds of it passed .select(-1,k), then .sum(-1)/.reshape/
        // torch::stack — so the producer refuses the shape itself, where the
        // actual tensor is in hand and no parsing is involved.
        if (!((c.dim() == 1 && c.size(0) == B_) ||
              (c.dim() == 2 && c.size(0) == B_ && c.size(1) == K_))) {
            std::string dims = "[";
            for (int64_t i = 0; i < c.dim(); ++i)
                dims += (i ? "," : "") + std::to_string(c.size(i));
            throw std::runtime_error(
                std::string("g33: field ") + field + " has shape " + dims + "]"
                + ", expected [" + std::to_string(B_) + "] or ["
                + std::to_string(B_) + "," + std::to_string(K_) + "]");
        }
        std::string shape = "[";
        for (int64_t i = 0; i < c.dim(); ++i)
            shape += (i ? "," : "") + std::to_string(c.size(i));
        shape += "]";
        const uint64_t op_seq_id = g_op_seq.fetch_add(1);
        // One string equality covers identity, dtype, rank and shape at once,
        // all read off the tensor rather than inferred from source text.
        std::string got = std::to_string(op_seq_id) + "|" + stage + "|" + cell_role
                        + "|" + std::to_string(k) + "|" + species + "|" + op_id
                        + "|" + field + "|" + dtype + "|";
        for (int64_t i = 0; i < c.dim(); ++i)
            got += (i ? "," : "") + std::to_string(c.size(i));
        if (seq_ >= int(want_.size()))
            throw std::runtime_error("g33: record beyond the sealed stream: " + got);
        if (got != want_[seq_])
            throw std::runtime_error("g33: record " + std::to_string(seq_)
                                     + " does not match the sealed descriptor\n"
                                     + "  expected: " + want_[seq_] + "\n"
                                     + "  actual:   " + got);
        std::string key = std::string("{\"seq_no\":") + std::to_string(seq_)
            + ",\"op_seq_id\":" + std::to_string(op_seq_id)
            + ",\"outer_loop\":" + std::to_string(g_context->outer_loop_1based)
            + ",\"chain\":\"" + jesc(chain_) + "\",\"n\":" + std::to_string(n_)
            + ",\"cell_role\":\"" + jesc(cell_role) + "\",\"k\":" + std::to_string(k)
            + ",\"species\":\"" + jesc(species) + "\",\"op_id\":\"" + jesc(op_id)
            + "\",\"stage\":\"" + jesc(stage) + "\",\"field\":\"" + jesc(field)
            + "\",\"dtype\":\"" + dtype
            + "\",\"shape\":" + shape + ",\"payload_size\":" + std::to_string(pay.size()) + "}";
        w_->record(key, pay);
        ++seq_;
    }
    void finalize() {
        if (!w_) return;
        // A short stream is a MISSING record. Without this, a scope that
        // returned early would publish a COMPLETE container holding a prefix.
        if (seq_ != int(want_.size()))
            throw std::runtime_error(
                "g33: container " + cid_ + " emitted " + std::to_string(seq_)
                + " of " + std::to_string(want_.size()) + " sealed records");
        w_->finalize(); w_.reset();
    }
private:
    std::unique_ptr<Writer> w_;
    std::string chain_;                 // OWNED: a const char* member could dangle
    std::string cid_;                   // container_id, echoed into the header
    std::vector<std::string> want_;     // sealed expected stream, consumed in order
    std::string desc_sha_;              // digest of the descriptor actually read
    int n_; int B_ = 0, K_ = 0, seq_ = 0;
};

}}}  // namespace kdm6::g33::trace

#endif  // KDM6_G33_OP_DUMP
