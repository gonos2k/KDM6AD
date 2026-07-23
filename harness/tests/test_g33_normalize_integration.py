"""Public-CI integration of the Fortran normalizer with the comparator core — no
gfortran build. Parses the checked-in real legacy dump, projects it to the
comparator's normalized run, and proves the schema-canonical order + monotonic
scalar_seq_id + dtype + no-duplicate-identity contract holds on REAL evidence
(579 ops across TOP/INTERIOR/BOTTOM, qr+nr) — not just the synthetic fixtures."""
import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = Path(__file__).parent / "data" / "g33_legacy_sample.g33f"
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
sys.path.insert(0, str(ROOT / "harness"))
import g33_fortran_dump as fd            # noqa: E402
import g33_normalize as nz               # noqa: E402
import g33_fourcase_comparator as cmp    # noqa: E402

RUN = fd.parse_fortran_run(SAMPLE.read_text(), "legacy", 4, 3)
NORM = nz.from_fortran_run(RUN)


def test_real_run_projects_and_events_build():
    assert NORM["algorithm"] == "legacy" and len(NORM["ops"]) == len(RUN.ops)
    # _events enforces schema order, monotonic scalar_seq_id, dtype match, and
    # identity uniqueness — it must accept the real run without a StructuralError.
    ev = cmp._events(NORM)
    assert len(ev) == len(NORM["ops"]) + len(NORM["stages"])


def test_real_run_self_compare_has_no_divergence():
    d = cmp.compare_pair(NORM, NORM)
    assert d.invalid is None and d.phase is None


def _mutate(pred):
    m = copy.deepcopy(NORM)
    o = next(o for o in m["ops"] if pred(o))
    o["bits"] ^= 0xFF
    return m


def test_real_run_shared_rung_mutation_first_diverges_there():
    mut = _mutate(lambda o: o["role"] == "INTERIOR" and o["op_id"] == "QR_FALK"
                  and o["field"] == "mul_work1")
    d = cmp.compare_pair(NORM, mut)
    assert d.phase == "op" and d.tag == "FALK_mul_work1" and d.kind == cmp.mech.SHARED


def test_real_run_scrambled_scalar_seq_is_invalid():
    m = copy.deepcopy(NORM)
    m["ops"][0]["op_seq_id"] = 10 ** 9          # break monotonicity in canonical order
    assert cmp.compare_pair(NORM, m).invalid is not None
