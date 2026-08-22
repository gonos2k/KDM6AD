# The MPI findings were produced by a different kernel revision than everything else

Found while trying to build the Arm L diagnostic binary the review asked for.
There are TWO WRF trees on this host, and the evidence and the runs use
different ones.

| tree | `module_mp_kdm6.F` | `wrf.exe` | what uses it |
|---|---|---|---|
| `KDM6AD-k/host/KIM-meso_v1.0` | `9354141b...` | 17 Jul | every fixture, factorial, Arm N/N_d/L result |
| `KDM6AD+/KIM-meso_v1.0` | **`a06c954b...`** | 24 Jun | **every MPI run in this campaign** |

`ss_real_case_.../SS/wrf.exe` is a symlink into the SECOND tree. So
`FINDING_real_mpi_decomposition_v1`, `FINDING_mpi_trajectory_growth_v1` and
`FINDING_mpi_repeatability_v1` were all produced by a binary built from a kernel
revision that no fixture work has ever touched -- and none of them says so.

This also corrects something in the previous cycle's notes: what was called "the
operational binary" and treated as too important to rebuild is the REPOSITORY
tree's, which the operational case does not run.

## What it does not do

It does not invalidate the MPI results. Checked:

- The run tree's kernel carries the SCALAR `ncmin` -- declaration at its line
  789, assignments at 855 and 857 -- so the candidate mechanism those findings
  name is present in the binary that produced them.
- The two revisions differ by 114 lines and **none of the differences touches
  `ncmin` or the interface transfer statements**.

So the MPI findings stand, with their scope stated: they are about a deployed
binary built from a kernel revision that differs from the SHA-pinned reference
in 114 lines elsewhere.

## What it blocks

The Arm L diagnostic test. Building the arm into the repository tree -- which
was done, and the legacy rebuild came back BIT-IDENTICAL to the original binary,
so the toolchain is deterministic and the tree is unchanged -- produces a
binary the operational case never runs.

Testing whether Arm L removes the decomposition difference needs the arm built
in the RUN tree. The variant generator applies cleanly to that revision (21
lines changed, no line over the source's own maximum), so the obstacle is not
technical: it is that the run tree is outside this repository and rebuilding a
binary there is the owner's to authorise. It was attempted and refused by the
sandbox, and the run tree was left untouched -- kernel `a06c954b`, binary
`a40bd80f`, both verified unchanged afterwards.

## What should be recorded on every MPI claim

    scope: the deployed KDM6AD+ tree's kernel revision a06c954b, built 24 Jun,
    which differs from the SHA-pinned reference in 114 lines -- none of them in
    `ncmin` or the interface transfers.
