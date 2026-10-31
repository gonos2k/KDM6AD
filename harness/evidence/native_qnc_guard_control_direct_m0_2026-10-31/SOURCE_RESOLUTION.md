# Source, build and runtime resolution

The private producer ran frozen public commit `302328a5265c53e1a21ffe557dc087b8bfdd87ad`;
the operational harness/oracle/data tree recorded 517 files and SHA-256
`1ef3cc94d90465cea370c0974445f1d54b8de3192d33d2f5438464de41c0609f`.
The exact executed runner snapshot is `executed_sources/run_control_direct.py.txt`,
SHA-256 `bdd80f465509bf7d5f0a935cfdb4f3823a4a03950dc54f890d54b47e0ae0e760`.
It binds original baseline NPZ SHA-256
`c919f13c3ceb4defec42e43e0b60ad71d22d10f57a9454f6f880f98ec1bf9144`,
and #483 direct archive SHA-256
`736779e7084bccc0a4348eb62cbd0eacf753173a48146a37657e92e65f88df77`.
The source tree hash is a producer snapshot, not a redistributable source archive.

Trace-on/off host result hashes are respectively
`35ddd709eaf5d6ab1aebe9271202259011ec1cb0a9f3e1e03fff791590701fc7` and
`69d1735feb976539f7706131a0345c35a3c27ec1c8e04b99c5c1b218b88b0393`;
both bind checkpoint `950bc5d67dc8cf4980091ecac19a9b7b1ba94756e83d9bd101180e55863c0bb6`.
The private build receipt SHA-256 is
`4a0902d40ef369ce025fa42f6f44f3df815aee11e509ce6f65d4f56ba24c0b23`,
with host executable `d919d84b0dfa252b09a268f159fc9e691185c8f2c7287a30576bb8de1267bd82`
and DSO `9e01047610e290db36505ad52919a9f99ad97b8fe2c2924eb8aca2cba88ad92e`.
Trace-on/off plans hash to `452f341a22328aeaf304ae5b4dc0db9ed15168f1f6d9a6f0a260090260474912`
and `bda6367e47db9e0fe1bee9133e47230b612e6723507ccc6c8bcc77e7a6889f6c`.
These private files were checked at export but are not bundled for independent reopening.

The binding records Python 3.10.11, NumPy 2.2.6, Torch 2.13.0 and netCDF4
1.7.4, including selected executable and extension hashes. The RTTOV executable
hash is `0909d289778d3ea91f6300fd8c5f88e5e1dcc0528d260aec94f3aab0bc7692fd`,
coefficient file hash `73401691b9e5777daf0e4d8ba6d77dfc912c0d32bd8b70937886fcd91b54a7b5`,
and calibration hash `a6f830aa04e19f6982aa6ff36e832464a5b32fdcf8200211956969d5eb48325d`.
The saved binding records the complete asset and runtime comparison with #483;
the calibration path alone is normalized to account for relocation. The
bindings do not pin every native library loaded at runtime.

Archive SHA-256: `568b09524f6ab5ca9eaade51cd77c45ebcbe2b17afe5bd0827ff0590717845c5`.
Binding SHA-256: `9380922ab5e7e30e26ea2602fcccd1c43ba170cfa60c014b7541d99d00fc0864`.
Summary SHA-256: `7818fb559bd1358cd968a538b2ed1690bfe2622aefd2e43a3839bd84a6d455e7`.
Strengthened verifier/exporter SHA-256: `04c4bc9674f36249546ef60da7fc3901bb48fcbd2c5f7326b239923310fdd85d`.
The exporter used for the original copy is preserved at
`executed_sources/verify_export_executed.py.txt` (SHA-256 `69739993c1ef54b0f78abe1dc49901bc2258d820b79dfff75a9b6be83a2fe9fc`).
After export, a separate read-only check compared every archived file byte for
byte with the finalized private producer files; all 391 hashes matched.
The producer's full private call folders remain outside the packet; their
presence was checked in a separate private replay, and their contents are not
hash-verified by this public packet. No hash independently proves execution.

The separate private read-only verifier source is preserved as
`executed_sources/verify_control_direct.py.txt` (SHA-256
`9605bb42872e8637f76461a9eaf5c89ccdfd75cf2cc4a91f9f43ebe248a974ab`).
Its private report records a successful check, including presence of all raw
call directories; the public replay does not rerun that verifier or reopen them.
