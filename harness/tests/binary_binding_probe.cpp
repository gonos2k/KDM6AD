// Does resolve_containing_binary() report the artifact this code is actually
// running from, with a digest Python agrees with? Run bare it prints the
// resolved path and digest; given a sealed digest argument it mirrors the
// overlay's refusal path exactly (compare, reject on mismatch).
#include "g33_op_dump.h"
#include <cstdio>

static void anchor() {}

int main(int argc, char** argv) {
    auto rb = kdm6::g33::resolve_containing_binary(
        reinterpret_cast<const void*>(&anchor));
    std::printf("%s\n%s\n", rb.path.c_str(), rb.sha256.c_str());
    if (argc > 1 && rb.sha256 != argv[1]) {
        std::fprintf(stderr, "REJECTED (loaded binary is not the sealed one)\n");
        return 1;
    }
    return 0;
}
