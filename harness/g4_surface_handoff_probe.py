#!/usr/bin/env python3
"""Validate a source-pinned, selected-profile surface-handoff capture plan.

This is a replay contract for a future shadow capture, not a host instrumentor
or a native result. The expected event and operand universe is code-fixed and
constructed from the declared run configuration; it is never inferred from
the rows received. Pairwise differences localize an observed boundary only and
never establish a physical cause by themselves.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import re
from typing import Any


SOURCE_PINS = {
    "first_rk": "108a82b213c423acf916b91a0dd5f8084dc79288a01ca82d9f8d0ccb8febd53f",
    "surface_driver": "45543da3d3842985053d3d35cadccbd897aa4655c5f155d514133ce34f5524d5",
    "sfclay": "dfd7aae5ef1f0bd979246480af5276a1ee956bc216ec8dc6e82eb963ded761dc",
    "noahmp_driver": "9010a757da994ed8796c63ca97da354eaf60c5c732df4ea9acad5bc62a973890",
    "noahmp_lsm": "bd592a5b7db29000e715250e3a7c779ffb5e0dcc356f6b5a7d9e1c9f69c55282",
    "noahmp_mptable": "7fae6a77660c90ad80845565ecfb057093c100de41f35f25a7ffa63f41c19e5d",
}

SOURCE_PATHS = {
    "first_rk": "dyn_em/module_first_rk_step_part1.F",
    "surface_driver": "phys/module_surface_driver.F",
    "sfclay": "phys/module_sf_sfclay.F",
    "noahmp_driver": "phys/module_sf_noahmpdrv.F",
    "noahmp_lsm": "phys/module_sf_noahmplsm.F",
    "noahmp_mptable": "phys/noahmp/parameters/MPTABLE.TBL",
}

# Literal source anchors are deliberately narrow. A changed or duplicated
# call site invalidates the plan rather than moving instrumentation silently.
SOURCE_ANCHORS = {
    "first_rk": {
        "surface_driver_call": ("CALL surface_driver(", 1),
        "surface_driver_return": (
            ",pert_noah_tslb=config_flags%pert_noah_tslb                            &\n     &                                                           )",
            1,
        ),
    },
    "surface_driver": {
        "sfclay_call": ("CALL SFCLAY(u_phytmp,v_phytmp,t_phy,qv_curr,", 1),
        "sfclay_call_return": (
            "ustm,ck,cka,cd,cda,isftcflx,iz0tlnd,scm_force_flux  ) ", 1
        ),
        "sfclay_seaice_call": (
            "CALL SFCLAY_SEAICE_WRAPPER(u_phytmp,v_phytmp,t_phy,qv_curr,", 1
        ),
        "sfclay_seaice_call_return": ("sf_surface_physics  )", 1),
        "noahmp_dispatch_entry": ("CASE (NOAHMPSCHEME)", 1),
        "seaice_adjustment_post": ("!for NoahMP irrigation scheme", 1),
        "noahmp_call": ("CALL noahmplsm(ITIMESTEP,", 1),
        "noahmp_call_return": ("MP_HAIL = HAILNCV )", 1),
        "noahmp_urban_call": ("call noahmp_urban (sf_urban_physics,", 1),
        "noahmp_urban_call_return": ("dl_u_bep,         sf_bep,         vl_bep)", 1),
    },
    "sfclay": {
        "sfclay_entry": ("SUBROUTINE SFCLAY(U3D,V3D,T3D,QV3D,P3D,dz8w,", 1),
    },
    "noahmp_driver": {
        "water_category_branch": ("IVGTYP(I,J) == ISWATER_TABLE", 1),
    },
    "noahmp_lsm": {
        "noahmp_entry": ("SUBROUTINE NOAHMP_SFLX (parameters,", 1),
    },
    "noahmp_mptable": {},
}

PROFILES = (
    ("clear", 145, 11),
    ("warm_liquid", 139, 106),
    ("mixed", 124, 144),
    ("ice", 130, 209),
    ("rain", 112, 212),
)

MASS_LEVELS = tuple(range(1, 40))
INTERFACE_LEVELS = tuple(range(1, 41))
SOIL_LEVELS = tuple(range(1, 5))
SCALAR_LEVEL = (0,)


class SurfaceProbeError(ValueError):
    """The source, event plan, or captured operand universe is incomplete."""


@dataclass(frozen=True)
class G4SurfaceConfig:
    """Run switches that independently determine the selected call schedule."""

    timestep: int
    sf_sfclay_physics: int
    sf_surface_physics: int
    sf_urban_physics: int
    isfflx: int
    bldt_minutes: int
    adaptive_timestep: bool
    fractional_seaice: int | None


@dataclass(frozen=True)
class CaptureRow:
    arm: str
    sample: str
    j_fortran_1based: int
    i_fortran_1based: int
    event: str
    field: str
    level: int
    word: str


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def audit_sources(
    sources: Mapping[str, str],
    *,
    pins: Mapping[str, str] = SOURCE_PINS,
    anchors: Mapping[str, Mapping[str, tuple[str, int]]] = SOURCE_ANCHORS,
) -> dict[str, Any]:
    """Require exact source pins and independently declared unique anchors."""
    if set(sources) != set(pins) or set(anchors) != set(pins):
        raise SurfaceProbeError("source set differs from the fixed G4 source plan")
    receipts: dict[str, Any] = {}
    for name, source in sources.items():
        digest = _sha256(source)
        if digest != pins[name]:
            raise SurfaceProbeError(
                f"{name} source SHA-256 mismatch: expected {pins[name]}, got {digest}"
            )
        anchor_counts: dict[str, int] = {}
        for anchor_name, (anchor, expected_count) in anchors[name].items():
            count = source.count(anchor)
            if count != expected_count:
                raise SurfaceProbeError(
                    f"{name}.{anchor_name} anchor count {count}, expected {expected_count}"
                )
            anchor_counts[anchor_name] = count
        receipts[name] = {"sha256": digest, "anchor_counts": anchor_counts}
    return {"schema": "g4-surface-handoff-source-audit-v1", "sources": receipts}


def event_schedule(config: G4SurfaceConfig) -> tuple[str, ...]:
    """Build the independent event schedule from declared switches.

    The current G4 experiment must be step 2 with its known SFCLAY/Noah-MP
    path. `fractional_seaice` is mandatory because it controls a distinct
    state-conversion branch; a missing value cannot be guessed from trace rows.
    """
    if config.timestep != 2:
        raise SurfaceProbeError("G4 handoff plan is pinned to itimestep=2")
    if (config.sf_sfclay_physics, config.sf_surface_physics, config.sf_urban_physics,
            config.isfflx, config.bldt_minutes, config.adaptive_timestep) != (1, 2, 1, 1, 0, False):
        raise SurfaceProbeError("run switches do not select the pinned G4 surface path")
    if config.fractional_seaice not in (0, 1):
        raise SurfaceProbeError("fractional_seaice must be declared as 0 or 1")

    events = [
        "surface_call_pre", "sfclay_pre", "sfclay_post", "noahmp_dispatch_entry",
    ]
    if config.fractional_seaice == 1:
        events.append("seaice_adjustment_post")
    events.extend(("noahmp_pre", "noahmp_post"))
    events.extend(("noahmp_urban_pre", "noahmp_urban_post"))
    events.append("surface_return")
    return tuple(events)


# These are the minimal source-audited diagnostic operands for boundary
# classification. They do not claim to be every read in SFCLAY/Noah-MP.
EVENT_FIELDS: dict[str, dict[str, tuple[int, ...]]] = {
    "surface_call_pre": {
        field: SCALAR_LEVEL for field in (
            "XLAND", "IVGTYP", "ISLTYP", "VEGFRA", "XICE", "SST",
            "SST_INPUT", "SST_UPDATE", "ALBEDO", "EMISS", "TSK",
            "HFX", "LH", "QFX", "UST", "ZNT", "UOCE", "VOCE",
            "BLDT", "BLDTACTTIME", "STEPBL", "CURR_SECS", "ISFFLX",
            "SF_SFCLAY_PHYSICS", "SF_SURFACE_PHYSICS", "SF_URBAN_PHYSICS",
            "FRACTIONAL_SEAICE",
        )
    },
    "sfclay_pre": {
        **{field: MASS_LEVELS for field in (
            "U_PHYTEMP", "V_PHYTEMP", "T_PHY", "QV_CURR", "P_PHY", "DZ8W",
        )},
        **{field: SCALAR_LEVEL for field in (
            "PSFC", "CHS", "CHS2", "CQS2", "CPM", "ZNT", "UST", "PBLH",
            "MAVAIL", "ZOL", "MOL", "REGIME", "PSIM", "PSIH", "FM", "FHH",
            "XLAND", "HFX", "QFX", "LH", "TSK", "FLHC", "FLQC", "QGH",
            "QSFC", "RMOL", "U10", "V10", "TH2", "T2", "Q2", "GZ1OZ0",
            "WSPD", "BR", "ISFFLX", "DX2D", "LAKEMASK",
        )},
    },
    "sfclay_post": {
        field: SCALAR_LEVEL for field in (
            "UST", "HFX", "QFX", "LH", "TSK", "FLHC", "FLQC", "CHS",
            "CHS2", "CQS2", "QGH", "QSFC", "ZNT", "U10", "V10", "T2", "Q2",
        )
    },
    "noahmp_dispatch_entry": {
        field: SCALAR_LEVEL for field in (
            "FRACTIONAL_SEAICE", "IVGTYP", "ISLTYP", "XLAND", "XICE",
            "ALBEDO", "EMISS", "TSK", "HFX", "LH", "QFX",
        )
    },
    "seaice_adjustment_post": {
        field: SCALAR_LEVEL for field in (
            "FRACTIONAL_SEAICE", "XICE", "XICE_THRESHOLD", "ALBEDO", "EMISS",
            "TSK", "HFX", "LH", "QFX",
        )
    },
    "noahmp_pre": {
        **{field: MASS_LEVELS for field in (
            "T_PHY", "QV_CURR", "U_PHY", "V_PHY", "DZ8W",
        )},
        # P8W is interface pressure (bottom_top_stag), hence 40 values for
        # this 39-layer case. It is kept distinct from mass-level state.
        "P8W": INTERFACE_LEVELS,
        **{field: SOIL_LEVELS for field in ("SMOIS", "SH2O", "TSLB")},
        **{field: SCALAR_LEVEL for field in (
            "ITIMESTEP", "DTBL", "IVGTYP", "ISLTYP", "VEGFRA", "SHDMAX",
            "TMN", "XLAND", "XICE", "XICE_THRESHOLD", "SWDOWN", "SWDDIR",
            "SWDDIF", "GLW", "RAINBL", "SR", "TSK", "HFX", "QFX", "LH",
            "GRDFLX", "SMSTAV", "SMSTOT", "SFCRUNOFF", "UDRUNOFF", "ALBEDO",
            "SNOWC", "SNOW", "SNOWH", "CANWAT", "ACSNOM", "ACSNOW", "EMISS",
            "QSFC", "Z0", "ZNT", "LAI", "SF_URBAN_PHYSICS",
        )},
    },
    "noahmp_post": {
        **{field: SOIL_LEVELS for field in ("SMOIS", "SH2O", "TSLB")},
        **{field: SCALAR_LEVEL for field in (
            "TSK", "HFX", "QFX", "LH", "GRDFLX", "SMSTAV", "SMSTOT",
            "SFCRUNOFF", "UDRUNOFF", "ALBEDO", "SNOWC", "SNOW", "SNOWH",
            "CANWAT", "EMISS", "QSFC", "Z0", "ZNT",
        )},
    },
    "noahmp_urban_pre": {
        field: SCALAR_LEVEL for field in (
            "IVGTYP", "SF_URBAN_PHYSICS", "HFX", "LH", "QFX", "UST",
            "TSK", "ALBEDO", "EMISS", "Z0", "ZNT",
        )
    },
    "noahmp_urban_post": {
        field: SCALAR_LEVEL for field in (
            "HFX", "LH", "QFX", "UST", "TSK", "ALBEDO", "EMISS", "Z0", "ZNT",
        )
    },
    "surface_return": {
        field: SCALAR_LEVEL for field in (
            "HFX", "LH", "QFX", "UST", "TSK", "PBLH", "GRDFLX",
        )
    },
}


def expected_capture_keys(
    arm: str, config: G4SurfaceConfig
) -> set[tuple[str, str, str, int]]:
    if arm not in {"continuous", "restart"}:
        raise SurfaceProbeError(f"unknown comparison arm: {arm}")
    profiles = {name for name, _, _ in PROFILES}
    events = event_schedule(config)
    expected: set[tuple[str, str, str, int]] = set()
    for sample in profiles:
        for event in events:
            for field, levels in EVENT_FIELDS[event].items():
                expected.update((sample, event, field, level) for level in levels)
    return expected


def validate_capture(
    rows: Iterable[CaptureRow], *, arm: str, config: G4SurfaceConfig
) -> dict[tuple[str, str, str, int], str]:
    """Fail closed on incomplete, duplicate, extra, or malformed operand rows."""
    expected = expected_capture_keys(arm, config)
    received: dict[tuple[str, str, str, int], str] = {}
    expected_profiles = {name for name, _, _ in PROFILES}
    profile_coordinates = {name: (j, i) for name, j, i in PROFILES}
    for row in rows:
        if row.arm != arm:
            raise SurfaceProbeError(f"row arm {row.arm!r} does not match {arm!r}")
        key = (row.sample, row.event, row.field, row.level)
        if key in received:
            raise SurfaceProbeError(f"duplicate capture row: {key}")
        if key not in expected:
            raise SurfaceProbeError(f"out-of-plan capture row: {key}")
        if row.sample not in expected_profiles:
            raise SurfaceProbeError(f"unknown selected profile: {row.sample}")
        if (row.j_fortran_1based, row.i_fortran_1based) != profile_coordinates[row.sample]:
            raise SurfaceProbeError(f"profile coordinates do not match selected point: {row.sample}")
        if re.fullmatch(r"[0-9A-F]{8}", row.word) is None:
            raise SurfaceProbeError(f"invalid raw binary32 word for {key}: {row.word!r}")
        received[key] = row.word
    if set(received) != expected:
        raise SurfaceProbeError(
            "capture key universe incomplete; "
            f"missing={sorted(expected-set(received))[:20]}, "
            f"unexpected={sorted(set(received)-expected)[:20]}"
        )
    return received


def classify_pair(
    continuous: Mapping[tuple[str, str, str, int], str],
    restart: Mapping[tuple[str, str, str, int], str],
    *,
    config: G4SurfaceConfig,
) -> dict[str, Any]:
    """Report the earliest observed capture boundary without claiming cause."""
    expected = expected_capture_keys("continuous", config)
    for arm_name, values in (("continuous", continuous), ("restart", restart)):
        if set(values) != expected:
            raise SurfaceProbeError(f"{arm_name} classifier map has incomplete or extra capture keys")
        for key, word in values.items():
            if not isinstance(key, tuple) or len(key) != 4:
                raise SurfaceProbeError(f"malformed classifier key: {key!r}")
            if not isinstance(word, str) or re.fullmatch(r"[0-9A-F]{8}", word) is None:
                raise SurfaceProbeError(f"invalid raw binary32 word for {key}: {word!r}")
    schedule = event_schedule(config)
    mismatches: list[dict[str, Any]] = []
    first_event = None
    for event in schedule:
        event_rows = []
        for key in sorted(continuous):
            sample, key_event, field, level = key
            if key_event == event and continuous[key] != restart[key]:
                event_rows.append({
                    "sample": sample,
                    "j_fortran_1based": next(j for name, j, _ in PROFILES if name == sample),
                    "i_fortran_1based": next(i for name, _, i in PROFILES if name == sample),
                    "field": field,
                    "level": level,
                    "continuous_word": continuous[key],
                    "restart_word": restart[key],
                })
        if event_rows:
            first_event = event
            mismatches = event_rows
            break
    if first_event is None:
        return {
            "raw_word_equal": True,
            "first_differing_event": None,
            "classification": "no_difference_in_declared_capture",
            "cause_established": False,
        }
    if first_event.endswith("_pre") or first_event in {
        "surface_call_pre", "noahmp_dispatch_entry",
    }:
        classification = "input_or_state_operand_difference"
    elif first_event.endswith("_post") or first_event == "surface_return":
        classification = "producer_output_or_unobserved_dependency_difference"
    else:
        classification = "boundary_difference_requires_review"
    return {
        "raw_word_equal": False,
        "first_differing_event": first_event,
        "classification": classification,
        "cause_established": False,
        "scope": "five input-selected G4 profiles and declared operand subset",
        "mismatches": mismatches,
    }


def g4_source_plan() -> dict[str, Any]:
    """Portable description; private sources are not copied into this repo."""
    return {
        "schema": "g4-surface-handoff-plan-v1",
        "status": "plan_only_no_native_capture",
        "source_pins": dict(SOURCE_PINS),
        "source_paths_root_relative": dict(SOURCE_PATHS),
        "anchors": {
            module: {
                anchor_name: {"text": anchor, "expected_count": count}
                for anchor_name, (anchor, count) in module_anchors.items()
            }
            for module, module_anchors in SOURCE_ANCHORS.items()
        },
        "event_source_selection": {
            "surface_call_pre": "module_first_rk_step_part1.F before surface_driver call",
            "sfclay_pre_post": {
                "fractional_seaice_0": ["surface_driver.F sfclay_call", "surface_driver.F sfclay_call_return"],
                "fractional_seaice_1": ["surface_driver.F sfclay_seaice_call", "surface_driver.F sfclay_seaice_call_return"],
            },
            "noahmp_dispatch_entry": "surface_driver.F NOAHMPSCHEME case entry before the fractional-ice conversion",
            "seaice_adjustment_post": "surface_driver.F after the conditional Noah-MP sea-ice input conversion",
            "noahmp_pre_post": ["surface_driver.F noahmp_call", "surface_driver.F noahmp_call_return"],
            "noahmp_urban_pre_post": ["surface_driver.F noahmp_urban_call", "surface_driver.F noahmp_urban_call_return"],
            "surface_return": "module_first_rk_step_part1.F after surface_driver call",
        },
        "selected_profiles": [
            {"name": name, "j_fortran_1based": j, "i_fortran_1based": i}
            for name, j, i in PROFILES
        ],
        "profile_branch_activity": {
            "status": "not_observed_by_this_plan",
            "claim_limit": "No per-profile urban or sea-ice branch-active outcome is asserted; native capture must record these outcomes before profile-specific branch coverage can be claimed.",
            "profiles": {
                name: {
                    "urban_branch_active": None,
                    "seaice_adjustment_branch_active": None,
                }
                for name, _, _ in PROFILES
            },
        },
        "retained_input_sha256": "5a9ae8da992028dbf3a2a7652eb61532c1efab2acea7ea0e393e4cac8fd4c970",
        "observed_surface_classes": {
            "clear": {"XLAND": 2.0, "IVGTYP": 17, "VEGFRA": 0.0},
            "warm_liquid": {"XLAND": 1.0, "IVGTYP": 12, "VEGFRA": 60.35637283325195},
            "mixed": {"XLAND": 1.0, "IVGTYP": 12, "VEGFRA": 62.852149963378906},
            "ice": {"XLAND": 2.0, "IVGTYP": 17, "VEGFRA": 0.0},
            "rain": {"XLAND": 2.0, "IVGTYP": 17, "VEGFRA": 0.0},
        },
        "retained_namelist_switches": {
            "sf_sfclay_physics": 1,
            "sf_surface_physics": 2,
            "sf_urban_physics": 1,
            "isfflx": 1,
            "bldt_minutes": 0,
            "adaptive_timestep": False,
            "fractional_seaice": 0,
        },
        "fractional_seaice_observation": {
            "status": "local_run_artifact_verified",
            "value": 0,
            "source": "WRF-generated namelist.output in each run_ss_case working directory, line 1496",
            "portable_run_receipt_path": "harness/evidence/g4_restart_shadow_runs_2026-09-25.json",
            "runs": {
                "continuous": {
                    "run_id": "mp237_g4-s6-continuous_0min40s_hist0_1x1_20260925_175103_p81169",
                    "campaign_id": "e1fe6e30e3ea27fa95ab40add6204580e0d9738ebbdc29a3f8360eb5fcf3b8f3",
                    "started_utc": "2026-09-25T08:51:03Z",
                    "finished_utc": "2026-09-25T08:52:02Z",
                    "base_namelist_input_sha256_before_after": "db3938789305aee81a65eef1a906df5d88ff3cc13d6c30cca472eef604d00755",
                    "effective_run_namelist_sha256": "eb9328308e03553f1e24700d19e9d1d91c7b7b042039938e91cd4a0062242948",
                    "input_identity_sha256": "12e132ecefa9e0f7e0a0bd67d57353ec3a7ec113ab1b43121474340293125fdf",
                    "run_identity_sha256": "935c04384fbbd0c100203142d90c46362726a97747b9ce1e6852f413d4946780",
                    "input_sha256_json_sha256": "d53940dc621f368cf1ce4ae4a770def8598dfa912cef48e412b6316b60800017",
                    "experiment_valid_sha256": "e824ff6bdda31c666e5a5c5b161258dbfc94f46cd0fc8d65f2f2e04980ba205b",
                    "wrf_executable_sha256": "3197df4dcdcf9c1af4132e15662531bc28be4c61892fac54cf7a015311c24140",
                    "runner_sha256": "175ade71058672b957d565ef88ffd7925bc7d74dfe559c36aaec61fa8de0d96e",
                    "namelist_output_path": "graphify-out/s6-g4-relink/case-continuous/namelist.output",
                    "namelist_output_sha256": "e1d3654124ec150515dcc7341509ac8d4cc892d4338236cd408e5ae9e7ad0a50",
                    "namelist_output_size_bytes": 89987,
                    "namelist_output_birth_utc": "2026-09-25T08:51:05.131477Z",
                    "namelist_output_mtime_utc": "2026-09-25T08:51:05.136371Z",
                    "stdout_sha256": "1436a6db28418193df4284b9053b9c954343fd5b90dda1e6ab25a6423ffd58df",
                    "stdout_birth_utc": "2026-09-25T08:51:03.754749Z",
                    "stdout_mtime_utc": "2026-09-25T08:51:05.130494Z"
                },
                "restart": {
                    "run_id": "mp237_g4-s6-restart_0min20s_hist0_1x1_20260925_175316_p86644",
                    "campaign_id": "0482f049ac6dbbfc17bea8272a2ffedfbedf7c28d8e9f91fbb619eacb0617963",
                    "started_utc": "2026-09-25T08:53:16Z",
                    "finished_utc": "2026-09-25T08:53:30Z",
                    "base_namelist_input_sha256_before_after": "b1749c4ed14883783452b85dff0979a73892fb5764797d65f055807f69675a19",
                    "effective_run_namelist_sha256": "a670c0bba108916a2eaad34a90071ecb5368f4a0766102a1f4a7eaf7910f7a9c",
                    "input_identity_sha256": "1b3585d0492d0c158017f7dbc4aa0700c61c8e5b992c742681f9d1c5a5f50152",
                    "run_identity_sha256": "6058cf76b3bffe5461b17b8dfa8744ec2a4354abfbf99e763f8045e696280fb7",
                    "input_sha256_json_sha256": "16a47ebdcae4b59f4b17b69c38e7393f23c928a9a1ab906ba67d6c93cbd85ddc",
                    "experiment_valid_sha256": "e824ff6bdda31c666e5a5c5b161258dbfc94f46cd0fc8d65f2f2e04980ba205b",
                    "wrf_executable_sha256": "3197df4dcdcf9c1af4132e15662531bc28be4c61892fac54cf7a015311c24140",
                    "runner_sha256": "175ade71058672b957d565ef88ffd7925bc7d74dfe559c36aaec61fa8de0d96e",
                    "namelist_output_path": "graphify-out/s6-g4-relink/case-restart/namelist.output",
                    "namelist_output_sha256": "be495c496fde053dd4cb445a1b5476589ab1828deaec7e6af83f7ecc34408bcd",
                    "namelist_output_size_bytes": 89999,
                    "namelist_output_birth_utc": "2026-09-25T08:53:17.356787Z",
                    "namelist_output_mtime_utc": "2026-09-25T08:53:17.361497Z",
                    "stdout_sha256": "1436a6db28418193df4284b9053b9c954343fd5b90dda1e6ab25a6423ffd58df",
                    "stdout_birth_utc": "2026-09-25T08:53:17.101442Z",
                    "stdout_mtime_utc": "2026-09-25T08:53:17.355966Z"
                }
            },
            "provenance_limit": (
                "run_ss_case launches with cwd=case directory but does not clean, hash, "
                "or archive namelist.output. Birth/mtime fall inside each recorded run. "
                "Relative to stdout mtime, output birth is "
                "0.983 ms (continuous) and 0.821 ms (restart) later; output mtime is "
                "5.877 ms and 5.531 ms later, respectively. These local "
                "filesystem facts support attribution but are not cryptographically "
                "bound by the portable run receipt. Instrumented reruns must preserve "
                "and hash their own namelist.output."
            )
        },
        "configured_event_schedule": list(event_schedule(G4SurfaceConfig(
            timestep=2,
            sf_sfclay_physics=1,
            sf_surface_physics=2,
            sf_urban_physics=1,
            isfflx=1,
            bldt_minutes=0,
            adaptive_timestep=False,
            fractional_seaice=0,
        ))),
        "capture_schedule_ready": True,
        "schedule_blocker": None,
        "schedule_caveat": (
            "The retained-run schedule uses the locally verified fractional_seaice=0. "
            "An instrumented rerun must independently record and match 0 before its "
            "capture can be validated."
        ),
        "operand_contract": {
            event: {field: list(levels) for field, levels in fields.items()}
            for event, fields in EVENT_FIELDS.items()
        },
        "fixed_event_plan_requires_explicit": ["fractional_seaice"],
        "noninterference_gate": (
            "Run the same event-dump executable once with its dump switch off and "
            "once on; require retained-history raw-bit identity before interpreting traces."
        ),
        "classification_limit": (
            "Capture fields are a selected diagnostic operand subset, not proof that "
            "all active callee reads or module state have been observed. Any reported "
            "producer boundary is a candidate; cause_established always remains false."
        ),
        "evidence_boundary": (
            "Current live private-source pins do not by themselves prove those exact "
            "sources produced the retained G4 executable; verify source/object identity "
            "before any causal interpretation."
        ),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(g4_source_plan(), indent=2, sort_keys=True))
