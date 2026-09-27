# S15 opt-in trace-graupel process gate

The default mp37/mp137 paths are unchanged. The opt-in Fortran patch
[`s15_trace_graupel_skip.patch`](../g33_fortran/s15_trace_graupel_skip.patch)
uses the predicate that `ProgB_param` evaluated **before** it rewrote `brs` to
record whether it produced `rhox`. It skips graupel melt, deposition,
evaporation, and enhanced melt when no density was produced. The latter three
rates are gated at their producers, before their shared limiters, so their
graupel mass, volume, vapor, rain, and heat effects all use the same zero rate.
An invalid density with a remaining nonzero rate stops rather than inventing a
density. This is a proposed **trace-process policy**, not a numerical guard
that can be enabled without a physics decision.

The patch applies with `patch -p1` from the private host root. It was generated
against canonical `phys/module_mp_kdm6.F` SHA-256
`fc0a72d33a5e61803fea56eb9118018039c6da8b5775813032b4861a2bd66eb5`.
A fresh application with zero fuzz reproduced the final run-5 source SHA-256
`13e807a4823b545dd3078d7fc865851107529d56c57a0eb29fb6807fd641850d`.
No canonical private source or operational install was edited.

| Isolated mp37 attempt | Result on the retained 40 s, one-rank/one-thread case |
| --- | --- |
| G1 melt skip plus four fail-closed density consumers | Stopped at nonzero `pgevp=-2.9107463e-12` with invalid density, `(lat,loop,i,k)=(63,1,108,9)`. G1 alone is insufficient. |
| Add `pgdep/pgevp/pgeml` producer gates | Completed at 0/20/40 s. A separate private, fixed-cell run-2 tap recorded `qg=5.8214926e-11`, `bg=0`, and all three gated rates at zero. |
| Use one finite-positive density or `1` only for proven-zero rates; remove the fixed-cell tap | Completed; all 254 common saved variables matched the prior variant raw-bit in all three frames. |
| Reuse the pre-`ProgB` validity mask at the melt opener | Completed; saved variables again matched the prior two variants raw-bit. This does not prove the predicate difference was reached in the run. |
| Preserve the original `qg>0` melt condition alongside that mask and use one declared threshold | Completed; all 254 common saved variables still matched raw-bit in all three frames. |

The private run-2 source SHA-256 is
`fceedf93083db59bbb5cf304bd1a59d408a194ddabdfc5896bddc948cbf5a95a`;
its RSL log SHA-256 is
`b0c45baf8b5dabb27b2abb08ba6b7e55a4e6a53574110e9697b1239f2661a358`.
The fixed-cell raw-word row is private supporting evidence; the final run did
not emit it. Run 5's executable SHA-256 is
`35f2998cfcc1368220f38d1aa25d6ccb94348d64f9afa70bd222155505c0f8b1`;
its 0/20/40 s forecast SHA-256 is
`ec2959361c42b6f66dad63c04aac18812b9e9a82aae7945b8dc6ad81a14064c7`.
The private build, link map, input links, logs, and histories are retained
locally. CI did not perform these native runs.

In the three saved frames, this variant had no nonfinite or negative QIB cells;
the earlier face-discovery reference had two negative QIB cells. Cloud, ice, and
rain number still had 4, 4, and 3 negative cells, respectively. There is no
same-executable capture-off control for the opt-in variant, no whole-host
nonnegativity proof, no mp137/oracle mirror or derivative check, and no owner
decision that trace mass with absent volume should remain inactive. **S15 and
the operational/default-path decision remain OPEN.**
