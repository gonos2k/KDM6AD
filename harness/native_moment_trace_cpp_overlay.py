"""Prepare diagnostic insertions in an isolated copy of the value-only C API.

The operational C API, packed AD entry and physical expressions are unchanged.
"""
from __future__ import annotations


def overlay_cpp_source(source: str) -> str:
    marker = '#include "native_moment_trace_v2.hpp"'
    if marker in source:
        raise ValueError("moment trace overlay is already present")
    begin = source.index('extern "C" int kdm6_native_fp64_value_c(')
    end = source.index("\n#endif", begin)
    body = source[begin:end]

    input_anchor = "        auto params = kdm6::make_parameters(param_grad_flags);"
    output_anchor = "        // Value-only output admission before any REAL4 buffer is written."
    for anchor in (input_anchor, output_anchor):
        if body.count(anchor) != 1:
            raise ValueError("native value-only trace anchor is missing or ambiguous")

    def capture(stage: str, state: str) -> str:
        return f'''        if (kdm6_moment_trace_v2::enabled()) {{
            // This entry is explicitly value-only; no extracted value re-enters physics.
            torch::NoGradGuard moment_trace_value_only;
            const auto trace_qc = {state}.qc.contiguous();
            const auto trace_nc = {state}.nc.contiguous();
            kdm6_moment_trace_v2::record("{stage}", trace_qc.data_ptr<double>(),
                trace_nc.data_ptr<double>(), im, kme, jme, dt, ncmin_land, ncmin_sea);
        }}

'''

    body = body.replace(input_anchor, capture("FP64_INPUT", "state_in") + input_anchor)
    body = body.replace(output_anchor, capture("FP64_OUTPUT", "result.state_out") + output_anchor)
    result = source[:begin] + body + source[end:]
    anchor = "#include <limits>\n"
    if result.count(anchor) != 1:
        raise ValueError("C API include anchor is missing or ambiguous")
    return result.replace(anchor, anchor + marker + "\n")
