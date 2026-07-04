# HARNESS KDM6 PARITY GUIDE

Scope: parity and dump-comparison scripts for KDM6/KDM6AD.

## Overview

`harness/` is the lightweight verification layer around host runs and substep
dumps. It is stricter than a scientific tolerance comparison because the current
contract is raw-bit forward parity.

## Files

| File | Role |
| --- | --- |
| `strict_bitwise_nc.py` | final NetCDF raw-bit comparator |
| `run_ss_case.py` | SS namelist/run wrapper copy |
| `compare_step1_kdm6_bitwise.py` | step-1 KDM6 bitwise helper |
| `compare_step1_kdm6_vs_kdm6ad.py` | mp37 vs mp137 comparison helper |
| `compare_substep_stage.py` | substep dump stage localizer |

## Conventions

- Bitwise comparison means variable-set equality plus raw integer view equality
  for numeric values.
- Keep `Times` handling explicit; do not generalize non-numeric exemptions.
- Namelist edits must be exact-key replacements. `history_interval` must not
  rewrite `history_interval_s`.
- Keep host-tree copies of run/parity scripts behaviorally aligned when changing
  comparator semantics.

## Anti-Patterns

- Do not introduce tolerance-based pass/fail behavior into strict comparators.
- Do not compare stale run directories; scripts should pick or receive explicit
  run paths.
- Do not hide missing variables as zero-difference success.

## Commands

```bash
python3 harness/strict_bitwise_nc.py <mp37-history-file> <mp137-history-file> 1
python3 harness/compare_substep_stage.py --help
```
