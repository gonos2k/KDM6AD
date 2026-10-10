# PR399 vertical-neighbor direct-H Green review

Green verified the fixed attempt-2 comparison against the hash-bound native and PR398 evidence. The nine rows cover native frame index 1 (`2025-07-19 05:56:00`), `j=85..87`, `i=47..49`, at one fixed AMI candidate geometry, with channels 10–16, the same all-seven frozen support, target BT, sigma 1 K, bias 0 K, and Huber delta 1 K. The PR398 center row is reused only after exact State, Forcing, dry-density, P8W, surface, profile, geometry, options, and RTTOV asset checks.

Attempt 1 is preserved as a fixture-setup error before any H call. Attempt 2 supplies all six arrays required by the existing fixture helper and prepares the eight neighbor profile fixtures offline. Each profile contains 66 layers and 67 interfaces; Green and Red independently verified the per-cell pressure, temperature, humidity, O3, and CO2 vectors. The offline preflight records zero H/M/optimizer calls. The subsequent authorized serial batch made eight new direct H calls, retained all nine rows, and made no M, optimization, or native-model call.

All nine rows returned with seven zero `rad_quality` flags. The reused center cost is `26.59768478212186`; neighbor `Jo` ranges from `26.140741655222705` at `(85,49)` to `26.801101203080805` at `(85,47)`. The largest absolute channel BT difference from the center is `0.15186496873326405 K` at `(87,47)`. Green recomputed every saved `Jo` from the saved BT and confirmed exact agreement within `1e-12`. The postrun audit also confirms actual RTTOV profile files, geometry angles, and surface files match the hash-pinned inputs.

The comparison is direct `H(native saved State, Forcing)` under a fixed viewing geometry. Spatial differences combine native state, pressure, density, and surface changes. It establishes neither footprint overlap nor pixel-time alignment, parallax, a scientific matchup, or forecast skill.

Evidence hashes:

- Executed source: `1ab829a94daa80c211984f7ddfbbe9bb825aa859a44bdc5aa83645368459e947`
- Attempt-2 plan: `5451176d914b5758ffc6315f08a957ae0b6f6ae38019df38faa5b4e58c086afb`
- Result: `2bf488dca1a39f5c8d6fc19fd299a5a4de2560cfa083b98dc0bafd133f150422`
- Private NPZ: `4e2c36075e69d000bff48db8b2586ff1378adda3297508c58caa72b092e1c793` (`0600` file under `0700` directory)
- Postrun audit: `f8e3c941f57dc39faa72dc7b7c10bec2c4dfe5cdc2a458bfbf65d61da4c0636`
- Canonical attempt-2 archive manifest: `e5e45d7bacb10c8edab30906b0c2f2cf6e05db3d3a97507f06b4b83aecaf31cb`
