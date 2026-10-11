# PR403 final Green consistency review

The held-out scene packet, current observation contract, completion matrix and coordinator narrative are consistent. Current satellite-observation input is limited to source-pinned GK2A AMI L1B. The two exact 05:56 nominal slots are decoded through the unchanged production LA reader and paired calibration, with nine channels retained and channels 10–16 still the seven-channel analysis subset. Original source hashes, row/column, navigation, packed words, DQF, BT and raw time metadata are bound to the plan and private archive.

The fixed-point and 5×5 selections are location-only. All-zero DQF is described as L1B data quality; the reports do not infer cloud-free conditions, cloud phase, ocean-surface truth or SST. OBT filename/acquisition labels, planned UTC and unverified pixel UTC remain distinct. A verified time matchup is not claimed.

The added `REPLAYED_PATCH_RADIANCE.csv` is correctly labeled an additive arithmetic replay from retained DN and the pinned gain/offset. Its 450 per-cell/channel rows were produced after the original decode, are not part of the original NPZ/CSV, and add no new sensor acquisition or spatial mean. The output unit and input/calibration/output hashes are recorded separately.

The coverage review and coordinator correctly limit completion to observation intake: no July 20/21 native inputs or same-configuration analyses are present, and July 19 model state is not relabeled for those dates. The two scene dates are not asserted to be independent meteorological events. PR401/402 remain evidence for their separate July 19 fixed case, not held-out-date H/K runs. The historical 56/75 reference stays unchanged and no new score is assigned. I found no Green consistency blocker.
