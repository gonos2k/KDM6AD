// Exercise the sealed-digest comparison exactly as the overlay does.
#include "g33_op_dump.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <sstream>
static bool lookup_csv(const char* env, const std::string& cid, std::string& out) {
    const char* m = std::getenv(env);
    if (!m) return false;
    std::string s(m), tok; std::istringstream in(s);
    while (std::getline(in, tok, ',')) {
        auto a = tok.find(':');
        if (a == std::string::npos) continue;
        if (tok.substr(0, a) != cid) continue;
        out = tok.substr(a + 1); return true;
    }
    return false;
}
int main(int argc, char** argv) {
    std::string cid = argv[2];
    std::ifstream f(argv[1], std::ios::binary);
    std::string blob((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    kdm6::g33::Sha256 s; s.update((const uint8_t*)blob.data(), blob.size());
    std::string actual = s.hexdigest(), want;
    if (!lookup_csv("KDM6_G33_SCHEMA_SHA256", cid, want)) { std::cout << "NO SEALED DIGEST\n"; return 2; }
    if (want != actual) { std::cout << "REJECTED (sealed != actual)\n"; return 1; }
    std::cout << "accepted\n"; return 0;
}
