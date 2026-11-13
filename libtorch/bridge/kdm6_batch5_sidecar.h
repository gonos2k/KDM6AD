#pragma once
/* Private test-only POD copy-out interface, present only in research builds.
 * No pointer into sidecar storage or stable public ABI is exposed. */
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
enum { KDM6_BATCH5_META_VERSION = 1 };
/* Caller initializes both fields before metadata copy-out; exact v1 size required. */
struct kdm6_batch5_meta {
    uint32_t abi_version, struct_size;
    char input_id[128], mode[32], family[32], scope[16], stage[64], field[64];
    /* v1 exposes forward value/mask only; derivative identities are always "none". */
    char record_kind[16], derivative_mode[16], direction_id[128], seed_sha256[65], cotangent_id[128];
    uint64_t runtime_call, one_step_call, outer_loop, substep_n, event_ordinal;
    int64_t b_zero, k_zero, native_level_bottom_first, B, K;
};
int kdm6_batch5_begin_c(const char*,const char*,uint64_t);
uint64_t kdm6_batch5_count_c(void);
int kdm6_batch5_metadata_c(uint64_t,struct kdm6_batch5_meta*,size_t);
/* mode capture_on_value only: kind=1 f32, 2 f64, 3 bool; raw bits low-aligned. */
int kdm6_batch5_value_word_c(uint64_t,uint64_t*,int*);
void kdm6_batch5_clear_c(void);
#ifdef __cplusplus
}
#endif
