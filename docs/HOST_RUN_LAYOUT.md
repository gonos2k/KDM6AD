# Host run layout — which case / resolution / directory is which

Disambiguation map for the WRF host run directories under `host/` (gitignored).
Written after a session confused three different cases. **The real-time DA target
is the 5 km LC05 SS case only.** When in doubt, re-check `DX` with
`ncdump -h <wrfinput> | grep ':DX'` — 5 km ⇒ `DX = 5000`.

## The three cases that get confused

| Case | Resolution | Grid | Where | Role |
|---|---|---:|---|---|
| **LC05 SS real case** | **5 km** (`DX/DY = 5000`) | 234 × 282 (e_we 235 / e_sn 283), 39 lev | `host/lc05_da_run/` → symlinks to the canonical case (below) | **THE real-time DA target.** GK2A 2025-07-19. |
| old 1 km experiment | 1 km (`DX = 1000`) | 100 × 100 | `host/KIM-meso_v1.0/run/wrfinput_d01.37` (a per-scheme IC copy) | previous experiment — NOT the DA case |
| ideal experiment | 100 km (`DX = 100000`) | 41 × 81, `ideal_case = 7` | `host/KIM-meso_v1.0/run/namelist.input` | previous experiment (uses `ideal.exe`) — NOT the DA case |

## Directory map

```
host/
├── lc05_da_run/                         ← REAL 5 km DA run dir (symlink farm)
│   ├── wrfinput_d01  → …/SS/wrfinput_d01 (374 MB, DX=5000, 234×282)  ← 5 km IC
│   ├── wrfbdy_d01    → …/SS/wrfbdy_d01                                ← real BCs
│   ├── namelist.input   (dx=5000, run_hours=3, hist 5 min, mp_physics=137)
│   ├── wrf.exe       → host/KIM-meso_v1.0/main/wrf.exe
│   ├── klfs_lc05_fcst.202507190000   (3.6 GB — the 3 h 5 km forecast trajectory,
│   │                                   37 frames; the DA's forcing)
│   └── obs_products/                 (gk2a_superob_{0000,0100}.pt on the 5 km grid,
│                                      65 988 = 234×282 cells × 16 ch; ko_to_lc05_mapping.pt)
├── KIM-meso_v1.0/
│   ├── main/     wrf.exe, ideal.exe, real.exe  (WRF V4.6.0, built 2026-07-04,
│   │             link @rpath/libkdm6_c.dylib → ../../libtorch/install/lib)
│   └── run/      ← 100 km IDEAL experiment (NOT the DA case)
│                   namelist.input = ideal_case 7, dx=100000, 41×81
│                   wrfinput_d01.37 / .137 = 1 km per-scheme IC copies (old)
│                   run_parity.sh / run_kdm6ad.sh use ideal.exe + `rm -f wrfinput_d01`
└── (canonical 5 km case data lives OUTSIDE the repo:)
    /Users/yhlee/KDM6AD+/KIM-meso_v1.0/test/ss_real_case_20260619_063620/SS/
      wrfinput_d01, wrfbdy_d01, + all WRF data tables  ← lc05_da_run symlinks here
```

## The C ABI dylib the host loads

- `host/KIM-meso_v1.0/main/wrf.exe` records `@rpath/libkdm6_c.dylib` and its rpath
  resolves to **`libtorch/install/lib/libkdm6_c.dylib`** (the in-repo install).
- That install is currently the **2026-07-04 pre-hardening build**. The sealed,
  hardened C ABI is tag **`abi-v2-hardened`** (`origin/main@a53503e`); re-installing
  it there is a drop-in (v1 byte-frozen; `wrf.exe` uses only the 9 C ABI symbols via
  the dev symlink). See [HOST_INTEGRATION](HOST_INTEGRATION.md) and
  [PR3 visibility design](PR3_VISIBILITY_DESIGN.md).

## Rules (avoid the confusion that happened)

1. **Real-time DA = 5 km = `host/lc05_da_run/`.** The DA (`oracle/kdm6/da_*.py`,
   `run_fulldomain_lc05.py`) consumes the 5 km grid + the 5 km superob products.
   The v10 evidence artifact's `n_domain = 65 988 = 234 × 282` confirms 5 km.
2. **Do NOT use the ideal scripts for the real case.** `run_parity.sh` /
   `run_kdm6ad.sh` run `ideal.exe` and `rm -f wrfinput_d01` first — for the real
   case run `wrf.exe` directly on the existing 5 km `wrfinput` (no `ideal.exe`).
3. **`/Users/yhlee/KDM6AD` (no `+`, no `-k`) is a STALE sibling** (kdm6_libtorch @
   `eb1c823`, June wrf.exe) — a red herring; not this repo's host.
4. **5 km is the fixed model resolution**; 4 km is only the superob assignment gate,
   not a grid — GK2A is superobbed onto the fixed 5 km grid once, then reused.
