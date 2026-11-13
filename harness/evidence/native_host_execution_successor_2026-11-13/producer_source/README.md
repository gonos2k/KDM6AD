# Isolated producer source reconstruction

This source-only packet reconstructs the reviewed v5 research source from the archived `ebe0260b` libtorch tree and the inspectable `v5_changes.patch`. It verifies 68 base files, 16 changed paths, and all 76 resulting file hashes against the filtered private v5 source-before snapshot (excluding its private audit document). It does not establish installed DSO identity, build or execute the model, or establish scientific or physical validity.

Run `python3 replay.py` and `python3 -m unittest discover -s . -p test_replay.py`. Reconstruction uses a temporary directory and the Git executable, without a repository history or network access.

SHA-256: base archive `7ac32efbbe58dc2c6b4793dc40f0c22a3434d63b55026e2c629cfc936166041f`; patch `8788add86cfe01f678f27d90e24496b63cd30ce65cc5c2c8b4eee25244a9863d`; manifest `ad19651e4571f75e30b62668f4c3097b9c6018dae19ea4b653442830cafa1fef`.

The local `.gitattributes` disables Git's trailing-whitespace warning **only for the patch file**. The patch retains the exact source whitespace needed to reproduce the private build bytes; replay still checks every reconstructed file SHA.
