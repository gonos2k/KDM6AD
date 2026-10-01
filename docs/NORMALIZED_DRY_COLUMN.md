# One normalized dry-number column experiment

Run the same **fp64 selector 2 / dry-number 1** map for the graph forward,
value-only forward, JVP/VJP and independent centered differences. This is an
experimental microphysics diagnostic. Physical number/threshold policy, host
transport, RTTOV accuracy and observation approval remain open.

```sh
python oracle/scripts/run_normalized_dry_column.py \
  --input /path/to/native_5km_history \
  --library /path/to/libkdm6_c.2.0.0.dylib \
  --time-index 1 --i 3 --j 272 --output /path/to/new_result
```

The input is the retained model's native 5 km NetCDF frame. Coordinates are
zero-based; layers remain in native bottom-up order. The existing frame reader
derives temperature, pressure/Exner, moist density and thickness from the saved
fields. This is a snapshot-derived offline call, not a replay of a host physics
call's exact staged operands. QNCCN is read as stored, with no synthesized CCN.

The fixed candidate uses dt=20 s, existing ProgB behavior and internal volume
number thresholds `ncmin_land=ncmin_sea=10`. The dry-number boundary interprets
the four input QN fields per kg dry air; that interpretation is conditional and
does not settle S2. The selected direction is entry `qi` plus 1% entry `qv` and
`nc`; zero reservoirs remain unperturbed. VJP uses `u=Jv/max(abs(Jv))`. The
centered width is 1e-4. Each field's max-norm relative JVP/FD difference must be
at most 1e-5; JVP/VJP duality must be at most 1e-12. Endpoint spacing is reported
as a quantization estimate and does not relax the FD gate. Branch certification
is not measured by this command.

The command rejects nonfinite/negative states, nonpositive forcing, unsupported
mass/number or mass/volume pairs, an empty ice profile, invalid coordinates and
an existing output directory. It saves `arrays.npz` (inputs including XLAND,
graph/value-only outputs, both FD endpoints, direction, JVP/VJP/FD arrays) and
`result.json` (configuration, artifact hashes and checks).
A failed numerical check saves an explicit failure result and exits nonzero.
No observation cost or operational approval is granted by a successful run.
