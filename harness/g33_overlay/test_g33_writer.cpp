// Compatibility check: the C++ overlay Writer must produce a container the Python
// g33_dump.read_container() accepts (same bytes, same SHA-256). Build:
//   clang++ -std=c++17 -DKDM6_G33_OP_DUMP test_g33_writer.cpp -o /tmp/g33w && /tmp/g33w <out>
#include "g33_op_dump.h"
#include <string>
using namespace kdm6::g33;

int main(int argc, char** argv) {
    std::string out = argc > 1 ? argv[1] : "/tmp/cpp_c.g33";
    std::string header =
        "{\"producer_commit\":\"cppcommit\",\"binary_sha256\":\"" + std::string(64,'0') +
        "\",\"resolved_binary_path\":\"/tmp/g33w\",\"resolved_binary_sha256\":\"" + std::string(64,'0') +
        "\",\"case_id\":\"closure3-C3.3\",\"pair_id\":\"conservative\",\"backend\":\"cpp\","
        "\"algorithm\":\"conservative\",\"B\":3,\"K\":4,\"column_layout_id\":\"lc05-3col\","
        "\"column_index_map\":[[0,0,0,0],[1,0,1,1],[2,0,2,2]],\"canonical_k_order\":\"top-first\","
        "\"run_uuid\":\"uuid-c\",\"process_id\":1,\"owner_thread_id\":\"1\","
        "\"descriptor_sha256\":\"" + std::string(64,'a') + "\",\"container_id\":\"L1_main_n1\",\"global_op_seq_start\":0,"
        "\"global_op_seq_end\":99,\"record_count_expected\":3}";
    Writer w(out, header);

    std::vector<uint8_t> p0; be_f32(p0, 1.0f); be_f32(p0, 2.5f); be_f32(p0, -3.25f);
    w.record("{\"seq_no\":0,\"op_seq_id\":0,\"outer_loop\":1,\"chain\":\"main\",\"n\":1,\"cell_role\":\"TOP\",\"k\":0,"
             "\"species\":\"qr\",\"op_id\":\"QR_FALK\",\"stage\":\"op\",\"field\":\"falk_f32\","
             "\"dtype\":\"f32\",\"shape\":[3],\"payload_size\":12}", p0);

    std::vector<uint8_t> p1; be_f64(p1, 3.14159265358979); be_f64(p1, 1e-30);
    w.record("{\"seq_no\":1,\"op_seq_id\":1,\"outer_loop\":1,\"chain\":\"main\",\"n\":1,\"cell_role\":\"TOP\",\"k\":0,"
             "\"species\":\"qr\",\"op_id\":\"QR_FALK\",\"stage\":\"op\",\"field\":\"falk_precast\","
             "\"dtype\":\"f64\",\"shape\":[2],\"payload_size\":16}", p1);

    std::vector<uint8_t> p2; be_i32(p2, 2); be_u8(p2, 1);
    w.record("{\"seq_no\":2,\"op_seq_id\":2,\"outer_loop\":1,\"chain\":\"main\",\"n\":1,\"cell_role\":\"TOP\",\"k\":0,"
             "\"species\":\"qr\",\"op_id\":\"QR_OUTFLOW\",\"stage\":\"op\",\"field\":\"mix\","
             "\"dtype\":\"i32\",\"shape\":[1],\"payload_size\":4}", std::vector<uint8_t>(p2.begin(), p2.begin()+4));

    w.finalize();
    return 0;
}
