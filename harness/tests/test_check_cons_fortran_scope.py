#!/usr/bin/env python3
"""C4 Gate A contract: check_cons_fortran_scope.py must accept EXACTLY the
pinned edit set (rename-normalized) and fail loud on anything else —
out-of-scope edits, drifted pinned-edit content, legacy sha drift, and any
touch of the raw ice-velocity handoff blocks.

Runs against SYNTHETIC fixtures (the real Fortran lives only in the private
host tree); the real manifest is validated structurally.

Runs under pytest OR directly (`python3 test_check_cons_fortran_scope.py`).
"""
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HARNESS = pathlib.Path(__file__).resolve().parents[1]
CHECKER = HARNESS / "check_cons_fortran_scope.py"
REAL_MANIFEST = HARNESS / "cons_fortran_scope_manifest.json"

SPACER = ["! spacer %02d" % i for i in range(12)]

EDIT_OLD = [
    "           falk = dend*qrs*work1/mstep",
    "           qrs = max(qrs-falk*dtcld/dend,0.)",
]
# fully distinct from EDIT_OLD (no shared leading/trailing lines): the
# checker's diff clusters contain only NON-equal lines, so a manifest entry
# must be written the same way.
EDIT_NEW = [
    "           dqr = min(dend*qrs*work1/mstep*dtcld/dend,qrs)",
    "           qrs = qrs-dqr",
]

HANDOFF = [
    "        do k = kte, kts, -1",
    "            work1(i,k,1) = work1(i,k,1)/delz(i,k)",
    "        enddo",
]


def legacy_text() -> str:
    lines = (
        ["module module_mp_kdm6", "! header"]
        + SPACER
        + ["subroutine kdm6init(a)", "end subroutine kdm6init"]
        + SPACER
        + ["subroutine kdm6(x)"]
        + EDIT_OLD
        + SPACER
        + HANDOFF
        + SPACER
        + ["end subroutine kdm6", "end module module_mp_kdm6"]
    )
    return "\n".join(lines) + "\n"


def rename(text: str) -> str:
    text = re.sub(r"\bmodule_mp_kdm6\b", "module_mp_kdm6_cons", text)
    text = re.sub(r"\bkdm6init\b", "kdm6init_cons", text)
    return re.sub(r"\bkdm6\b", "kdm6_cons", text)


def good_cons_text() -> str:
    return rename(legacy_text().replace("\n".join(EDIT_OLD), "\n".join(EDIT_NEW)))


def run_checker(tmp: pathlib.Path, legacy: str, cons: str, manifest: dict):
    (tmp / "legacy.F").write_text(legacy)
    (tmp / "cons.F").write_text(cons)
    (tmp / "manifest.json").write_text(json.dumps(manifest))
    out = tmp / "report.json"
    proc = subprocess.run(
        [sys.executable, str(CHECKER),
         "--legacy", str(tmp / "legacy.F"),
         "--cons", str(tmp / "cons.F"),
         "--manifest", str(tmp / "manifest.json"),
         "--json-out", str(out)],
        capture_output=True, text=True)
    if not out.exists():
        # the checker crashed before writing its report — fail with the real
        # cause (traceback/stderr) instead of a bare FileNotFoundError.
        raise AssertionError(
            f"checker wrote no report (rc={proc.returncode}); "
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
    return proc.returncode, json.loads(out.read_text())


def base_manifest(legacy: str) -> dict:
    return {
        "legacy_sha256": {
            "module_mp_kdm6.F": hashlib.sha256(legacy.encode()).hexdigest(),
            "module_mp_kdm6ad.F": "0" * 64,   # not passed in these tests
        },
        "allowed_edits": [
            {"name": "sed-edit", "legacy_span": [0, 0],
             "old": EDIT_OLD, "new": EDIT_NEW},
        ],
        "handoff_blocks": [
            {"name": "reslope", "expect_count": 1, "lines": HANDOFF},
        ],
    }


def test_pass_on_exact_pinned_edits():
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        legacy = legacy_text()
        rc, rep = run_checker(tmp, legacy, good_cons_text(), base_manifest(legacy))
        assert rc == 0, rep["failures"]
        assert rep["pass"] is True and rep["failures"] == []
        assert all(c["match"] for c in rep["clusters"])
        assert all(h["match"] for h in rep["handoff_blocks"])


def test_fail_on_out_of_scope_edit():
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        legacy = legacy_text()
        bad = good_cons_text().replace("! header", "! header TAMPERED")
        rc, rep = run_checker(tmp, legacy, bad, base_manifest(legacy))
        assert rc == 1 and rep["pass"] is False
        assert any("outside the allowed set" in f or "drifted" in f
                   for f in rep["failures"]), rep["failures"]


def test_fail_on_drifted_pinned_edit():
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        legacy = legacy_text()
        drifted = good_cons_text().replace(
            "           qrs = qrs-dqr", "           qrs = qrs-dqr*1.0000001")
        rc, rep = run_checker(tmp, legacy, drifted, base_manifest(legacy))
        assert rc == 1 and rep["pass"] is False
        assert any("drifted" in f for f in rep["failures"]), rep["failures"]


def test_fail_on_legacy_sha_drift():
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        legacy = legacy_text() + "! legacy touched\n"
        manifest = base_manifest(legacy_text())   # pins the UNtouched legacy
        rc, rep = run_checker(tmp, legacy, good_cons_text(), manifest)
        assert rc == 1 and rep["pass"] is False
        assert any("sha256" in f for f in rep["failures"]), rep["failures"]


def test_fail_on_handoff_block_touch():
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        legacy = legacy_text()
        bad = good_cons_text().replace(
            "work1(i,k,1) = work1(i,k,1)/delz(i,k)",
            "work1(i,k,1) = work1(i,k,1)*dend(i,k)/delz(i,k)")
        rc, rep = run_checker(tmp, legacy, bad, base_manifest(legacy))
        assert rc == 1 and rep["pass"] is False
        assert any("handoff" in f for f in rep["failures"]), rep["failures"]


def test_real_manifest_structure():
    m = json.loads(REAL_MANIFEST.read_text())
    for key in ("legacy_sha256", "renames_cons_to_legacy",
                "allowed_edits", "handoff_blocks"):
        assert key in m, key
    for f in ("module_mp_kdm6.F", "module_mp_kdm6ad.F"):
        assert re.fullmatch(r"[0-9a-f]{64}", m["legacy_sha256"][f]), f
    # header-comment, decl-temporaries, sed-main-chain, sed-ice-chain — an
    # exact count so a silently-added "allowed" edit cannot pass unnoticed.
    assert len(m["allowed_edits"]) == 4
    assert [e["name"] for e in m["allowed_edits"]] == [
        "header-comment",
        "decl-interface-transfer-temporaries",
        "sed-main-chain (top cell + interior; qr/nr/brs/qs/qg)",
        "sed-ice-chain (top cell + interior; qi/ni)",
    ]
    assert len(m["handoff_blocks"]) == 2


def _selftest():
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as e:
                print(f"  FAIL {name}: {e}")
                fails += 1
    return fails


if __name__ == "__main__":
    sys.exit(1 if _selftest() else 0)
