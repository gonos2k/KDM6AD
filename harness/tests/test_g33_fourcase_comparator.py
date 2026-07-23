"""Verdict-matrix unit tests for the four-case comparator core (public CI — no
build). Synthetic normalized runs built from the REAL schema vocabulary exercise
PASS / FAIL / INCONCLUSIVE / INVALID_EVIDENCE and the owner's P0 closeout matrix:
role/expression-aware mechanism tags, canonical schema order, duplicate-identity
and op_seq/algorithm/stage fail-closed guards, and dtype in the PASS key."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_fourcase_comparator as cmp  # noqa: E402
import g33_mechanism as mech           # noqa: E402
import g33_schema as schema            # noqa: E402


def _base(n, col, k, opid, fld):
    return (hash((n, col, k, opid, fld)) & 0x7FFFFFFF) or 1


def _run(algo, cells=((1, 1, 1, "INTERIOR"),), stages=None, bits=None):
    """Emit every qr op field (schema order, monotonic op_seq) for each cell;
    `bits` overrides specific (n,col,k,op_id,field) rungs to force a divergence."""
    bits = bits or {}
    ops, seq = [], 0
    for n, col, k, role in cells:
        for opid in schema.ops_for_species(algo, role, "qr"):
            for fld, dt in schema.op_fields(algo, role, opid):
                key = (n, col, k, opid, fld)
                ops.append({"n": n, "col": col, "k": k, "role": role, "species": "qr",
                            "op_id": opid, "field": fld, "dtype": dt,
                            "bits": bits.get(key, _base(*key)), "op_seq_id": seq})
                seq += 1
    return {"algorithm": algo, "ops": ops, "stages": list(stages or [])}


def _surface(bits=None):
    bits = bits or {}
    out = []
    for fld in cmp._SURFACE_ORDER:
        dt = "u8" if False else "f32"
        out.append({"stage": "surface", "n": 0, "col": 1, "k": -1, "field": fld,
                    "dtype": dt, "bits": bits.get(fld, (hash(fld) & 0x7FFFFFFF) or 1)})
    return out


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


def test_conservative_rhodz_inflow_is_fail():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_INFLOW", "inflow_final"): 9}))
    assert r["verdict"] == "FAIL" and "CONS_INFLOW_rhodz" in r["reason"]


# ── P0-1: TOP q_minus_out is NOT a shared subtract ────────────────────────────
def test_top_q_minus_out_both_pairs_is_not_pass():
    top = ((1, 1, 0, "TOP"),)
    d = {(1, 1, 0, "QR_UPDATE", "q_minus_out"): 0xBEEF}
    v = _verdict(_run("legacy", cells=top, bits=d), _run("legacy", cells=top),
                 _run("conservative", cells=top, bits=d), _run("conservative", cells=top))
    # legacy TOP raw depletion vs conservative TOP capped depletion — different
    # arithmetic topology, must never be classified as a shared PASS.
    assert v != "PASS" and v == "FAIL"


# ── P0-2: FALLACC carry input is not conservative arithmetic ───────────────────
def test_conservative_fallacc_carry_before_is_invalid_not_fail():
    r = cmp.adjudicate(_run("legacy"), _run("legacy"), _run("conservative"),
                       _run("conservative", bits={(1, 1, 1, "QR_FALLACC", "fall_before"): 7}))
    assert r["verdict"] == "INVALID_EVIDENCE" and "carry" in r["reason"]


# ── P0-3: out-of-scope surface species is not a shared sum ─────────────────────
def test_surface_out_of_scope_species_both_pairs_is_inconclusive():
    d = {"bottom_fall_qs": 0x1234}
    v = _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                 _run("conservative", stages=_surface()), _run("conservative", stages=_surface(d)))
    assert v == "INCONCLUSIVE"


def test_surface_species_sum_both_pairs_is_pass():
    d = {"bottom_fall_total": 0x5678}
    v = _verdict(_run("legacy", stages=_surface()), _run("legacy", stages=_surface(d)),
                 _run("conservative", stages=_surface()), _run("conservative", stages=_surface(d)))
    assert v == "PASS"


# ── canonical order: n=1 op wins over the n=2 stage it perturbs (P0-3 of PR#64) ─
def test_n1_op_divergence_not_misattributed_to_later_stage():
    cells = ((1, 1, 1, "INTERIOR"), (2, 1, 1, "INTERIOR"))
    lf = _run("legacy", cells=cells)
    lc = _run("legacy", cells=cells, bits={(1, 1, 1, "QR_FALK", "mul_work1"): 42})
    lc["stages"] = [{"stage": "substep_pre", "n": 2, "col": 1, "k": 1,
                     "field": "qr", "dtype": "f32", "bits": 999}]
    lf["stages"] = [{"stage": "substep_pre", "n": 2, "col": 1, "k": 1,
                     "field": "qr", "dtype": "f32", "bits": 1}]
    d = cmp.compare_pair(lf, lc)
    assert d.phase == "op" and d.identity[6] == "QR_FALK"


# ── fail-closed structural guards ─────────────────────────────────────────────
def test_identity_universe_mismatch_is_invalid():
    a = _run("conservative")
    b = _run("conservative")
    b["ops"] = b["ops"][:-1]
    assert _verdict(_run("legacy"), _run("legacy"), a, b) == "INVALID_EVIDENCE"


def test_duplicate_identity_is_invalid():
    b = _run("conservative")
    b["ops"].append(dict(b["ops"][0]))            # exact identity duplicate
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_wrong_op_seq_id_is_invalid():
    b = _run("conservative")
    b["ops"][0]["op_seq_id"] = 10 ** 6            # not monotonic in schema order
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_algorithm_typo_is_invalid():
    bad = _run("conservative")
    bad["algorithm"] = "conservativ"
    assert _verdict(_run("legacy"), _run("legacy"), bad, _run("conservative")) == "INVALID_EVIDENCE"


def test_unknown_stage_is_invalid():
    b = _run("conservative")
    b["stages"] = [{"stage": "reslope_output", "n": 1, "col": 1, "k": 1,
                    "field": "qr", "dtype": "f32", "bits": 1}]
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


def test_dtype_mismatch_vs_schema_is_invalid():
    b = _run("conservative")
    b["ops"][0]["dtype"] = "f64"                  # QR_FALK.mul_dend_q is f32
    assert _verdict(_run("legacy"), _run("legacy"), _run("conservative"), b) == "INVALID_EVIDENCE"


# ── P0-8: dtype is part of the variant-independent PASS key ────────────────────
def test_shared_key_includes_dtype():
    # The PASS key must carry the dtype/rounding domain, so a shared field name
    # that diverged in f32 in one pair and f64 in the other can never align.
    ev = cmp._events(_run("legacy"))
    falk = next(e for e in ev if e.identity[6:8] == ("QR_FALK", "mul_work1"))
    assert falk.shared_key[-1] == "f64" and falk.identity[-1] == "f64"


# ── taxonomy is role/expression aware (P0-1) ──────────────────────────────────
def test_mechanism_taxonomy_is_role_and_expression_aware():
    assert mech.mechanism("conservative", "TOP", "qr", "QR_UPDATE", "q_minus_out").kind == mech.CONSERVATIVE
    assert mech.mechanism("legacy", "TOP", "qr", "QR_UPDATE", "q_minus_out").kind == mech.LEGACY
    assert mech.mechanism("legacy", "INTERIOR", "qr", "QR_UPDATE", "q_minus_out").kind == mech.SHARED
    assert mech.mechanism("legacy", "INTERIOR", "qr", "QR_FALK", "mul_work1").kind == mech.SHARED
    assert mech.mechanism("conservative", "INTERIOR", "qr", "QR_FALLACC", "fall_before").kind == mech.INPUT


def test_check_universe_covers_every_schema_field():
    mech.check_universe()          # raises on any unmapped field
