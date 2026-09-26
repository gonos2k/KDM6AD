# S15 step-2 evidence checklist

- [x] Exact step-2 window, owner-5 schedule, retained LC05 input hashes, 40 s
  final time, fixed `dt=20 s`, one rank, and one thread were pinned before link
  and launch.
- [x] Macro-off source and macro-on WRF preprocessing used the pinned source;
  the invalid empty `WRFPLUS` preprocessing attempt was rejected as setup, not
  counted as model execution.
- [x] Three fresh focused objects were built, hashed, and inspected; the
  module-em FMA/tendency operation order was checked against the source.
- [x] A fresh executable was linked from those objects and the untouched,
  hash-pinned S8 archive. The link receipt records its command, SDK version,
  tool identities, all link-input hashes, and executable hash.
- [x] The launch gate checked the explicit step-2 plan, link receipt, fresh
  executable, exact run contract, and four retained-input hashes.
- [x] The 40 s discovery completed and saved forecast `Times` at 0/20/40 s.
  All six step-2 owner-5 summaries were present; 87,937 transition occurrences
  and six first QIB rows replayed exactly in f32.
- [x] Discovery produced 258 melt rows; all were `rhox_valid=0`. Their
  `brs1` values are not used as trusted thermodynamic evidence.
- [x] The logging-off control and logging-on confirmation used the same
  executable and inputs. Forecast frame 0/1/2 comparisons passed for all 253
  numeric variables plus exact `Times`; confirmation selected S15 bytes
  matched discovery.
- [x] Energy frames 0/1 passed for four numeric variables plus `Times`.
  Energy frame 2 is recorded as insufficient; precipitation and ocean outputs
  are empty and recorded as insufficient rather than parity passes.
- [x] Full stdout hashes, selected-stream hashes, NetCDF hashes, run identity
  hashes, and original private receipt SHA pins are available in the
  path-redacted public manifest and projections.
- [ ] Attribute the QIB transitions to upstream producer processes and resolve
  physical units / graupel policy. S15 remains OPEN pending that work.
