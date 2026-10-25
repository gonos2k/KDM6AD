# Native full-physics observation baseline

This packet reports direct RTTOV observation costs from the actual full-host
checkpoint at **2025-07-19 00:01:00** (timestep 3), over all 65,988 native
columns and 39 model levels. It is a no-new-analysis control; the 00:00:40
restart already carried prior unaccepted T/Q diagnostic-DA history, as described
in the [H1 host-pair report](../native_full_physics_forward_2026-10-25/REPORT.md).
The observation bundle is the original nominal 00:00 KO slot. KO pixel UTC is
unverified, so no temporal interpolation or time correction is applied.

`native_full_physics_observation_baseline.npz` contains the full-domain
observation BTs, baseline direct BTs, quality and source masks, profile validity,
reason codes, mapped owner IDs, and native `i/j` indices. It does not contain the
private 12-field checkpoint state or per-profile RTTOV case files.

Run the arithmetic replay with:

```bash
python replay.py
```

The replay verifies the packet SHA, reopens the exact hashed bytes with
`BytesIO`, checks full flat-index coverage and the M0 gate, and recomputes
per-channel and per-chunk Huber sums with `math.fsum`. It needs Python and NumPy
only; it makes no RTTOV, KDM, host, cleanup, finish, or optimizer calls.

The baseline has 377,342 supported channel cells (`Z=377342`), a global Huber
numerator of 4,153,766.894054753, and cost 11.007963317242059. All seven channels
have 53,906 supported cells each. The edge map counts all 1,028 outer-ring
columns as input. It distinguishes source coverage from model profile and
RTTOV quality exclusions.

The fixed KO matched bundle has all seven raw-source coverage flags valid at
65,988 mapped columns, and every source DQF/QC cell is valid. This reports the
coverage of that pinned bundle; it is not a new provider navigation or
observation coverage certification. Exclusion counts are separate: 41 initial
negative-number rows, 1,033 checkpoint profile-invalid rows, one q_min-invalid
row, 11,007 rows with direct RTTOV quality failures, and 53,906 rows admitted
with support.

One column (flat index 28195) was omitted from the RTTOV profile input because
its converted dry-air humidity was below RTTOV's strict `1e-11 ppmv` minimum.
Its native state remains in the full-domain capture with an explicit reason;
the native Q value was not changed. The original unfiltered chunk55 RTTOV
failure is preserved, and the successful filtered output was recovered from
that single direct call's saved output without another RTTOV invocation.

This is a baseline observation diagnostic. All three tested candidate T/Q
updates were inadmissible on frozen baseline support, so no candidate or
intersection cost is reported; see the [candidate trial summary](../native_full_physics_trials_2026-10-25/README.md).
The packet does not certify water/energy closure, raw number-moment units,
forecast skill, or unattended cycling.

The exact first exporter was not captured. A subsequently frozen independent
reconstruction reads all 129 hash-pinned chunk outputs and the original KO
owner mapping. It reproduces every array byte and the complete NPZ container
byte-for-byte (`c919f13c…9144`), with zero model calls. Its exact source and
receipt are included; the original unavailable source attribution remains in
the producer history rather than being relabeled. The reconstruction source
retains its configured local input paths; private checkpoint data are not
included.
