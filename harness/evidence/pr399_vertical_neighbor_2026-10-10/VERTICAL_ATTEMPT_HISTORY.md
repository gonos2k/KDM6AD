# PR399 vertical analysis attempt history

- V1 source `vertical_structure.py` and its plan remain preserved with the exact `STARTED_ONCE.json` and `FAILED.json` receipts under `graphify-out/pr399-vertical-neighbor-2026-10-10/private/`. It read and verified the already-saved PR398 NPZ, then stopped at a missing `kdm6` import path before derived arrays were written. It opened no native forecast and called no M/H/optimizer. The public explanation is `VERTICAL_ATTEMPT1_SETUP_FAILURE.json`.
- V2 uses a new source, plan, output directory, canonical private directory, and artifact names. Red reviewed the exact source and plan before the one-shot derivation. The V2 outputs are the execution-bound artifacts; unsuffixed `VERTICAL_RESULT.*` / context, sensitivity, and report files are byte-identical convenience copies of their V2 counterparts.
- The only scientific input is the existing canonical PR398 3×3 patch NPZ. There was no model/RTTOV/optimization run and no native forecast re-read.
