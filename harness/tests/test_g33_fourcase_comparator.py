"""Verdict-matrix unit tests for the four-case comparator core (public CI — no
build). Synthetic runs from the REAL schema vocabulary exercise the owner's PR#66A
closeout matrix: fall_after as a shared accumulator add (not a false FAIL), the
mass/number conservative labels, the closed-world taxonomy, causal-carry vs
external-input, surface output increments, and malformed-input -> INVALID."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fourcase_comparator as cmp  # noqa: E402
import g33_mechanism as mech           # noqa: E402
import g33_schema as schema            # noqa: E402


_MASK = {"f32": 0xFFFFFFFF, "f64": 0xFFFFFFFFFFFFFFFF, "u8": 0xFF}


def _base(dt, n, col, k, opid, fld):
    return (hash((n, col, k, opid, fld)) & _MASK[dt]) or 1


def _species_run(algo, sp, cells, stages, bits):
    bits = bits or {}
    ops = []
    for n, col, k, role in cells:
        for opid in schema.ops_for_species(algo, role, sp):
            for fld, dt in schema.op_fields(algo, role, opid):
                key = (n, col, k, opid, fld)
                b = bits.get(key, _base(dt, *key)) & _MASK[dt]
                ops.append({"n": n, "col": col, "k": k, "role": role, "species": sp,
                            "op_id": opid, "field": fld, "dtype": dt, "bits": b})
    return {"algorithm": algo, "ops": ops, "stages": list(stages or [])}


def _run(algo, cells=((1, 1, 1, "INTERIOR"),), stages=None, bits=None):
    return _species_run(algo, "qr", cells, stages, bits)


def _nr_run(algo, cells=((1, 1, 1, "INTERIOR"),), bits=None):
    return _species_run(algo, "nr", cells, None, bits)


def _surface(bits=None):
    bits = bits or {}
    return [{"stage": "surface", "n": 0, "col": 1, "k": -1, "field": f,
             "dtype": "f32", "bits": bits.get(f, (hash(f) & 0xFFFFFFFF) or 1)}
            for f in schema.semantic_surface_fields()]


def _verdict(lf, lc, cf, cc):
    return cmp.adjudicate(lf, lc, cf, cc)["verdict"]


# ── core verdicts ─────────────────────────────────────────────────────────────
def test_no_divergence_is_inconclusive():
    assert _verdict(_run("legacy"), _run("legacy"),
                    _run("conservative"), _run("conservative")) == "INCONCLUSIVE"


def test_shared_falk_divergence_is_pass():
    d = {(1, 1, 1, "QR_FALK", "mul_work1"): 0xABCD}
    assert _verdict(_run("legacy"), _run("legacy", bits=d),
                    _run("conservative"), _run("conservative", bits=d)) == "PASS"


# ── P0-1: fall_after is a shared accumulator add, not a variant result ─────────
def test_fall_after_both_pairs_is_pass_not_fail():
    d = {(1, 1, 1, "QR_FALLACC", "fall_after"): 0x4242}
    v = _verdict(_run("legacy"), _run("legacy", bits=d),
                 _run("conservative"), _run("conservative", bits=d))
    assert v == "PASS"


def test_conservative_fall_increment_is_fail():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_FALLACC", "fall_increment"): 9}))
    assert r["verdict"] == "FAIL" and "RATE_ACCUMULATION" in r["reason"]


def test_fall_before_is_invalid_causal_carry():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_FALLACC", "fall_before"): 7}))
    assert r["verdict"] == "INVALID_EVIDENCE" and "causal carry" in r["reason"]


# ── P0-2: mass (ρΔz) vs number (Δz) conservative inflow labels ─────────────────
def test_conservative_qr_inflow_labeled_mass_rhodz():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_INFLOW", "inflow_final"): 9}))
    assert r["verdict"] == "FAIL" and "CONS_MASS_RHODZ_INFLOW" in r["reason"]


def test_conservative_nr_inflow_labeled_number_dz():
    r = cmp.adjudicate(_nr_run("legacy"), _nr_run("legacy"), _nr_run("conservative"),
                       _nr_run("conservative", bits={(1, 1, 1, "NR_INFLOW", "inflow_final"): 9}))
    assert r["verdict"] == "FAIL" and "CONS_NUMBER_DZ_INFLOW" in r["reason"]


# ── P0-3: closed-world taxonomy ───────────────────────────────────────────────
def test_taxonomy_is_closed_world():
    mech.check_universe()                          # exact schema coverage + canary
    import pytest
    with pytest.raises(mech.TaxonomyHole):
        mech.mechanism("legacy", "INTERIOR", "qr", "QR_UPDATE", "invented_field")


# ── P0-4: surface output increments ───────────────────────────────────────────
def test_surface_rain_increment_both_pairs_is_pass():
    d = {"rain_increment": 0x77}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "PASS"


def test_surface_snow_increment_both_pairs_is_inconclusive():
    d = {"snow_increment": 0x77}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "INCONCLUSIVE"


def test_surface_species_sum_both_pairs_is_pass():
    d = {"bottom_fall_total": 0x5678}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "PASS"


def test_surface_out_of_scope_species_both_pairs_is_inconclusive():
    d = {"bottom_fall_qs": 0x1234}
    assert _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                    _run("conservative", stages=_surface()),
                    _run("conservative", stages=_surface(d))) == "INCONCLUSIVE"


# ── P0-5: external input is not evidence corruption ───────────────────────────
def test_surface_denr_external_input_is_inconclusive_not_invalid():
    d = {"surface_denr": 0x1111}
    r = cmp.adjudicate(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                       _run("conservative", stages=_surface()),
                       _run("conservative", stages=_surface(d)))
    assert r["verdict"] == "INCONCLUSIVE" and "external input" in r["reason"]


# ── P0-6: malformed normalized input -> INVALID_EVIDENCE, never a crash ───────
def test_missing_key_is_invalid_not_crash():
    b = _run("conservative")
    del b["ops"][0]["dtype"]
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_wrong_type_is_invalid_not_crash():
    b = _run("conservative")
    b["ops"][0]["bits"] = "not-an-int"
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_unknown_surface_field_is_invalid_not_crash():
    b = _run("conservative", stages=[{"stage": "surface", "n": 0, "col": 1, "k": -1,
                                      "field": "bogus_out", "dtype": "f32", "bits": 1}])
    assert _verdict(_run("legacy"), _run("legacy"),
                    _run("conservative", stages=[]), b) == "INVALID_EVIDENCE"


# ── role-aware TOP depletion + shared interior ────────────────────────────────
def test_top_q_minus_out_both_pairs_is_not_pass():
    top = ((1, 1, 0, "TOP"),)
    d = {(1, 1, 0, "QR_UPDATE", "q_minus_out"): 0xBEEF}
    v = _verdict(_run("legacy", cells=top, bits=d), _run("legacy", cells=top),
                 _run("conservative", cells=top, bits=d), _run("conservative", cells=top))
    assert v == "FAIL"


def test_interior_q_minus_out_both_pairs_is_pass():
    d = {(1, 1, 1, "QR_UPDATE", "q_minus_out"): 0xBEEF}
    assert _verdict(_run("legacy"), _run("legacy", bits=d),
                    _run("conservative"), _run("conservative", bits=d)) == "PASS"


# ── structural guards ─────────────────────────────────────────────────────────
def test_identity_universe_mismatch_is_invalid():
    b = _run("conservative")
    b["ops"] = b["ops"][:-1]
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_duplicate_identity_is_invalid():
    b = _run("conservative")
    b["ops"].append(dict(b["ops"][0]))
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_algorithm_typo_is_invalid():
    bad = _run("conservative")
    bad["algorithm"] = "conservativ"
    assert _verdict(_run("legacy"), _run("legacy"), bad, _run("conservative")) == "INVALID_EVIDENCE"


def test_dtype_mismatch_vs_schema_is_invalid():
    b = _run("conservative")
    b["ops"][0]["dtype"] = "f64"                   # QR_FALK.mul_dend_q is f32
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_unknown_stage_is_invalid():
    b = _run("conservative", stages=[{"stage": "reslope_output", "n": 1, "col": 1,
                                      "k": 1, "field": "qr", "dtype": "f32", "bits": 1}])
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative", stages=[]),
                    b) == "INVALID_EVIDENCE"


# ── P1-4: PASS records the raw-bit divergence signature ───────────────────────
def test_pass_records_bit_signature():
    d = {(1, 1, 1, "QR_FALK", "mul_work1"): 0xABCD}
    r = cmp.adjudicate(_run("legacy"), _run("legacy", bits=d),
                       _run("conservative"), _run("conservative", bits=d))
    sig = r["legacy_first_divergence"]["signature"]
    assert sig and "ulp_delta" in sig and sig["direction"] in ("C>F", "C<F", "equal")


# ── taxonomy role/expression awareness ────────────────────────────────────────
def test_mechanism_taxonomy_is_role_and_expression_aware():
    m = mech.mechanism
    assert m("conservative", "TOP", "qr", "QR_UPDATE", "q_minus_out").kind == mech.CONSERVATIVE
    assert m("legacy", "TOP", "qr", "QR_UPDATE", "q_minus_out").kind == mech.LEGACY
    assert m("legacy", "INTERIOR", "qr", "QR_UPDATE", "q_minus_out").kind == mech.SHARED
    assert m("legacy", "INTERIOR", "qr", "QR_FALLACC", "fall_after").kind == mech.SHARED
    assert m("conservative", "INTERIOR", "qr", "QR_FALLACC", "fall_before").kind == mech.CAUSAL_CARRY
