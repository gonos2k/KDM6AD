"""The arms, once.

Every arm the refinement driver can emit, with the two facts the harness needs
about it: which base kernel it edits and which number-transfer metric its
interface applies. Everything else that used to be spelled per arm -- the
manifest vocabulary, the metric table, the structurally-legacy set, the
bindings' derived-arm map, the build script's compile defines -- is read from
here.

The Fortran driver cannot import this, so `g33_refine_driver.f90` keeps its own
`#ifdef KDM6_ARM_* -> ALGOTAG` cascade; one test holds the two together.
"""

#: Insertion order is the manifest's vocabulary order; keep it.
ARMS = {
    "legacy":           {"base": "legacy",       "metric": "thickness"},
    "conservative":     {"base": "conservative", "metric": "thickness"},
    "nmass":            {"base": "legacy",       "metric": "moist_layer_mass"},
    "lncmin":           {"base": "legacy",       "metric": "thickness"},
    "nmasslncmin":      {"base": "legacy",       "metric": "moist_layer_mass"},
    "cons_nmass":       {"base": "conservative", "metric": "moist_layer_mass"},
    "cons_lncmin":      {"base": "conservative", "metric": "thickness"},
    "cons_nmasslncmin": {"base": "conservative", "metric": "moist_layer_mass"},
    "nmass_dry":        {"base": "legacy",       "metric": "current_dry_layer_mass"},
    "nmass_dry_window": {"base": "legacy",       "metric": "window_dry_layer_mass"},
    "melt_g1":          {"base": "legacy",       "metric": "thickness"},
    "melt_g2":          {"base": "legacy",       "metric": "thickness"},
    "melt_g3":          {"base": "legacy",       "metric": "thickness"},
    "melt_g4":          {"base": "legacy",       "metric": "thickness"},
    "melt_g5":          {"base": "legacy",       "metric": "thickness"},
}

BASES = ("legacy", "conservative")


def names() -> tuple:
    return tuple(ARMS)


def base(arm: str) -> str:
    return ARMS[arm]["base"]


def metric(arm: str) -> str:
    return ARMS[arm]["metric"]


def metrics() -> dict:
    return {a: s["metric"] for a, s in ARMS.items()}


def derived() -> dict:
    """arm -> base, for every arm that is not itself a base."""
    return {a: s["base"] for a, s in ARMS.items() if a not in BASES}


def structurally_legacy() -> frozenset:
    return frozenset(a for a, s in ARMS.items() if s["base"] == "legacy")


def compile_defines(arm: str) -> list:
    """What refine_build.sh passes the driver: the arm's own define, plus the
    conservative call-shape define when the base is conservative."""
    if arm == "legacy":
        return []
    if arm == "conservative":
        return ["-DKDM6_CONS"]
    out = [f"-DKDM6_ARM_{arm.upper()}"]
    if base(arm) == "conservative":
        out.append("-DKDM6_CONS")
    return out


if __name__ == "__main__":
    import sys
    # `python3 g33_arms.py defines <arm>` -- for the build script
    if len(sys.argv) == 3 and sys.argv[1] == "defines":
        if sys.argv[2] not in ARMS:
            sys.exit(f"unknown arm {sys.argv[2]!r}; known: {' '.join(ARMS)}")
        print(" ".join(compile_defines(sys.argv[2])))
    elif len(sys.argv) == 2 and sys.argv[1] == "names":
        print(" ".join(ARMS))
    else:
        sys.exit("usage: g33_arms.py names | defines <arm>")
