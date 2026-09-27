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


def _bounded_extractor_fixture() -> bytes:
    return (
        b"WRF banner\nS15Q legacy\n"
        + b"S15AX axis\n" * 18
        + b"S15PD limiter\n" * 2
        + b"S15RK consumer\n" * 6
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
