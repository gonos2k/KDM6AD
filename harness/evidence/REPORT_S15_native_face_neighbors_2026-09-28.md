# S15 selected native QIB face neighbors

**S15 remains OPEN.** This capture connects two negative final-RK QIB cells
to the eight interior cells across their outgoing faces in one retained mp37
40-second case. QIB is the Registry's rime-ice volume mixing ratio
(`m³ kg⁻¹`), not cloud particle number. It measures the existing operator;
no repair was linked or run.

The optional `neighbors=True` overlay keeps the six earlier witnesses and adds
eight fixed RK3 receivers. The expected schedule is independent of the arrived
records: 42 axis, 10 PD-limiter and 14 RK records. The default six-witness
overlay is unchanged. The [bounded face stream](S15_face_neighbors_run4/face.stream),
[legacy context stream](S15_face_neighbors_run4/legacy.stream), and
[path-redacted native receipt](S15_face_neighbors_run4/native_receipt.json) are
the public replay inputs. Their SHA-256 values are respectively
`be71e8c8f43bac58b44f5e1610d095e1caa89a20dda163d64f1981f57596d817`,
`efc51e882d487e8d8f4bff3805cbec0b8ac5fa5d4ab8b1970babf74bce2e8900`,
and `1ebc554d00ffd9b1ecc641d4ce534406d9c0e27611550bbb1ece27e338715025`.
The full RSL and original host inputs remain in the isolated private run.

The overlay is macro-gated; macro-on syntax and all three fresh object
compiles passed. The same
linked executable SHA-256
`137237b2a5410b88e4a828cf0a789de1f830c21790b3f840f8933f993f6535eb`
ran capture OFF and ON with one rank and one thread. Both completed at 40 s.
Their forecast files have the same SHA-256
`49bbda101a367d5eeb9c460e21c2304767311d274dddecb17a4ec39fe14f1d04`;
all 254 common variables match raw-bit at each saved 0, 20 and 40 s frame.
This is same-executable instrumentation noninterference for this case, not a
fresh general host certification.

At step 2, RK3, the two measured donor stores are still negative:

| Tile; QIB donor `(i,j,k)` | RK store word | Approximate value | Interior outgoing receivers |
| --- | --- | ---: | ---: |
| 1; `(141,2,17)` | `991817B7` | −7.8630×10⁻²⁴ | 3; outgoing south face leads to the specified boundary zone |
| 2; `(141,143,16)` | `9C121BA4` | −4.8343×10⁻²² | 5; south receiver is on tile 1 |

The captured eight receivers have positive RK3 stores. Each listed interior
face has identical stored high and low binary32 words on its donor and
receiver side, including the tile seam:

| Donor outgoing face → receiver opposite face | High word | Low word |
| --- | --- | --- |
| tile 1 `(141,2,17)` xL → `(140,2,17)` xR | `AFE9346C` | `00000000` |
| tile 1 `(141,2,17)` xR → `(142,2,17)` xL | `316F8CEC` | `B1873D0B` |
| tile 1 `(141,2,17)` zB → `(141,2,16)` zT | `23568C35` | `80000000` |
| tile 2 `(141,143,16)` xL → `(140,143,16)` xR | `B1945D4D` | `00000000` |
| tile 2 `(141,143,16)` xR → `(142,143,16)` xL | `3386B136` | `00000000` |
| tile 2 `(141,143,16)` yS → tile 1 `(141,142,16)` yN | `B214D940` | `33A6051E` |
| tile 2 `(141,143,16)` yN → `(141,144,16)` yS | `30C25102` | `00000000` |
| tile 2 `(141,143,16)` zT → `(141,143,17)` zB | `A705343A` | `80000000` |

The Fortran tap labels axis 1 as Y, 2 as X and 3 as Z. The face map above uses
that mapping and the source PD outgoing signs: xL<0, xR>0, yS<0, yN>0,
zB>0, zT<0. The first donor also has an outgoing south face (`ADD8FDC1`)
to the `j=1` specified boundary zone; there is no accepted RK receiver for
that face. The public parser independently
replays all 14 producer-to-RK joins and source-ordered stores. The eight
shared-word comparisons above were separately calculated from its AX stream;
they do not establish metric-weighted conservation or a viable corrected
trajectory.

This QIB capture supplies measured operands for an S15 volume-scalar repair.
It does not measure S3 particle-number donors, resolve the trace-graupel
policy, close the boundary-zone exchange, or show a corrected host trajectory.
