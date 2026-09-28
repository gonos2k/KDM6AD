from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import make_s10_stage2_pair as pair  # noqa: E402
import make_progb_validity_capture as validity  # noqa: E402


def fixture_source() -> str:
    return (
        pair._DECL_ANCHOR
        + "! limiter complete\n"
        + pair.COLD_QG_ANCHOR
        + pair.COLD_BRS_ANCHOR
    )


def fixture_validity_overlay(source: str) -> str:
    slope_code = "       write(*,*) 'S10SLP'\n" + pair._SHAPE_GENERIC_WRITE + pair._SHAPE_FIXED_BLOCK
    return source + "".join(
        validity._guard(f"slope_consumer_{site}", slope_code)
        for site in range(1, 8)
    )


def test_pair_wraps_actual_cold_updates_and_strips_exactly_without_rhox_payload():
    source = fixture_source()
    generated = pair._inject_pair(source)
    assert pair.strip_pair(generated) == source
    blocks = []
    cursor = 0
    while True:
        start = generated.find("! S10_PAIR_BEGIN:", cursor)
        if start < 0:
            break
        end = generated.find("! S10_PAIR_END:", start)
        blocks.append(generated[start:end])
        cursor = end
    payload = "\n".join(blocks).lower()
    assert "rhox" not in payload
    assert "capture_enabled .and. capture_step.eq.1" in payload and "lat.eq.2" in payload
    assert "i.eq.142" in payload and "k.eq.17" in payload
    assert "capture_last_site" in payload and "loop," in payload
    assert "loop,n" not in payload and ",n," not in payload
    assert "capture_last_loop,capture_last_substep,1,i,k" in payload
    assert "mstepmax" not in payload and "mstepmax_i" not in payload
    assert "12(1X,I0)" in generated
    assert "storage_size(0_s10pair_word_kind).ne.32" in payload
    assert "storage_size(qrs(i,k,3)).ne.32" in payload
    assert "24(1X,Z8.8)" in generated
    for name in (*pair.MASS_RATES, *pair.BRS_RATES):
        assert f"transfer({name}(i,k),0_s10pair_word_kind)" in payload
    for name in ("delta2", "delta3"):
        assert f"transfer({name},0_s10pair_word_kind)" in payload
    assert "transfer(qrs(i,k,3),0_s10pair_word_kind)" in payload
    assert "transfer(brs(i,k),0_s10pair_word_kind)" in payload


def test_pair_fails_closed_on_duplicate_or_missing_update_anchor():
    source = fixture_source()
    with pytest.raises(ValueError, match="cold qg update: expected one source anchor"):
        pair._inject_pair(source + pair.COLD_QG_ANCHOR)
    with pytest.raises(ValueError, match="cold brs update: expected one source anchor"):
        pair._inject_pair(source.replace(
            "baacw(i,k)+bgacr(i,k)", "baacw(i,k)+bgacr(i,k)+1"))


def test_pair_only_overlay_removes_two_unsafe_shape_writes_at_each_slope_site():
    source = fixture_source()
    overlay = fixture_validity_overlay(source)
    filtered, removed = pair._remove_s10shape_writes(overlay)
    assert removed == 14
    assert "S10SHAPE" not in filtered
    assert filtered.count("'S10SLP'") == 7
    assert validity.strip_capture(filtered) == source
    missing = overlay.replace(pair._SHAPE_FIXED_BLOCK, "", 1)
    with pytest.raises(ValueError, match="expected two S10SHAPE writes and one S10SLP"):
        pair._remove_s10shape_writes(missing)


def test_build_calls_pinned_mp237_validity_builder_and_records_strip_contract(tmp_path, monkeypatch):
    source = tmp_path / "module_mp_kdm6_cons.F"
    base = fixture_source()
    source.write_text(base)
    validity_overlay = fixture_validity_overlay(base)
    seen = {}

    def fake_validity_build(given_source, output, manifest, variant):
        seen.update(source=given_source, variant=variant)
        output.write_text(validity_overlay)
        manifest.write_text("{}\n")
        return {
            "canonical_source_sha256": "test-source-sha",
            "capture_source_sha256": "test-validity-overlay-sha",
        }

    monkeypatch.setattr(pair.validity, "build", fake_validity_build)
    output = tmp_path / "overlay.F"
    manifest = tmp_path / "overlay.json"
    result = pair.build(source, output, manifest)
    assert seen == {"source": source, "variant": "mp237"}
    generated = output.read_text()
    pair_stripped = pair.strip_pair(generated)
    assert "S10SHAPE" not in pair_stripped
    assert pair_stripped.count("'S10SLP'") == 7
    assert validity.strip_capture(pair_stripped) == source.read_text()
    assert result["canonical_source_sha256"] == "test-source-sha"
    assert result["rhox_read_or_emitted_by_pair"] is False
    assert result["brs_nonrhox_volume_rate_fields"] == list(pair.BRS_RATES)
    assert result["unrecorded_brs_term"] == (
        "pgdep/rhox (density OUT unassigned possible; never read by tap)"
    )
    assert result["s10shape_numeric_writes_removed"] == 14
    assert result["s10shape_numeric_writes_remaining"] == 0
    assert "brs_volume_rate_fields" not in result
    assert result["physical_updates_changed"] is False
    assert result["native_build_or_run"] is False
    assert manifest.exists()
    with pytest.raises(ValueError, match="paths must be distinct"):
        pair.build(source, output, source)
