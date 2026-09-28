from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
import s15_face_cause_probe as replay
import s15_face_fortran_overlay as overlay
from test_s15_face_cause_probe import _synthetic


ROOT = Path(__file__).resolve().parents[2]
CONFIG = {"rk_order": 3, "adv_opt": "POSITIVEDEF"}


def _raw_stream() -> str:
    producers, consumers = _synthetic()
    coordinates = replay._projection(ROOT)
    rows: list[str] = []
    for slot, (producer, coordinate) in enumerate(zip(producers, coordinates)):
        identity = [
            producer["step"],
            producer["rk"],
            producer["owner"],
            slot % 2 + 1,
            producer["tile_i0"],
            producer["tile_i1"],
            producer["tile_j0"],
            producer["tile_j1"],
            *coordinate,
        ]
        branch_id = 2 if producer["branch"] == "positive_definite" else 1
        order = producer["tendency_order"]
        before = producer["initial_tendency"]
        for axis in order:
            part = producer["axes"][axis]
            faces = part["face_fluxes"]
            low = (
                producer["pd_low_order_fluxes"][axis]
                if branch_id == 2
                else {"minus": "00000000", "plus": "00000000"}
            )
            words = [
                faces["minus"],
                faces["plus"],
                low["minus"],
                low["plus"],
                part["metric_factor"],
                part["inverse_spacing"],
                before,
                part["tendency_prefix"],
            ]
            axis_id = {"y": 1, "x": 2, "z": 3}[axis]
            rows.append(
                "S15AX " + " ".join(map(str, identity + [axis_id, branch_id] + words))
            )
            before = part["tendency_prefix"]
        if branch_id == 2:
            low = producer["pd_low_order_fluxes"]
            pre = producer["pd_unlimited_high_order_fluxes"]
            post = producer["pd_high_order_fluxes"]
            words = [
                producer["pd_flux_out"],
                producer["pd_available_state"],
                overlay.PD_EPS_F32,
                "00000000",
                *[low[a][s] for a in ("x", "y", "z") for s in ("minus", "plus")],
                *[pre[a][s] for a in ("x", "y", "z") for s in ("minus", "plus")],
                *[post[a][s] for a in ("x", "y", "z") for s in ("minus", "plus")],
            ]
            rows.append("S15PD " + " ".join(map(str, identity + [0] + words)))

    for slot, (consumer, coordinate) in enumerate(zip(consumers, coordinates)):
        identity = [
            consumer["step"],
            consumer["rk"],
            consumer["owner"],
            slot % 2 + 1,
            consumer["tile_i0"],
            consumer["tile_i1"],
            consumer["tile_j0"],
            consumer["tile_j1"],
            *coordinate,
        ]
        words = [
            consumer["advect_tend"],
            consumer["msfty"],
            consumer["sc_tend"],
            consumer["tendency"],
            consumer["before"],
            consumer["dt"],
            consumer["c1"],
            consumer["c2"],
            consumer["muold"],
            consumer["munew"],
            consumer["after"],
        ]
        rows.append("S15RK " + " ".join(map(str, identity + words)))

    return "\n".join(rows) + "\n"


def _neighbor_stream() -> str:
    rows = _raw_stream().splitlines()
    coordinates = replay._projection(ROOT)
    for tile, coordinate in replay.NEIGHBOR_RECEIVERS:
        donor = coordinates[4 if tile == 1 else 5]
        for raw in tuple(rows):
            parts = raw.split()
            if (
                parts[0] not in {"S15AX", "S15PD", "S15RK"}
                or parts[1:5] != ["2", "3", "5", str(tile)]
                or tuple(map(int, parts[9:12])) != donor
            ):
                continue
            parts[9:12] = list(map(str, coordinate))
            if parts[0] == "S15RK":
                parts[14] = "3F800000"  # synthetic positive source tendency
                parts[15] = replay._add(replay._mul(parts[12], parts[13]), parts[14])
                parts[16] = "00000000"
                old_mass = replay._fma32(parts[18], parts[20], parts[19])
                dt_tendency = replay._mul(parts[17], parts[15])
                numerator = replay._fma32(old_mass, parts[16], dt_tendency)
                new_mass = replay._fma32(parts[18], parts[21], parts[19])
                parts[22] = replay.value_word(
                    replay.word_value(numerator) / replay.word_value(new_mass)
                )
                assert replay.word_value(parts[22]) > 0.0
            rows.append(" ".join(parts))
    return "\n".join(rows) + "\n"


def _qn_stream() -> str:
    rows = _raw_stream().splitlines()
    donor = replay._projection(ROOT)[4]
    selected = []
    for raw in rows:
        parts = raw.split()
        if (
            parts[0] not in {"S15AX", "S15PD", "S15RK"}
            or parts[1:5] != ["2", "3", "5", "1"]
            or tuple(map(int, parts[9:12])) != donor
        ):
            continue
        selected.append(parts)
    assert len(selected) == 5  # Z/X/Y, one PD limiter, one RK store.
    result = []
    for coordinate in (replay.QN_DONOR, *replay.QN_RECEIVERS):
        for raw_parts in selected:
            parts = raw_parts.copy()
            parts[0] = {"S15AX": "S3QNAX", "S15PD": "S3QNPD", "S15RK": "S3QNRK"}[
                parts[0]
            ]
            parts[1:12] = [2, 3, 3, 1, 1, 235, 1, 142, *coordinate]
            if parts[0] == "S3QNRK" and coordinate != replay.QN_DONOR:
                parts[14] = "41000000"  # positive synthetic sc_tend for receivers
                parts[15] = replay._add(replay._mul(parts[12], parts[13]), parts[14])
                parts[16] = "00000000"
                old_mass = replay._fma32(parts[18], parts[20], parts[19])
                dt_tendency = replay._mul(parts[17], parts[15])
                numerator = replay._fma32(old_mass, parts[16], dt_tendency)
                new_mass = replay._fma32(parts[18], parts[21], parts[19])
                parts[22] = replay.value_word(
                    replay.word_value(numerator) / replay.word_value(new_mass)
                )
                assert replay.word_value(parts[22]) > 0.0
            result.append(" ".join(map(str, parts)))
    return "\n".join(result) + "\n"


def test_source_pins_and_both_owner_call_anchors_are_independent() -> None:
    assert overlay.SOURCE_PINS == {
        "dyn_em/solve_em.F": "d66e9db1bba8f37e3f46d30c2fd74bdf8def411adf233376a69e0b401c6d3d1f",
        "dyn_em/module_em.F": "7695bfb05a7f99763334a6e69523bbcc1de0f2c659177a18c10a6e1cf530a0c7",
        "dyn_em/module_advect_em.F": "58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d",
    }
    assert overlay.PRODUCER_ANCHOR == ("scalar_tile_loop_1", "rk_scalar_tend")
    assert overlay.CONSUMER_ANCHOR == ("scalar_tile_loop_2", "rk_update_scalar")
    source = """SUBROUTINE solve_em()
IMPLICIT NONE
other_scalar_advance: IF (num_3d_s >= 1) THEN
scalar_tile_loop_1: DO ij=1,n
 CALL rk_scalar_tend(x)
ENDDO scalar_tile_loop_1
scalar_tile_loop_2: DO ij=1,n
 CALL rk_update_scalar(x)
ENDDO scalar_tile_loop_2
END IF
END SUBROUTINE solve_em
"""
    anchors = overlay.find_dual_owner_calls(source)
    assert anchors["producer"] != anchors["consumer"]
    patched = overlay._patch_solve(source)
    assert patched.count("s15_step=grid%itimestep") == 2
    assert (
        patched.count("s15_owner=MERGE(5,0,is==P_QIB .and. s15_capture_enabled)") == 2
    )
    assert patched.count("GET_ENVIRONMENT_VARIABLE('KDM6_S15_NATIVE_CAPTURE_LOG'") == 1
    assert overlay.strip_capture_macro(patched) == source
    with pytest.raises(overlay.OverlayError, match="rk_scalar_tend call"):
        overlay.find_dual_owner_calls(
            source.replace("CALL rk_scalar_tend(x)", "CALL other_tend(x)")
        )


def test_fortran_emitters_enforce_the_26_event_family_caps() -> None:
    em_helpers = "\n".join(overlay._append_module_em_helpers(["END MODULE module_em"]))
    advect_helpers = "\n".join(
        overlay._append_advect_helpers(["END MODULE module_advect_em"])
    )
    assert "if (s15_count.ge.6) then" in em_helpers
    assert "S15LIMIT S15RK event cap exceeded" in em_helpers
    assert "if (s15_count.ge.18) then" in advect_helpers
    assert "S15LIMIT S15AX event cap exceeded" in advect_helpers
    assert "if (s15_count.ge.2) then" in advect_helpers
    assert "S15LIMIT S15PD event cap exceeded" in advect_helpers
    em_neighbor_helpers = "\n".join(
        overlay._append_module_em_helpers(["END MODULE module_em"], neighbors=True)
    )
    advect_neighbor_helpers = "\n".join(
        overlay._append_advect_helpers(["END MODULE module_advect_em"], neighbors=True)
    )
    assert "if (s15_count.ge.14) then" in em_neighbor_helpers
    assert "if (s15_count.ge.42) then" in advect_neighbor_helpers
    assert "if (s15_count.ge.10) then" in advect_neighbor_helpers
    assert (
        "tile.eq.1 .and. i.eq.141 .and. j.eq.142 .and. k.eq.16) hit=.true."
        in advect_neighbor_helpers
    )


def test_qn_overlay_has_separate_p_qnc_owner_roster_and_exact_caps() -> None:
    solve = overlay._convert_qn_overlay(
        overlay._patch_solve(
            """SUBROUTINE solve_em()\nIMPLICIT NONE\nother_scalar_advance: IF (num_3d_s >= 1) THEN\nscalar_tile_loop_1: DO ij=1,n\n CALL rk_scalar_tend(x)\nENDDO scalar_tile_loop_1\nscalar_tile_loop_2: DO ij=1,n\n CALL rk_update_scalar(x)\nENDDO scalar_tile_loop_2\nEND IF\nEND SUBROUTINE solve_em\n"""
        )
    )
    em_helpers = overlay._convert_qn_overlay(
        "\n".join(
            overlay._append_module_em_helpers(["END MODULE module_em"], neighbors=True)
        )
    )
    advect_helpers = overlay._convert_qn_overlay(
        "\n".join(
            overlay._append_advect_helpers(
                ["END MODULE module_advect_em"], neighbors=True
            )
        )
    )
    assert solve.count("s15_owner=MERGE(3,0,is==P_QNC .and. s15_capture_enabled)") == 2
    assert "P_QIB" not in solve and "P_QIB" not in em_helpers + advect_helpers
    assert "owner.ne.3" in em_helpers + advect_helpers
    assert "S3QNAX" in advect_helpers and "S3QNPD" in advect_helpers
    assert "S3QNRK" in em_helpers
    assert "if (s15_count.ge.15) then" in advect_helpers
    assert advect_helpers.count("if (s15_count.ge.5) then") == 1
    assert "if (s15_count.ge.5) then" in em_helpers
    assert "i.eq.234" not in advect_helpers + em_helpers


def test_qn_xr_shadow_uses_independent_physics_latch_and_pre_tap_factor() -> None:
    solve_source = """SUBROUTINE solve_em()
IMPLICIT NONE
other_scalar_advance: IF (num_3d_s >= 1) THEN
scalar_tile_loop_1: DO ij=1,n
 CALL rk_scalar_tend(x)
ENDDO scalar_tile_loop_1
scalar_tile_loop_2: DO ij=1,n
 CALL rk_update_scalar(x)
ENDDO scalar_tile_loop_2
END IF
END SUBROUTINE solve_em
"""
    solve = overlay._convert_qn_overlay(overlay._patch_solve(solve_source, shadow=True))
    gate = "s3qn_xr_shadow_enabled=(is==P_QNC.and.grid%itimestep.eq.2.and.rk_step.eq.3.and.ij.eq.1.and.s3qn_xr_shadow_latched)"
    assert "KDM6_S3_QN_XR_SHADOW" in solve
    assert "trim(s3qn_xr_shadow_env).eq.'1'" in solve
    assert gate in solve
    assert "s15_owner=MERGE(3,0,is==P_QNC .and. s15_capture_enabled)" in solve
    assert "s15_capture_enabled" not in gate
    declarations = "\n".join(
        overlay._add_optional_declarations(
            ["SUBROUTINE sample()", "IMPLICIT NONE", "END SUBROUTINE sample"],
            "sample",
            ("s3qn_xr_shadow_enabled",),
            declaration_type="LOGICAL",
        )
    )
    assert "LOGICAL, OPTIONAL, INTENT(IN) :: s3qn_xr_shadow_enabled" in declarations

    pd_source = """SUBROUTINE advect_scalar_pd()
IMPLICIT NONE
IF( flux_out(i,k,j) .gt. ph_low(i,k,j)) THEN
 scale = max(0.,ph_low(i,k,j)/(flux_out(i,k,j)+eps))
END IF
END SUBROUTINE advect_scalar_pd
"""
    tapped = "\n".join(overlay._tap_pd_limiter(pd_source.splitlines(), shadow=True))
    assert "0.9999784827232361*fqx(i+1,k,j)" in tapped
    assert "transfer(fqx(i+1,k,j),0).ne.int(z'502AB870',kind=4)" in tapped
    assert tapped.index("s3qn_xr_shadow_enabled .and. i.eq.233") < tapped.index(
        "s15_pd_post(2)=fqx(i+1,k,j)"
    )
    assert tapped.count("fqx(i+1,k,j)=0.9999784827232361*fqx(i+1,k,j)") == 1
    assert replay.value_word(float(overlay.QN_XR_SHADOW_FACTOR_LITERAL)) == (
        overlay.QN_XR_SHADOW_FACTOR_WORD
    )


def test_synthetic_qn_stream_joins_exact_five_with_only_donor_transition() -> None:
    stream = _qn_stream()
    producers, consumers = overlay.parse_fortran_capture(stream, ROOT, CONFIG, qn=True)
    assert len(producers) == len(consumers) == 5
    expected = {
        (*replay.QN_SCHEDULE, *coord)
        for coord in (replay.QN_DONOR, *replay.QN_RECEIVERS)
    }
    assert {replay._identity(row) for row in producers} == expected
    after = {replay._identity(row): row["after"] for row in consumers}
    donor_key = (*replay.QN_SCHEDULE, *replay.QN_DONOR)
    assert replay.word_value(after[donor_key]) < 0.0
    assert all(
        replay.word_value(value) > 0.0
        for key, value in after.items()
        if key != donor_key
    )
    with pytest.raises(overlay.OverlayError, match="exactly 5 producer keys"):
        overlay.parse_fortran_capture(
            stream.rsplit("\n", 2)[0] + "\n", ROOT, CONFIG, qn=True
        )


def test_qn_shadow_replays_factorized_xr_and_positive_store_from_native_stream() -> (
    None
):
    rows = (
        (ROOT / "harness/evidence/S3_QN_face_neighbors_run1/S3QN_face.stream")
        .read_text(encoding="ascii")
        .splitlines()
    )
    donor_identity = [2, 3, 3, 1, 1, 235, 1, 142, *replay.QN_DONOR]
    pd_index = next(
        index
        for index, row in enumerate(rows)
        if row.startswith("S3QNPD ")
        and list(map(int, row.split()[1:12])) == donor_identity
    )
    pd = rows[pd_index].split()
    assert pd[30] == replay.QN_XR_SHADOW_INPUT_WORD
    pd[30] = replay._mul(replay.QN_XR_SHADOW_FACTOR_WORD, pd[30])
    assert pd[30] == "502AB77F"
    rows[pd_index] = " ".join(pd)

    x_index = next(
        index
        for index, row in enumerate(rows)
        if row.startswith("S3QNAX ")
        and list(map(int, row.split()[1:12])) == donor_identity
        and row.split()[12] == "2"
    )
    x = rows[x_index].split()
    x[15] = pd[30]
    x_difference = replay._sub(replay._add(replay._sub(x[15], x[14]), x[17]), x[16])
    x_scaled = replay._mul(x[19], x_difference)
    x_prefix = replay._fma32(replay._negate_word(x[18]), x_scaled, x[20])
    x[21] = x_prefix
    rows[x_index] = " ".join(x)

    y_index = next(
        index
        for index, row in enumerate(rows)
        if row.startswith("S3QNAX ")
        and list(map(int, row.split()[1:12])) == donor_identity
        and row.split()[12] == "1"
    )
    y = rows[y_index].split()
    y[20] = x_prefix
    y_difference = replay._sub(replay._add(replay._sub(y[15], y[14]), y[17]), y[16])
    y_scaled = replay._mul(y[19], y_difference)
    advect_tend = replay._fma32(replay._negate_word(y[18]), y_scaled, y[20])
    y[21] = advect_tend
    rows[y_index] = " ".join(y)

    rk_index = next(
        index
        for index, row in enumerate(rows)
        if row.startswith("S3QNRK ")
        and list(map(int, row.split()[1:12])) == donor_identity
    )
    rk = rows[rk_index].split()
    rk[12] = advect_tend
    rk[15] = replay._add(replay._mul(rk[12], rk[13]), rk[14])
    old_mass = replay._fma32(rk[18], rk[20], rk[19])
    numerator = replay._fma32(old_mass, rk[16], replay._mul(rk[17], rk[15]))
    new_mass = replay._fma32(rk[18], rk[21], rk[19])
    rk[22] = replay.value_word(
        replay.word_value(numerator) / replay.word_value(new_mass)
    )
    assert rk[22] == "3C3263AA"
    rows[rk_index] = " ".join(rk)
    native_shadow_stream = "\n".join(rows) + "\n"

    producers, consumers = overlay.parse_fortran_capture(
        native_shadow_stream, ROOT, CONFIG, qn=True, shadow=True
    )
    assert len(producers) == len(consumers) == 5
    parsed_donor = next(
        row for row in consumers if replay._identity(row)[-3:] == replay.QN_DONOR
    )
    assert parsed_donor["after"] == "3C3263AA"
    with pytest.raises(replay.ProbeError, match="PD x.plus local post-limit face"):
        overlay.parse_fortran_capture(native_shadow_stream, ROOT, CONFIG, qn=True)


def test_wrf_final_suffix_cpp_pass_uses_only_cpp_base_and_tradflag() -> None:
    argv = overlay.wrf_suffix_final_cpp_argv("cpp-15", "module_mp_kdm6.H")
    assert argv == [
        "cpp-15",
        "-P",
        "-nostdinc",
        "-xassembler-with-cpp",
        "-traditional-cpp",
        "module_mp_kdm6.H",
    ]
    assert "-I" not in argv
    assert not any(arg.startswith("-D") for arg in argv)
    assert overlay.MACRO not in argv


def test_macro_off_call_rewrite_preserves_the_original_closing_line() -> None:
    original = "                                  kts=k_start, kte=k_end )"
    guarded = overlay._wrap_closing_line(
        original,
        ["s15_step=grid%itimestep", "s15_rk=rk_step", "s15_owner=5", "s15_tile=ij"],
    )
    assert overlay.strip_capture_macro("\n".join(guarded)) == original + "\n"


def test_synthetic_s15_records_parse_and_join_to_the_six_pinned_slots() -> None:
    stream = _raw_stream()
    producers, consumers = overlay.parse_fortran_capture(stream, ROOT, CONFIG)
    assert len(producers) == len(consumers) == 6
    assert producers[4]["pd_limiter_active"] is False
    assert producers[4]["tendency_order"] == ["z", "x", "y"]

    rows = stream.splitlines()
    pd_index = next(i for i, row in enumerate(rows) if row.startswith("S15PD "))
    bad_scale = rows.copy()
    pd_words = bad_scale[pd_index].split()
    pd_words[16] = "3F000000"
    bad_scale[pd_index] = " ".join(pd_words)
    with pytest.raises(overlay.OverlayError, match="inactive PD limiter.*zero scale"):
        overlay.parse_fortran_capture("\n".join(bad_scale) + "\n", ROOT, CONFIG)

    bad_eps = rows.copy()
    pd_words = bad_eps[pd_index].split()
    pd_words[15] = "00000000"
    bad_eps[pd_index] = " ".join(pd_words)
    with pytest.raises(overlay.OverlayError, match="epsilon differs"):
        overlay.parse_fortran_capture("\n".join(bad_eps) + "\n", ROOT, CONFIG)

    nontransition = rows.copy()
    rk_index = next(i for i, row in enumerate(rows) if row.startswith("S15RK "))
    rk_words = nontransition[rk_index].split()
    rk_words[14] = "40C00000"  # scaled advection -6 plus sc_tend +6 -> tendency 0
    rk_words[15] = "00000000"
    rk_words[16] = "3F800000"
    rk_words[17] = "00000000"
    rk_words[22] = "3F800000"
    nontransition[rk_index] = " ".join(rk_words)
    with pytest.raises(overlay.OverlayError, match="nonnegative-to-negative"):
        overlay.parse_fortran_capture("\n".join(nontransition) + "\n", ROOT, CONFIG)


def test_synthetic_neighbor_mode_validates_six_targets_and_eight_receivers() -> None:
    assert replay.NEIGHBOR_RECEIVERS == (
        (1, (140, 2, 17)),
        (1, (142, 2, 17)),
        (1, (141, 2, 16)),
        (1, (141, 142, 16)),
        (2, (140, 143, 16)),
        (2, (142, 143, 16)),
        (2, (141, 144, 16)),
        (2, (141, 143, 17)),
    )
    stream = _neighbor_stream()
    producers, consumers = overlay.parse_fortran_capture(
        stream, ROOT, CONFIG, neighbors=True
    )
    assert len(producers) == len(consumers) == 14
    coordinates = replay._projection(ROOT)
    target_keys = {
        (*schedule, *coordinate)
        for schedule, coordinate in zip(replay.SCHEDULE, coordinates)
    }
    receiver_keys = {
        (*replay.NEIGHBOR_SCHEDULE_BY_TILE[tile], *coordinate)
        for tile, coordinate in replay.NEIGHBOR_RECEIVERS
    }
    assert target_keys.isdisjoint(receiver_keys)
    assert {replay._identity(row) for row in producers} == target_keys | receiver_keys
    receiver_after = {
        replay._identity(row): row["after"]
        for row in consumers
        if replay._identity(row) in receiver_keys
    }
    assert len(receiver_after) == 8
    assert any(replay.word_value(word) > 0.0 for word in receiver_after.values())

    with pytest.raises(overlay.OverlayError, match="six-slot schedule"):
        overlay.parse_fortran_capture(stream, ROOT, CONFIG)

    rows = stream.splitlines()
    missing_receiver = next(
        i
        for i, row in enumerate(rows)
        if row.startswith("S15RK ")
        and tuple(map(int, row.split()[9:12])) == replay.NEIGHBOR_RECEIVERS[0][1]
    )
    del rows[missing_receiver]
    with pytest.raises(overlay.OverlayError, match="exactly 14 producer keys"):
        overlay.parse_fortran_capture(
            "\n".join(rows) + "\n", ROOT, CONFIG, neighbors=True
        )


def test_pd_incoming_shared_face_may_change_before_divergence_tap() -> None:
    rows = _raw_stream().splitlines()
    pd_index = next(
        i
        for i, row in enumerate(rows)
        if row.startswith("S15PD ") and row.split()[1:5] == ["2", "3", "5", "1"]
    )
    pd = rows[pd_index].split()
    pd[26] = "BF800000"  # selected cell's local pre-limiter Y-plus face
    pd[32] = "BF800000"  # unchanged at that cell; neighbor owns this inflow
    rows[pd_index] = " ".join(pd)

    y_axis_index = next(
        i
        for i, row in enumerate(rows)
        if row.startswith("S15AX ")
        and row.split()[1:5] == ["2", "3", "5", "1"]
        and row.split()[12] == "1"
    )
    y_axis = rows[y_axis_index].split()
    y_axis[15] = "BF400000"  # final divergence face after neighboring limiter
    y_axis[18] = "00000000"  # synthetic zero metric isolates the face ownership
    rows[y_axis_index] = " ".join(y_axis)

    producers, consumers = overlay.parse_fortran_capture(
        "\n".join(rows) + "\n", ROOT, CONFIG
    )
    assert len(producers) == len(consumers) == 6


def _bounded_extractor_fixture(*, neighbors: bool = False) -> bytes:
    counts = (
        overlay.EXPECTED_NEIGHBOR_FACE_TAG_COUNTS
        if neighbors
        else overlay.EXPECTED_FACE_TAG_COUNTS
    )
    return (
        b"WRF banner\nS15Q legacy\n"
        + b"S15AX axis\n" * counts["S15AX"]
        + b"S15PD limiter\n" * counts["S15PD"]
        + b"S15RK consumer\n" * counts["S15RK"]
    )


def test_dual_stream_extractor_preserves_legacy_and_face_lines(tmp_path: Path) -> None:
    full = tmp_path / "rank0.stdout"
    face = tmp_path / "face.records"
    legacy = tmp_path / "legacy.records"
    raw = _bounded_extractor_fixture()
    full.write_bytes(raw)
    receipt = overlay.extract_s15_streams(full, face, legacy)
    assert (
        face.read_bytes()
        == b"S15AX axis\n" * 18 + b"S15PD limiter\n" * 2 + b"S15RK consumer\n" * 6
    )
    assert legacy.read_bytes() == b"S15Q legacy\n"
    assert (
        receipt["full_stdout_sha256"] == hashlib.sha256(full.read_bytes()).hexdigest()
    )
    assert receipt["tag_counts"]["S15AX"] == 18
    with pytest.raises(overlay.OverlayError, match="destinations must be new"):
        overlay.extract_s15_streams(full, face, tmp_path / "legacy-new")


def test_qn_dual_stream_extractor_requires_exact_s3qn_counts(tmp_path: Path) -> None:
    full = tmp_path / "rank0.stdout"
    face = tmp_path / "qn-face.records"
    legacy = tmp_path / "legacy.records"
    raw = (
        b"WRF banner\nS15Q legacy\n"
        + b"S3QNAX axis\n" * 15
        + b"S3QNPD limiter\n" * 5
        + b"S3QNRK consumer\n" * 5
    )
    full.write_bytes(raw)
    receipt = overlay.extract_s15_streams(full, face, legacy, qn=True)
    assert receipt["schema"] == "KDM6AD-S3-QNCLOUD-DUAL-STREAM-EXTRACTION-v1"
    assert receipt["capture_mode"] == "S3_QNCLOUD_OWNER3"
    assert receipt["tag_counts"] == {
        "S3QNAX": 15,
        "S3QNPD": 5,
        "S3QNRK": 5,
        "S15Q": 1,
        "S15QC": 0,
        "S15M": 0,
    }
    assert face.read_bytes() == (
        b"S3QNAX axis\n" * 15 + b"S3QNPD limiter\n" * 5 + b"S3QNRK consumer\n" * 5
    )
    assert legacy.read_bytes() == b"S15Q legacy\n"

    mixed = tmp_path / "mixed.stdout"
    mixed_face = tmp_path / "mixed-face.records"
    mixed_legacy = tmp_path / "mixed-legacy.records"
    mixed.write_bytes(raw + b"S15AX wrong mode\n")
    with pytest.raises(overlay.OverlayError, match="unexpected S15 tap in QNCLOUD"):
        overlay.extract_s15_streams(mixed, mixed_face, mixed_legacy, qn=True)
    assert not mixed_face.exists()
    assert not mixed_legacy.exists()


def test_dual_stream_extractor_rejects_unknown_s15_tag_without_outputs(
    tmp_path: Path,
) -> None:
    full = tmp_path / "rank0.stdout"
    face = tmp_path / "face.records"
    legacy = tmp_path / "legacy.records"
    full.write_text("S15AX 1\nS15FUTURE 2\n", encoding="ascii")
    with pytest.raises(overlay.OverlayError, match="unknown S15 record tag"):
        overlay.extract_s15_streams(full, face, legacy)
    assert not face.exists()
    assert not legacy.exists()


def test_dual_stream_extractor_rejects_dangling_output_symlink(tmp_path: Path) -> None:
    full = tmp_path / "rank0.stdout"
    outside = tmp_path / "outside.records"
    full.write_bytes(_bounded_extractor_fixture())
    face = tmp_path / "face.records"
    face.symlink_to(outside)
    with pytest.raises(overlay.OverlayError, match="destinations must be new"):
        overlay.extract_s15_streams(full, face, tmp_path / "legacy.records")
    assert face.is_symlink()
    assert not outside.exists()
    assert not (tmp_path / "legacy.records").exists()


def test_dual_stream_extractor_rejects_symlinked_output_parent(tmp_path: Path) -> None:
    full = tmp_path / "rank0.stdout"
    full.write_bytes(_bounded_extractor_fixture())
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    parent_link = tmp_path / "linked"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(overlay.OverlayError, match="symlinked parent"):
        overlay.extract_s15_streams(
            full, parent_link / "face.records", tmp_path / "legacy.records"
        )
    assert not (real_parent / "face.records").exists()
    assert not (tmp_path / "legacy.records").exists()


def test_dual_stream_extractor_rejects_symlinked_source_and_source_parent(
    tmp_path: Path,
) -> None:
    raw = _bounded_extractor_fixture()
    real_parent = tmp_path / "real"
    real_parent.mkdir()
    target = real_parent / "rank0.stdout"
    target.write_bytes(raw)
    source_link = tmp_path / "linked.stdout"
    source_link.symlink_to(target)
    with pytest.raises(overlay.OverlayError, match="not a regular file"):
        overlay.extract_s15_streams(source_link, tmp_path / "face", tmp_path / "legacy")
    parent_link = tmp_path / "linked-parent"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(overlay.OverlayError, match="symlinked parent"):
        overlay.extract_s15_streams(
            parent_link / "rank0.stdout", tmp_path / "face", tmp_path / "legacy"
        )
    assert not (tmp_path / "face").exists()
    assert not (tmp_path / "legacy").exists()


def test_dual_stream_extractor_rejects_fifo_without_blocking(tmp_path: Path) -> None:
    source = tmp_path / "rank0.stdout"
    source.write_bytes(b"ordinary log\n")
    code = "\n".join(
        (
            "import os",
            "import sys",
            "sys.path.insert(0, sys.argv[1])",
            "import s15_face_fortran_overlay as o",
            "from pathlib import Path",
            "original_open = os.open",
            "source_name = Path(sys.argv[2]).name",
            "swapped = [False]",
            "def race_open(path, flags, mode=0o777, *, dir_fd=None):",
            "    if path == source_name and dir_fd is not None and not swapped[0]:",
            "        swapped[0] = True",
            "        os.unlink(path, dir_fd=dir_fd)",
            "        os.mkfifo(path, dir_fd=dir_fd)",
            "    if dir_fd is None:",
            "        return original_open(path, flags, mode)",
            "    return original_open(path, flags, mode, dir_fd=dir_fd)",
            "os.open = race_open",
            "try:",
            "    o._open_regular_nofollow(Path(sys.argv[2]))",
            "except o.OverlayError:",
            "    raise SystemExit(0 if swapped[0] else 8)",
            "raise SystemExit(9)",
        )
    )
    result = subprocess.run(
        [sys.executable, "-c", code, str(ROOT / "harness"), str(source)],
        timeout=2,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_dual_stream_rollback_uses_pinned_parent_after_symlink_swap(
    tmp_path: Path, monkeypatch
) -> None:
    full = tmp_path / "rank0.stdout"
    full.write_bytes(_bounded_extractor_fixture())
    output_parent = tmp_path / "outputs"
    output_parent.mkdir()
    moved_parent = tmp_path / "outputs-moved"
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "face.records"
    sentinel.write_bytes(b"external sentinel\n")
    face = output_parent / "face.records"
    legacy = output_parent / "legacy.records"
    original_write = overlay._exclusive_write_no_symlinks

    def write_then_swap(path: Path, data: bytes) -> tuple[int, str]:
        created = original_write(path, data)
        if path == face:
            output_parent.rename(moved_parent)
            output_parent.symlink_to(outside, target_is_directory=True)
        return created

    monkeypatch.setattr(overlay, "_exclusive_write_no_symlinks", write_then_swap)
    with pytest.raises(overlay.OverlayError, match="symlinked parent"):
        overlay.extract_s15_streams(full, face, legacy)
    assert sentinel.read_bytes() == b"external sentinel\n"
    assert not (moved_parent / "face.records").exists()


def test_dual_stream_extractor_enforces_full_log_and_line_caps(
    tmp_path: Path, monkeypatch
) -> None:
    full = tmp_path / "rank0.stdout"
    full.write_bytes(_bounded_extractor_fixture())
    monkeypatch.setattr(overlay, "MAX_FULL_STDOUT_BYTES", 8)
    with pytest.raises(overlay.OverlayError, match="size cap"):
        overlay.extract_s15_streams(full, tmp_path / "face", tmp_path / "legacy")
    monkeypatch.setattr(overlay, "MAX_FULL_STDOUT_BYTES", 1_000_000)
    monkeypatch.setattr(overlay, "MAX_CAPTURE_LINE_BYTES", 8)
    with pytest.raises(overlay.OverlayError, match="line exceeds size cap"):
        overlay.extract_s15_streams(full, tmp_path / "face", tmp_path / "legacy")
    assert not (tmp_path / "face").exists()
    assert not (tmp_path / "legacy").exists()


def test_dual_stream_extractor_bounds_unterminated_line_reads(tmp_path: Path) -> None:
    full = tmp_path / "rank0.stdout"
    full.write_bytes(b"x" * (overlay.MAX_CAPTURE_LINE_BYTES + 1))
    with pytest.raises(overlay.OverlayError, match="line exceeds size cap"):
        overlay.extract_s15_streams(full, tmp_path / "face", tmp_path / "legacy")
    assert not (tmp_path / "face").exists()
    assert not (tmp_path / "legacy").exists()


def test_dual_stream_extractor_requires_exact_face_event_count(tmp_path: Path) -> None:
    full = tmp_path / "rank0.stdout"
    full.write_bytes(_bounded_extractor_fixture().replace(b"S15AX axis\n", b"", 1))
    with pytest.raises(overlay.OverlayError, match="exactly 18 AX, 2 PD, and 6 RK"):
        overlay.extract_s15_streams(full, tmp_path / "face", tmp_path / "legacy")

    full_neighbors = tmp_path / "rank0-neighbors.stdout"
    full_neighbors.write_bytes(_bounded_extractor_fixture(neighbors=True))
    receipt = overlay.extract_s15_streams(
        full_neighbors,
        tmp_path / "face-neighbors",
        tmp_path / "legacy-neighbors",
        neighbors=True,
    )
    assert receipt["tag_counts"]["S15AX"] == 42
    assert receipt["tag_counts"]["S15PD"] == 10
    assert receipt["tag_counts"]["S15RK"] == 14

    full_neighbors_missing = tmp_path / "rank0-neighbors-missing.stdout"
    full_neighbors_missing.write_bytes(
        _bounded_extractor_fixture(neighbors=True).replace(b"S15PD limiter\n", b"", 1)
    )
    with pytest.raises(overlay.OverlayError, match="42 AX, 10 PD, and 14 RK"):
        overlay.extract_s15_streams(
            full_neighbors_missing,
            tmp_path / "face-neighbors-missing",
            tmp_path / "legacy-neighbors-missing",
            neighbors=True,
        )


@pytest.mark.parametrize(
    "mutation,match",
    [
        ("drop_axis", "exactly Y/X/Z"),
        ("duplicate_axis", "duplicate .* face record"),
        ("unknown", "unknown S15 record tag"),
        ("wrong_tile", "tile slot or coordinate"),
        ("wrong_branch", "source branch does not match"),
        ("duplicate_json_shape", "duplicate RK consumer"),
    ],
)
def test_raw_fortran_parser_fails_closed(mutation: str, match: str) -> None:
    rows = _raw_stream().splitlines()
    if mutation == "drop_axis":
        rows.remove(next(row for row in rows if row.startswith("S15AX ")))
    elif mutation == "duplicate_axis":
        event = next(row for row in rows if row.startswith("S15AX "))
        rows.append(event)
    elif mutation == "unknown":
        rows.append("S15FUTURE 2")
    elif mutation == "wrong_tile":
        index = next(i for i, row in enumerate(rows) if row.startswith("S15RK "))
        parts = rows[index].split()
        parts[4] = "2"
        rows[index] = " ".join(parts)
    elif mutation == "wrong_branch":
        index = next(
            i
            for i, row in enumerate(rows)
            if row.startswith("S15AX ") and " 3 2 " in row
        )
        parts = rows[index].split()
        parts[13] = "1"
        rows[index] = " ".join(parts)
    elif mutation == "duplicate_json_shape":
        index = next(i for i, row in enumerate(rows) if row.startswith("S15RK "))
        rows.append(rows[index])
    with pytest.raises(overlay.OverlayError, match=match):
        overlay.parse_fortran_capture("\n".join(rows) + "\n", ROOT, CONFIG)
