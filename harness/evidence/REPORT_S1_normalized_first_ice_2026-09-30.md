# S1 first-ice velocity units: separate normalized experiment

The retained S1 mp337 dry-number trace used conservative interface transfers,
but its first ice substep consumed raw `vt_i`/`vtn_i`. Its `mstep_i` was selected
from `vt_i/delz` and `vtn_i/delz`; only ice substeps after the first divided
the recomputed velocity by layer thickness. In the recorded step-2 upper
layer, `falk_ni=25944.287109375` and `ni=436204.8125`, so the 20 s offer
exceeded the reservoir while the selected `mstep_i` was 1. That old capture
remains evidence for the raw-handoff variant, not a normalized ice run.

Physics selector 2 now uses the existing conservative departure/arrival
functions and passes `v/delz` at the first ice handoff. Thus the consumed
coefficient has the same units as the coefficient used to select `mstep_i`
and as later ice-substep coefficients. Selectors 0 (legacy) and 1 (historical
conservative) retain their raw handoff; no default or host scheme changes.
The Python experiment exposes the same choice through
`normalize_ice_handoff=True`. The C/Fortran enum adds value 2 without changing
the ABI struct layout or old selector meanings.

Focused source-boundary tests check nonuniform `delz`, the first top-layer
outflow, selector acceptance, and a finite fp64 JVP/VJP duality identity.
The existing selector-1 full-step Python/C++ fixture remains unchanged; a
selector-2 mixed-ice single-subcycle fixture compares the two implementations.

This is an **opt-in algorithm candidate**, not S1 closure. The selected
three-subcycle mixed-phase fixture is branch-sensitive: tiny first-subcycle
Python/C++ differences change `prevp`/`psdep` on the next subcycle, so broad
selector-2 cross-tree agreement is not established. No variant-2 native host
run, multiple ice substeps, nonzero bottom ice-number export, physical QN
basis, or observation acceptance is claimed here.
