"""Density comparisons through real text parsing, without a host or driver build."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import g33_metric_trajectory as mt
import g33_number_transport as nt
from test_g33_number_transport import _ext, _FEATS, _f64, _stream


def _matrix(**call_options):
    return {a: _stream(_ext(**call_options), feats=_FEATS, rho_profile=a)
            for a in mt.ARMS}


@pytest.mark.parametrize("options,field", [({"nsplit": 99}, "nsplit"),
                                          ({"mode": "carry"}, "carry"),
                                          ({"width": 7}, "expected")])
def test_request_must_match_valid_raw_streams(options, field):
    args = dict(nsplit=1, mode="rezero", width=1)
    args.update(options)
    raw = _matrix()
    assert all(nt.validated_run_identity(t) for t in raw.values())
    with pytest.raises(nt.StreamError, match=field):
        mt.analysis("must-not-run", raw=raw, **args)


def test_each_arm_must_declare_its_requested_profile():
    raw = _matrix()
    raw["inverted"] = raw["as-is"]
    with pytest.raises(nt.StreamError, match="inverted: requested rho"):
        mt.analysis("must-not-run", 1, width=1, raw=raw)


def test_matching_but_unsupported_mode_is_not_a_valid_raw_experiment():
    raw = {a: s.replace("legacy rezero", "legacy unknown")
           for a, s in _matrix().items()}
    with pytest.raises(ValueError, match="unsupported mode"):
        mt.analysis("must-not-run", 1, width=1, mode="unknown", raw=raw)


def test_supported_carry_records_remain_readable():
    raw = {a: s.replace("legacy rezero", "legacy carry")
           for a, s in _matrix().items()}
    result = mt.analysis("must-not-run", 1, width=1, mode="carry", raw=raw)
    assert result["mode"] == "carry" and result["baseline"] == "provided raw"


@pytest.mark.parametrize("change,field", [
    (lambda s: s.replace("42C80000", "43480000"), "delt"),
    (lambda s: s.replace("legacy rezero", "nmass rezero"), "algorithm"),
    (lambda s: _f64(s).replace("40000000", "4000000000000000"), "real_bytes"),
])
def test_internally_valid_streams_can_still_be_different_experiments(change, field):
    raw = _matrix()
    raw["uniform"] = change(raw["uniform"])
    base, arm = [nt.validated_run_identity(raw[a]) for a in ("as-is", "uniform")]
    assert base[field] != arm[field]
    with pytest.raises(nt.StreamError, match=field + " differs"):
        mt.analysis("must-not-run", 1, width=1, raw=raw)


def test_changed_level_count_is_not_a_density_intervention():
    raw = _matrix()
    raw["uniform"] = _matrix(ks=3)["uniform"]
    assert nt.validated_run_identity(raw["uniform"])["levels"] == 3
    with pytest.raises(nt.StreamError, match="levels differs"):
        mt.analysis("must-not-run", 1, width=1, raw=raw)


def test_equal_outer_steps_with_different_inner_step_sizes_are_refused():
    raw = _matrix()
    lines = raw["uniform"].splitlines()
    body = [line for line in lines if line.startswith("G33F ")]
    second = []
    for line in body:
        words = line.split()
        words[2] = "2"  # the second complete inner loop of the same call
        second.append(" ".join(words))
    at = next(i for i, line in enumerate(lines) if line.startswith("G33N CALL_END"))
    lines[at:at] = second
    raw["uniform"] = "\n".join(
        line.replace("42C80000", "42480000") if "nflux_dtcld" in line else line
        for line in lines) + "\n"
    rid = nt.validated_run_identity(raw["uniform"])
    assert (rid["delt"], rid["dtcld"], rid["loops"]) == (100., 50., 2)
    with pytest.raises(nt.StreamError, match="dtcld differs"):
        mt.analysis("must-not-run", 1, width=1, raw=raw)


def test_declared_transfer_metric_cannot_override_the_registered_operator():
    raw = _matrix()
    lines = raw["uniform"].splitlines()
    lines.insert(1, "G33N METRIC moist_layer_mass")  # legacy uses thickness
    raw["uniform"] = "\n".join(lines) + "\n"
    with pytest.raises(ValueError, match="metric|measure"):
        mt.analysis("must-not-run", 1, width=1, raw=raw)


def _tiled(profile, ranges):
    calls = []
    for cid, cols in enumerate(ranges, 1):
        calls.append(_ext(cid, cols=cols).replace(
            f"G33N CALL_BEGIN {cid} {cid} 1 ", f"G33N CALL_BEGIN {cid} 1 {cid} ").replace(
            f"G33N CALL_END {cid} {cid} 1", f"G33N CALL_END {cid} 1 {cid}"))
    return _stream(*calls, nsplit=1, ntile=len(calls), feats=_FEATS, rho_profile=profile)


def test_equal_tile_counts_and_domain_width_do_not_prove_equal_partitions():
    raw = {a: _tiled(a, [(1,), (2, 3)]) for a in mt.ARMS}
    raw["uniform"] = _tiled("uniform", [(1, 2), (3,)])
    base, arm = [nt.validated_run_identity(raw[a]) for a in ("as-is", "uniform")]
    assert base["ntile"] == arm["ntile"] == 2
    assert base["width"] == arm["width"] == 3
    with pytest.raises(nt.StreamError, match="tile_ranges differs"):
        mt.analysis("must-not-run", 1, width=3, raw=raw)


def test_adaptive_substeps_remain_a_response_with_unmatched_interfaces():
    raw = _matrix()
    raw["inverted"] = _matrix(mstep=2)["inverted"]
    result = mt.analysis("must-not-run", 1, width=1, raw=raw)
    assert result["arms"]["uniform"][1]["comparable"]
    assert not result["arms"]["inverted"][1]["comparable"]
    assert "interface universes differ" in result["arms"]["inverted"][1]["reason"]


def test_raw_is_not_a_rerun_and_each_stream_is_strictly_parsed_once(monkeypatch):
    raw = _matrix()
    seen = []
    parse = nt.calls

    def observed_parse(text):
        seen.append(text)
        return parse(text)

    monkeypatch.setattr(nt, "calls", observed_parse)
    monkeypatch.setattr(mt.rmx, "collect", lambda *a, **k: pytest.fail("raw must not run"))
    kept = {}
    result = mt.analysis("must-not-run", 1, width=1, raw=raw, keep=kept)
    assert result["baseline"] == "provided raw"
    assert seen == [raw[a] for a in mt.ARMS]
    assert kept == raw
    assert all(r["run_identity"]["real_bytes"] == 4
               for r in result["arms_runtime"].values())


def test_supplied_bundle_baseline_must_be_the_one_actually_analyzed():
    raw = _matrix()
    result = mt.analysis("must-not-run", 1, width=1, raw=raw,
                         baseline_stream=raw["as-is"])
    assert result["baseline"] == "bundle member"
    with pytest.raises(nt.StreamError, match="differs from the supplied bundle baseline"):
        mt.analysis("must-not-run", 1, width=1, raw=raw,
                    baseline_stream=raw["as-is"] + "unrelated run log\n")


def test_collected_streams_use_the_same_request_guard(monkeypatch):
    raw = _matrix()
    monkeypatch.setattr(mt.rmx, "collect", lambda *a, **k: raw)
    assert mt.analysis("driver", 1, width=1)["baseline"] == "re-run"
    with pytest.raises(nt.StreamError, match="requested nsplit"):
        mt.analysis("driver", 2, width=1)


def test_actual_collector_subprocess_output_reaches_the_strict_boundary(tmp_path):
    records = tmp_path / "streams.json"
    records.write_text(json.dumps(_matrix()))
    driver = tmp_path / "driver"
    driver.write_text("#!/usr/bin/env python3\nimport json,sys\n"
                      f"with open({str(records)!r}) as f: streams=json.load(f)\n"
                      "print(streams[sys.argv[-1]],end='')\n")
    driver.chmod(0o755)
    result = mt.analysis(str(driver), 1, width=1)
    assert result["baseline"] == "re-run"
    assert all(cols[1]["comparable"] for cols in result["arms"].values())
    with pytest.raises(nt.StreamError, match="requested nsplit"):
        mt.analysis(str(driver), 2, width=1)


@pytest.mark.parametrize("extra", [False, True])
def test_matrix_requires_exactly_its_declared_arm_set(extra):
    raw = _matrix()
    if extra:
        raw["unrequested"] = raw["as-is"]
    else:
        del raw["uniform"]
    kept = {"sentinel": "unchanged"}
    with pytest.raises(nt.StreamError, match="exactly the requested arms"):
        mt.analysis("must-not-run", 1, width=1, raw=raw, keep=kept)
    assert kept == {"sentinel": "unchanged"}


def test_weight_first_order_assigns_the_interaction_to_transport():
    key = (1, 1, 1, 0, 1)
    row = dict(rho_up=1., rho_lo=2., drho=1., dz_up=1., dz_lo=1.,
               dn_out=.75, dn_in=.25)
    base = {1: {key: row}}
    arm = {1: {key: dict(row, rho_up=2., rho_lo=3., dn_in=.5)}}
    before = copy.deepcopy((base, arm))
    result = mt.decompose(base, arm)[1]
    assert result["weight_effect"] == -.5
    assert result["trajectory"] == .75
    assert result["residual_change"] == .25
    # Independent reversed path: change arrival under the original lower
    # weight, then weights under the new arrival. Interaction is .25.
    reverse_transport = 2. * (.5 - .25)
    reverse_weight = (3. - 2.) * .5 - (2. - 1.) * .75
    assert (reverse_weight, reverse_transport) == (-.25, .5)
    assert result["trajectory"] - reverse_transport == .25
    assert reverse_weight - result["weight_effect"] == .25
    assert (base, arm) == before
