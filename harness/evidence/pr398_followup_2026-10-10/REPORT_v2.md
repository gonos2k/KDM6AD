# PR398 V2 direct-H saved-frame and viewing-center results

**Result:** the single predeclared six-case batch returned all six RTTOV H outputs. Every case retained the same seven-channel support with all `rad_quality` values equal to zero. The cost was recomputed from each returned BT using the frozen mask, sigma 1 K, zero bias, and Huber delta 1 K. No KDM M step, backward pass, retry, native forecast read, or science acceptance occurred in this sensitivity run.

The execution used [PREDECLARED_v2.json](PREDECLARED_v2.json), plan SHA256 `ba389506ccdfbd835b282abf3a12ef39526149abf3dfdcc4f9581e04be95cebe`. Its pinned driver SHA256 `6f8b4c0c91fd5ce2c16975c76b7912119ac8c1a8edf5de81679efd5e40b1c830` matches the `0600` execution copy stored with the private result. The complete [public result copy](RESULT_v2.json) is byte-identical to the private `RESULT.json`; both have SHA256 `a246386cb2d5967924a771cecad1858270514be4b97c4ccef4be1658f40b1feb`. The private [backup manifest](</Users/yhlee/KDM6AD-k/host/research_evidence/pr398_sensitivity_20261010/PRIVATE_BACKUP_v2.json>) binds the original result, public copy, exact driver copy, plan, one-shot marker, and native intake hashes. The one-shot marker exists, and there is no failure or retry receipt.

To keep these results beyond the temporary worktree lifetime, I copied the result, execution-time driver, V2 plan, start marker, and private backup manifest byte-for-byte to `/Users/yhlee/KDM6AD-k/host/research_evidence/pr398_sensitivity_20261010/`. The canonical directory is `0700` and all five files are `0600`. [LOCAL_PRESERVATION_v2.json](LOCAL_PRESERVATION_v2.json) records each source/canonical path and matching SHA256 (receipt SHA256 `9b58259dad4de343bab3db08d56f76cccd7f31a93d1ea99a141191f02b66d2b4`). The temporary originals remain intact.

Each row evaluates `H(native saved State_t, Forcing_t)` at the exact saved labels `05:56:00`, `05:57:00`, and `05:57:40`, using frame indexes 1, 4, and 6. The fixed pair compares the AMI candidate center (`35.4192506933 N, 122.1372416465 E`) with the saved native cell center (`35.4156608582 N, 122.1433105469 E`) only as the location passed to `ami_geometry` for RTTOV viewing angles. The same native `j=86,i=48` column, state, forcing, pressure grids, surface values, optical density, and actual `HGT=0 m` remain in both rows at each time. This is a centroid viewing-angle sensitivity, not a pixel relocation, parallax correction, or footprint-overlap result.

| Native saved time | Geometry input | RTTOV zenith / azimuth (degrees) | Huber Jo |
| --- | --- | --- | ---: |
| 05:56:00 | AMI candidate center | 41.605267 / 169.606516 | 26.597685 |
| 05:56:00 | Native cell center | 41.600278 / 169.615875 | 26.600148 |
| 05:57:00 | AMI candidate center | 41.605267 / 169.606516 | 26.624654 |
| 05:57:00 | Native cell center | 41.600278 / 169.615875 | 26.627116 |
| 05:57:40 | AMI candidate center | 41.605267 / 169.606516 | 26.641499 |
| 05:57:40 | Native cell center | 41.600278 / 169.615875 | 26.643961 |

At each frame, native-center geometry increased BT by `0.000287–0.001107 K` across the seven channels relative to the AMI candidate-center geometry; the largest absolute channel change was about `0.0011065 K`. The corresponding Huber Jo increases were `0.0024632`, `0.0024621`, and `0.0024613` for the three frames.

With the AMI candidate geometry held fixed, the 05:57:00 BTs differ from 05:56:00 by at most `0.006688 K` across channels, and 05:57:40 differs by at most `0.010811 K`. The Huber Jo changes by `0.0269693` and `0.0438146`. The native-center geometry gives nearly the same temporal deltas. These temporal differences include the complete changes in each saved native State, pressure/P8W profile, optical density, and dynamic surface; they are not an isolated clock-offset perturbation.

The 05:57:00 and 05:57:40 labels lie inside the observation receipt's conditional file-level AMI interval only under its stated epoch/synchronization assumption. Per-pixel UTC remains unverified. No frame was interpolated. These outputs are `H(host(t))`, not the separate one-step `H(M(xb))` objective; they do not establish physical matchup or forecast skill.

The CTH-as-RTTOV-surface-elevation [V1 plan](PREDECLARED.json) is explicitly
marked `WITHDRAWN_UNEXECUTED` in [V1_WITHDRAWN.json](V1_WITHDRAWN.json); its
original source bytes are preserved with a `.disabled` suffix and the old V1
entrypoint now fails closed. The stale-hash V2 draft is preserved as
[PREDECLARED_v2_draft_unexecuted.json](PREDECLARED_v2_draft_unexecuted.json).
The executed V2 experiment uses no cloud-top-height value.

Validation checked every result row against the predeclared state, forcing, `rho_d`, profile, time, and geometry hashes, verified all-six all-channel quality support, and independently recomputed all six Huber costs from returned BT. The aggregate comparisons and file identities are in [RESULT_SUMMARY_v2.json](RESULT_SUMMARY_v2.json) and the V2 semantic fragment. No second H call was made for verification.
