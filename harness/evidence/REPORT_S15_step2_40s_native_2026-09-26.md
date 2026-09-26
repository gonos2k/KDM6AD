# S15 owner-5 step-2 native discovery and noninterference

**Disposition: S15 remains OPEN.** The fresh step-2 executable produced owner-5
QIB nonnegative-to-negative transition occurrences during the second 20-second
model timestep. Exact f32 replay and the same-executable populated-output
noninterference checks passed. This local update census does not identify an
upstream face cause, establish a physical unit, or select a graupel policy.

## Executed configuration and provenance

The run used the retained LC05 5 km case, `mp_physics=37`, fixed `dt=20 s`,
`duration=40 s`, one MPI rank and one thread. History output was requested at
20-second intervals. The model completed at 0, 20, and 40 seconds, and the
runner reported a 1×1 process grid with all active inputs complete and stable.

The source-pinned plan used for prelink and launch is
[`s15_native_step2_40s_plan_2026-09-26.json`](s15_native_step2_40s_plan_2026-09-26.json),
SHA-256 `e14cd636665d880816a7fa8a87e672670de832bd7c7eb167bdaeb169b00d0267`.
It retains step 1 as the default and selects step 2 only by explicit plan-bound
selection. The public manifest and redacted receipt projections are in
[`s15_step2_public/`](s15_step2_public/).

The active retained-input SHA-256 pins were: namelist `064b6f5e…`, initial
state `5a9ae8da…`, boundary `d46e5d71…`, and auxiliary chain input `c8e300d2…`.
Their full digests and the source, preprocessing, object, link, and run receipt
chain are in the public manifest. The canonical host was not modified.

The compile used GNU Fortran 15.2.0 through `mpif90` on arm64 with the
`KDM6_PROGB_VALIDITY_CAPTURE` overlay. The three generated overlay source
hashes, three WRF-preprocessed Fortran hashes, and three focused object hashes
are recorded in the compile projection. A fresh `module_em.o` disassembly
confirmed the required FMADD operations for RK mass and numerator, with
tendency multiply and add kept separately rounded. The link used the three
reviewed objects and untouched S8 archive
`f27a3633cae66c412123296eed3ebc3caeb3080ab7e8c9f224c18ab55c987a94`.
The new regular-file executable SHA-256 is
`7399d7cbc472f09f61a9fbe11cf681406f3bc6cc13a62f78c6a4df25d8f2f497`.

## Step-2 discovery

The selected S15 stream contained the complete six-key owner-5 census:

| RK stage | Tile 1 occurrences | Tile 2 occurrences | Total |
| --- | ---: | ---: | ---: |
| 1 | 18,356 | 11,017 | 29,373 |
| 2 | 36,182 | 20,849 | 57,031 |
| 3 | 1,038 | 495 | 1,533 |
| **Total** |  |  | **87,937** |

These are transition **occurrences across RK stages and tiles**. They are not
distinct cells or a count of final negative cells; a cell may transition at
more than one RK stage. The six emitted first-event QIB rows each had a
nonnegative source input and negative captured output. The six bounded raw-f32
witness rows in
[`s15_native_step2_qib_witnesses_public_2026-09-26.json`](s15_step2_public/s15_native_step2_qib_witnesses_public_2026-09-26.json)
replay bit-for-bit under the public source-order arithmetic verifier.

The run emitted 258 trace-graupel melt rows. All had `rhox_valid=0`, so the
captured `brs1` values are untrusted for thermodynamic attribution. The public
packet reports the melt count and raw-stream receipt hashes; it does not
publish the full selected stream or melt-row operands.

The full discovery stdout was 472,926 bytes, SHA-256
`90687dc2a2c037c9ca4a33f0f82e5d233fbb8a0673ee9687d83f7dd2ddbad49d`.
The exact S15-only stream was 50,380 bytes, SHA-256
`992f51208d4b32fd835a0d468c861e3c7bbb01a28480f45d92cd075c2c396a0b`.
Inherited S10 diagnostics, if present, remain only in full stdout and were
excluded from S15 replay.

## Same-executable noninterference

The logging-off control and logging-on confirmation used the same fresh
executable, retained inputs, namelist, and 40-second schedule. Both completed
successfully with stable inputs. The control emitted no S10 or S15 event rows.
The confirmation selected stream was byte-identical to discovery at 50,380
bytes with the same SHA-256. Its six owner-5 summaries and all 264 QIB/melt
event rows passed exact f32 replay, including the same 87,937 transition
occurrences and 258 melt rows.

The raw-bit comparator found all 253 populated forecast numeric variables and
`Times` identical at frames 0, 1, and 2. The energy output contained four
numeric variables and `Times`; it matched at its two saved frames, 0 and 1.
Energy frame 2 is **insufficient** because no third energy frame was saved.
The precipitation and ocean files had zero frames and zero numeric variables;
they are **insufficient**, not parity passes.

The full control stdout was 46,761 bytes, SHA-256
`3fc2e91bcee7cb82b0862b9f5f3765a1b674fd178b2b83c51fbd5311296272d5`.
The full confirmation stdout was 472,918 bytes, SHA-256
`b9a1c7e9a894888c6783137d5746e9406907d93275e92e66d26985fa9c27725e`.
Each full-stdout digest is kept separate from the selected event-stream digest.

## Evidence limits and continuity

The earlier B20 step-1 evidence remains unchanged: six owner-5 summaries were
zero and it contained 51 trace-melt rows. Its default step-1 window and
historical replay remain covered by the existing regression test. The initial
A capture is still excluded because its generic QIB alias rows did not include
the owner field needed to attribute them to owner 5.

This step-2 result establishes a replayable owner-5 update transition census
and instrumentation noninterference for populated forecast frames. It does
not attribute the transition to an upstream process, establish particle mass
loss, resolve the invalid `rhox`/`brs1` melt ledger, or choose a graupel policy.
S15 therefore remains **OPEN**.
