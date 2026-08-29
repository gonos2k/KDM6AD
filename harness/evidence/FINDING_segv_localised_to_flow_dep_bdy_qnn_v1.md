# Two CCN defects, one crash and one divergence: both sites located, fixed, and separated

Four decompositions in this campaign crash with `SIGSEGV` -- `1x3`, `1x4`,
`2x3`, `3x2` -- and the crash was carried as an open decomposition puzzle with a
debug rebuild of WRF as the proposed next step. The rebuild was not needed.

The fault is `share/module_bc.F`'s `flow_dep_bdy_qnn`. Fixing it removes the
crash and does **not** touch the `QNCCN` decomposition divergence, which comes
from a second site, `phys/module_mp_kdm6.F`, whose correction was already
carried by kernel revision `9354141b` and absent from the deployed `a06c954b`.
Both are now in the deployed tree, and the two effects separate cleanly.

## The recorded backtraces contain no localising information

The `rsl.error.*` files carry three frames:

    Could not print backtrace: executable file is not an executable
    #0  0x131a2a103
    #1  0x131a29083
    #2  0x1847ed743

Every crashing rank on record agrees on the ASLR-invariant low 14 bits of frames
#0 and #1 (`0x2103`, `0x1083`) across two microphysics schemes and two grids,
which reads like one shared code site. **It is not.** A minimal Fortran program
with a deliberate null-pointer store, unrelated to WRF, produces the same three
offsets and then a fourth frame:

    #0  0x10499e103   (&0x3FFF = 0x2103)
    #1  0x10499d083   (&0x3FFF = 0x1083)
    #2  0x181fb5743   (&0x3FFF = 0x1743)
    #3  0x1046a8767   <- the actual fault, which WRF never printed

Frames #0-#2 are libgfortran's signal handler and `_sigtramp`, and they are
program-independent. WRF's backtrace stops one frame short of the only frame
that carries information. Without the control program the matching offsets would
have been reported here as evidence that the crashes share a code site.

## What localises it instead, with no rebuild

macOS writes a fully symbolicated crash report, with each image's load address,
for these faults. None survived from the campaign: `.ips` retention on this host
is about one day, while the `.diag` files beside them go back further, which is
what makes the directory look populated. The reports were never suppressed --
the window was missed.

Re-running reopens it, on the campaign binary itself
(`a40bd80fae334c4b01af42bc8d7057aeb03b156d1672c94682ad15bb07175f20`, matching
the `wrf_exe_sha256` recorded in the crashing run directories), 17 s per grid:

| grid | np | rc | crash reports | faulting frame #0 |
|---|---|---|---|---|
| `1x3` | 3 | 139 | 1 | `__module_bc_MOD_flow_dep_bdy_qnn` |
| `1x4` | 4 | 139 | 2 | `__module_bc_MOD_flow_dep_bdy_qnn` |
| `2x3` | 6 | 139 | 2 | `__module_bc_MOD_flow_dep_bdy_qnn` |
| `3x2` | 6 | 139 | 3 | `__module_bc_MOD_flow_dep_bdy_qnn` |

Eight reports, one per faulting rank; `3x2` reproduced its original crash set
(ranks 3, 4, 5) on the same patches. The stack is identical in all eight:

    #0  wrf.exe +0x137590c  __module_bc_MOD_flow_dep_bdy_qnn
    #1  wrf.exe +0x28b5d3c  solve_em_
    #2  wrf.exe +0x1392ab8  solve_interface_
    #3  wrf.exe +0x7de78    __module_integrate_MOD_integrate
    #4  wrf.exe +0x14d8     __module_wrf_top_MOD_wrf_run
    #5  wrf.exe +0x2b91a1c  main

    EXC_BAD_ACCESS, KERN_INVALID_ADDRESS -- e.g. 0xcb8e31b4c, 0x634e5ba58, 0xd5ca38074

## Site 1: `flow_dep_bdy_qnn`, three defects

In all four boundary blocks -- Y-start, Y-end, X-start, X-end:

    REAL, DIMENSION( ims:ime , kms:kme , jms:jme ) :: dz8w     ! (i,k,j) -- correct
    REAL, DIMENSION( ims:ime , kms:kme )           :: xland    ! WRONG second extent
    ...
    z_sum = 0.
    DO k = kts, ktf
      DO i = ...
        IF (v < 0.) THEN ... ELSE
          z_sum = z_sum + dz8w(i,j,k)                          ! WRONG index order
          if(xland(i,j)==1) then                               ! index is right

1. `dz8w` is declared correctly and **indexed wrongly**.
2. `xland` is indexed correctly and **declared wrongly**.
3. `z_sum` is reset once per `j` and accumulated across the whole `k`-then-`i`
   nest, and only on the `ELSE` branch -- a branch-gated running sum over a
   slab, not the per-column height integral the formula wants.

The true shapes are not in doubt: `inc/i1_decl.inc` gives `dz8w` as
`(sm31:em31, sm32:em32, sm33:em33)` = `(i,k,j)`, and
`phys/module_microphysics_driver.F:603` declares `XLAND` as
`DIMENSION( ims:ime , jms:jme )`. `bottom_top_stag = 40` in the model's own
output gives `kds:kde = 1:40`, and WRF neither decomposes nor halos the vertical,
so `kms:kme` spans 40 while `j` runs to 283.

### Why some ranks fault and others do not

Not allocator luck; the sign of the index arithmetic decides it. The offset
actually computed for `dz8w` is

    (i - ims) + (j - kms)*NI + (k - jms)*NI*NK          NI = ime-ims+1, NK = 40

`(k - jms)` carries the whole slab stride. A rank whose patch starts at the
south domain edge has `jms = -4`, so `(k - jms) = k + 4 > 0` and the address
stays inside the array. Any other rank here has `jms >= 65`, so
`(k - jms) <= -26` and the read lands **before the array base**. Evaluated over
the loop bounds of every block each rank actually enters, for all 31 ranks on
record:

|  | ranks | SEGV |
|---|---|---|
| offset stays inside the array | 16 | **0** |
| offset lands outside the array | 15 | **8** |

Every inside-rank has `jps = 1`; every outside-rank has `jps` in
{72, 95, 142, 189, 213}. So `jps > 1` is **necessary and not sufficient**:
reading before the array base is deterministic, whether that address is mapped
is not. This is why `3x1` and `4x1` are immune -- every one of their ranks has
`jps = 1` -- and why `2x2` and `3x2`, with identical `j` patches, differ: their
`NI` differs. It also supplies the mechanism `FINDING_middle_rank_hypothesis_refuted_v1`
left open: the `j` band is not the variable, the `j` memory origin is.

## Site 2: the kernel's CCN block

`FINDING_qnccn_first_write_v1` identified this one and recorded that the fix
already existed upstream. Deployed `a06c954b`, line 311:

    do j = jms,jme          !  MEMORY bounds -- sweeps the unexchanged halo
      do i = ims,ime
        do k = kms,kme

Reference `9354141b`, line 318: `do j = jts,jte` / `do i = its,ite` /
`do k = kts,kte`. The CCN profile formula is the same at both sites; the
boundary routine holds a copy of it whose indices were corrupted in the copying.

## The fixes, and what each one does

Owner instruction, 2026-08-29: "QNCCN 버그이면 수정 필요", then "커널도
9354141b로 수정". Both files were taken from the repository tree, which already
carried the corrections, and WRF was rebuilt. `./compile` returns 0 whether or
not it linked, so the gate was the binary.

| binary | kernel | `module_bc` | crash | j-decomp, 20 s | i-seam, 1 min |
|---|---|---|---|---|---|
| `a40bd80f` (campaign) | `a06c954b` | defective | **SEGV on 4 grids** | 1 field, `QNCCN` | 77 of 197 |
| `4c899067` | `a06c954b` | fixed | none | 1 field, `QNCCN` | 77 |
| `f54ef3c9` | `9354141b` | fixed | none | **0 fields** | 77 |

The two defects are separable and each does one thing.

**`module_bc.F` removes the crash and nothing else.** On `4c899067` all four
grids complete (`2x3` and `3x2` at 6 of 6 ranks `SUCCESS COMPLETE`, `1x3` and
`1x4` at `rc = 0`), and `np = 1` against `1x2`/`1x3`/`1x4` still differs in
exactly one field, `QNCCN` -- the same field and count
`FINDING_real_mpi_decomposition_v1` recorded before any fix.

**The kernel closes the divergence.** On `f54ef3c9`, `np = 1` against
`1x2`, `1x3` and `1x4` differs in **no field**, and the zero is not a degenerate
comparison: **197 of 197** f32 3-D fields are byte-equal, with real variance
(`QNCCN` std 1.261e9, `T` std 51.26 K, `REFL_10CM` std 8.98). At one minute
`1x4` is likewise 0 of 197. The binary is deterministic -- `np = 1` and `1x4`
each repeat bit-identically, and the invariance reproduces on an independent
pair.

**Neither touches the i-seam.** `2x2` and `4x1` sit at 77 of 197 on `f54ef3c9`,
the same count the campaign binary gives, confirming exactly what
`FINDING_second_decomposition_defect_v1` predicted -- "the tile-bounds fix
leaves `np = 4` at 77 differing fields" -- and leaving that `delz` i-seam
difference, sized at relative median 6.9e-07 by
`FINDING_np4_seam_is_rounding_v1`, as the remaining decomposition dependence.

### Both fixes move `np = 1`

Each comparison below is between two binaries differing in exactly one file, so
the attribution is clean. One minute, `np = 1`:

| change | fields differing | `T` cells | `T` cond p99 |
|---|---|---|---|
| `module_bc.F` (`a40bd80f` -> `4c899067`) | 54 of 197 | 0.06% | 5.798e-04 K |
| kernel (`4c899067` -> `f54ef3c9`) | 75 of 197 | 4.62% | 1.404e-03 K |

The kernel move is the larger one because revision `9354141b` carries two
mp37<->mp137 parity reconciliations beyond the CCN loop -- a `rho_min = 100`
clamp straddle and `cmg1d` taken from the reconciled `diag_rhog` rather than raw
`rhox` (`REFL_10CM` 3.56% of cells, cond p99 1.639e-01). Its forensic
`#ifdef KDM6_SUBSTEP_DUMP` blocks compile in, `-DKDM6_SUBSTEP_DUMP` being in
`ARCH_LOCAL`, but stay dormant unless the `KDM6_SUBSTEP_DUMP` environment
variable names a dump directory.

**Any baseline pinned to the old binaries shifts, at every rank count.**

## A build-provenance hazard found on the way

The first rebuild produced a binary that could not be reproduced from the tree.
Rebuilding with the pre-fix `module_bc.F` gave `34fa1cef...`, not the campaign's
`a40bd80f...`. Forcing a recompile of `phys/module_mp_kdm6.F` changed its object
from `8937446f...` to `2ce70e62...` **from the same source file**, and changed
the preprocessed `.f90` too.

The `.F`, `.f90` and `.o` shared an mtime to the second, which is a `cp -p`
restore rather than a compile: an excursion between 2026-08-23 and 08-25
restored the source and left the derived files from a different build. Any
rebuild silently linked them, and the first fix binary did.

The campaign binary itself is clean: with the objects recompiled, pre-fix
`module_bc.F` reproduces `a40bd80f` **exactly**, which also establishes that the
toolchain is bit-deterministic and therefore that the stale object really was
foreign. Every measurement in this finding was re-taken after that recompile.

## What this does and does not establish

It establishes the fault site from eight symbolicated reports on the campaign
binary; the mechanism, down to which ranks can fault and why; that
`module_bc.F` accounts for the crash and the kernel for the divergence; and that
neither accounts for the i-seam.

It does **not** establish that `QNCCN` decomposition invariance survives longer
integrations -- it is measured at 20 s and, for `1x4`, at one minute. Nor does it
reach the graupel melt arms, which rest on the Fortran overlay fixtures rather
than MPI runs; `FINDING_arm_l_mpi_null_v1` was built from `a06c954b` and carried
both defects, so its null remains a null about `ncmin` only.

`QNCCN` comes back clean: 0 negative and 0 non-finite cells. `QNCLOUD` still
carries a handful of negative cells at 1e-9 to 1e-8; whether that is the same
thing as the separately noted -1.01e-02 over 200 cells is not established here.

## Reproduction

The crash needs the campaign binary, preserved as
`main/wrf.exe.a40bd80f.20260829_070639`; the pre-fix sources are kept beside
theirs as `share/module_bc.F.pre-qnnfix.*` and `phys/module_mp_kdm6.F.a06c954b.*`.

    cd /Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS
    python3 ./run_ss_case.py --mp 37 --minutes 0 --seconds 20 --history 0 \
            --np 6 --proc-grid 3x2 --label segvloc

Then, within about a day:

    ls -t ~/Library/Logs/DiagnosticReports/wrf.exe-*.ips

Each is JSON after a one-line header; `usedImages[].base` plus
`threads[].frames[].imageOffset` and `.symbol` give the symbolicated stack.
