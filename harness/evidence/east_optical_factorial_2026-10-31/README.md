# East optical four-arm direct diagnostic

Four locked direct RTTOV calls evaluated ten saved profiles and channels 10–16,
swapping serialized slot 7 ice content and effective diameter independently.
The first and second arm letters select guard (G) or pilot (P) content and
diameter, respectively. All other serialized inputs agreed. Every BT was finite
and all 70 quality values were zero in each arm. GG and PP reproduce all 70
receipt-mapped historical guard and pilot BTs exactly.

Across these profiles, GG = GP and PG = PP for every BT. Thus the diameter
contrasts and interaction are exactly zero for saved KMA BT and Huber values
in this intervention. Raw RTTOV radiance and native BT are not identical: GG
versus GP has 4/70 TOTAL differences (maximum 1.4210854715202004e-14 in
RTTOV radiance units) and 1/70 native BT differences (maximum
2.842170943040401e-14 K); PG versus PP has 2/70 TOTAL differences with the
same maximum and no native BT differences.
The content contrast PG − GG ranges from −5.370063623403723 to
−0.798306485991759 K. Its unweighted delta=1 Huber numerator change sums to
+123.92018052340481 over 70 cells, using `math.fsum`, corresponding to +0.000328402829590676 on
the unchanged full-M0 denominator 377342. BT and loss effects are distinct.
`analysis.json` gives every profile/channel value, contrast and interaction.

The preflight retained 40 positive but subthreshold ice-content rows with saved
cloud fraction zero in GG/GP; this is a serialized gate condition, not evidence
that the upstream clamp executed or a general absence of diameter sensitivity.
The 10-profile result does not establish a domain-wide effect, physical
mass/number budget, JVP/VJP, forecast skill or analysis acceptance. The nominal
observation is 00:00 and checkpoint 00:01, pixel UTC is unverified, and RTTOV
upper-background/model-top assumptions remain those of the parent witness.
The hydrotable was pinned prospectively for this run; the parent historical
calls did not individually pin it at execution.

Two earlier attempts failed at GG, each producing zero completed direct results.
`excluded_attempts.json` records their separate receipt, attempted-run and
failure-log hashes; those calls are excluded from the successful four. Hashes
were checked against retained private logs after failure.

## Offline replay and provenance

```sh
python3 harness/evidence/east_optical_factorial_2026-10-31/packet.py replay harness/evidence/east_optical_factorial_2026-10-31/export.json > /tmp/east-factorial-analysis.json
cmp /tmp/east-factorial-analysis.json harness/evidence/east_optical_factorial_2026-10-31/analysis.json
python3 -m unittest discover -s harness/evidence/east_optical_factorial_2026-10-31 -p 'test_*.py'
```

Replay reads the supplied export file once, checks those exact bytes against
the manifest's pinned `export.json` SHA-256, and analyzes the same bytes.
A byte-identical copy at another path is accepted; changed metadata, BT or
even whitespace is rejected before numeric analysis. Replay also verifies
the source/packet inventory and parent witness, including its
receipt-mapped guard and pilot captures, then recomputes the analysis. The
parent witness replay invokes `crosscheck_qnc.py` on the QNC archive and
`crosscheck_pilot.py` on the pilot archive; those checks join receipt-mapped
profile ordinals to captured BTs.
It makes zero model calls. The exporter reads the locked preflight, run attempt,
four receipts and captures; checks source/runtime/asset and consumed-input hashes,
slot assignments, historical optical values, and exact 10×7 quality; and records
receipt, capture, source and case hashes without private absolute paths. The
preflight manifest SHA is `87af6b7e6db1b0e51072b74a1158f5583565b9d9664cf5ed77b1899d64715371`;
runner and locked launcher SHAs are respectively
`1bc7640f620f71e519585f77f52810423f92a27f05cc994654de472522871dc4` and
`6640e17a52b21f5ead3a32bf77a56f0c503bf0f4ac73cff9730edd3f3acf8c9c`.
Private inputs and logs remain retained provenance: this compact export cannot
independently authenticate execution or reconstruct all input bytes. The parent
witness retains its own capture-time pinning limitations.

The separately executed private verifier summary is retained as
`private_verifier_summary.json` (SHA-256
`2d9bbdf97e483ab7f36d0348c9f7317e80d6030df3c633f1344a09759a16ced8`);
its verifier source SHA is `9cd1876b46d569429ec791d486f8c185f01e020c10cd2c29d39f32c84a7d611b`.
This is an attributed private check, not a verifier re-executed by public replay.

The observation/mask baseline NPZ is SHA-checked after the run against the
parent witness, but it was not included in the execution preflight pins.
The observation attribution is therefore a post-run binding, not proof of the
exact observation bytes at execution. Raw direct RTTOV output files are included
and hash-checked against the attributed private verifier summary.
