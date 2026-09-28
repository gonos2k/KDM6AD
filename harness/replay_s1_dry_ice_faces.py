"""Replay the fixed 40 s S1 ice-face capture; no private host is required."""

import argparse
import hashlib
import json
import math
import re
import struct
from fractions import Fraction
from pathlib import Path

FIELDS = (
    "q_before",
    "falk_q",
    "dq_out",
    "dq_in",
    "q_after",
    "n_before",
    "falk_n",
    "dn_out",
    "dn_in",
    "n_after",
    "dz_raw",
    "dz_safe",
    "dend_raw",
    "dend_safe",
    "mstep",
    "gate",
)
F = Fraction.from_float
TARGET_I, TARGET_J, TARGET_B, EXPECTED_K = 144, 153, 19748, 39
HERE = Path(__file__).resolve().parent / "evidence"
TRACE_SHA = "c82053d25a423a444d725c98a0c9af4718eacdd6cebd21134d011b76b13b7ff3"
TILE_SHA = "97ad7757681d5d0bd3ae183949a2271028385ce12d5955b245257e094c10358b"


def pinned(path, expected):
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected


def bits(x):
    return struct.pack(">f", x)


def f32(x):
    return struct.unpack(">f", bits(x))[0]


def parse_trace(path):
    pinned(path, TRACE_SHA)
    blocks, block = [], None
    for lineno, raw in enumerate(Path(path).read_text().splitlines(), 1):
        tok = raw.split()
        if not tok:
            continue
        if tok[:2] == ["BEGIN", "ice"]:
            assert block is None and len(tok) == 7, (lineno, tok)
            block = dict(
                seq=int(tok[2]),
                n=int(tok[3]),
                b=int(tok[4]),
                K=int(tok[5]),
                dt=float.fromhex(tok[6]),
                rows=[],
            )
        elif tok[0] == "ROW":
            assert block is not None and len(tok) == 18, (lineno, len(tok))
            k = int(tok[1])
            values = [float.fromhex(v) for v in tok[2:]]
            assert k == len(block["rows"])
            assert all(math.isfinite(v) for v in values)
            block["rows"].append(dict(zip(FIELDS, values)))
        elif tok == ["END", "ice"]:
            assert block is not None and len(block["rows"]) == block["K"]
            blocks.append(block)
            block = None
        else:
            raise ValueError((lineno, tok[:5]))
    assert block is None and blocks
    assert [b["seq"] for b in blocks] == list(range(1, len(blocks) + 1))
    assert all(b["b"] == TARGET_B and b["K"] == EXPECTED_K for b in blocks)
    return blocks


def parse_host(path):
    pinned(path, TILE_SHA)
    calls = []
    for line in Path(path).read_text(errors="replace").splitlines():
        m = re.search(r"\bS1_TILE_CALL\s+((?:\d+\s+){8}\d+)\b", line)
        if m:
            v = list(map(int, m.group(1).split()))
            calls.append(
                dict(
                    zip(("seq", "its", "ite", "jts", "jte", "im", "jm", "step", "b"), v)
                )
            )
    assert calls and [c["seq"] for c in calls] == list(range(1, len(calls) + 1))
    assert all(c["b"] == TARGET_B and c["im"] * c["jm"] > TARGET_B for c in calls)
    return calls


def group_blocks(blocks):
    groups = []
    for b in blocks:
        if b["n"] == 1:
            groups.append([])
        assert groups and b["n"] == len(groups[-1]) + 1
        groups[-1].append(b)
    return groups


def main():
    if not __debug__:
        raise SystemExit("assertions are required for evidence replay")
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "trace", nargs="?", default=HERE / "s1_dry_ice_face_trace_2026-09-28.log"
    )
    ap.add_argument(
        "rsl", nargs="?", default=HERE / "s1_dry_ice_tile_calls_2026-09-28.txt"
    )
    ap.add_argument("--out")
    a = ap.parse_args()
    blocks = parse_trace(a.trace)
    calls = parse_host(a.rsl)
    groups = group_blocks(blocks)
    assert len(calls) == len(blocks) == len(groups) == 4
    assert [c["step"] for c in calls] == [1, 1, 2, 2]
    targets = []
    for c, g in zip(calls, groups):
        owns = c["its"] <= TARGET_I <= c["ite"] and c["jts"] <= TARGET_J <= c["jte"]
        if owns:
            mapped = (TARGET_I - c["its"]) * c["jm"] + (TARGET_J - c["jts"])
            assert mapped == TARGET_B, (mapped, c)
            targets.append((c, g))
    assert len(targets) == 2 and len({c["step"] for c, _ in targets}) == 2
    assert all(
        sum(
            c["its"] <= TARGET_I <= c["ite"] and c["jts"] <= TARGET_J <= c["jte"]
            for c in calls
            if c["step"] == step
        )
        == 1
        for step in {c["step"] for c, _ in targets}
    )
    selected = []
    for c, g in targets:
        for b in g:
            rows = b["rows"]
            dt = b["dt"]
            failures = []
            faces = []
            caps_n = 0
            caps_q = 0
            assert math.isfinite(dt) and dt > 0
            for k, r in enumerate(rows):
                assert r["dz_raw"] > 0 and r["dend_raw"] > 0
                assert r["dz_raw"] == r["dz_safe"] and r["dend_raw"] == r["dend_safe"]
                assert r["mstep"] >= 1 and r["gate"] in (0, 1)
                n_offer = f32(r["falk_n"] * dt)
                q_offer = f32(f32(r["falk_q"] * dt) / r["dend_safe"])
                if bits(r["dn_out"]) != bits(min(n_offer, r["n_before"])):
                    failures.append((k, "n_cap"))
                if bits(r["dq_out"]) != bits(min(q_offer, r["q_before"])):
                    failures.append((k, "q_cap"))
                caps_n += n_offer > r["n_before"] and r["n_before"] > 0
                caps_q += q_offer > r["q_before"] and r["q_before"] > 0
                n_post = (
                    f32(r["n_before"] - r["dn_out"])
                    if k == 0
                    else f32(f32(r["n_before"] - r["dn_out"]) + r["dn_in"])
                )
                q_post = (
                    f32(r["q_before"] - r["dq_out"])
                    if k == 0
                    else f32(f32(r["q_before"] - r["dq_out"]) + r["dq_in"])
                )
                if bits(n_post) != bits(r["n_after"]):
                    failures.append((k, "n_update"))
                if bits(q_post) != bits(r["q_after"]):
                    failures.append((k, "q_update"))
                if k == 0:
                    assert r["dn_in"] == 0 and r["dq_in"] == 0
                else:
                    prev = rows[k - 1]
                    n_in = f32(f32(prev["dn_out"] * prev["dz_raw"]) / r["dz_safe"])
                    m_src = f32(prev["dend_safe"] * prev["dz_raw"])
                    m_dst = f32(r["dend_safe"] * r["dz_safe"])
                    q_in = f32(f32(prev["dq_out"] * m_src) / m_dst)
                    if bits(n_in) != bits(r["dn_in"]):
                        failures.append((k, "n_face_replay"))
                    if bits(q_in) != bits(r["dq_in"]):
                        failures.append((k, "q_face_replay"))
                    dn_face = F(r["dn_in"]) * F(r["dz_safe"]) - F(prev["dn_out"]) * F(
                        prev["dz_raw"]
                    )
                    dq_face = F(r["dq_in"]) * F(r["dend_safe"]) * F(r["dz_safe"]) - F(
                        prev["dq_out"]
                    ) * F(prev["dend_safe"]) * F(prev["dz_raw"])
                    faces.append((float(dn_face), float(dq_face)))
            dn_delta = sum(
                (F(r["n_after"]) - F(r["n_before"])) * F(r["dz_raw"]) for r in rows
            )
            dq_delta = sum(
                (F(r["q_after"]) - F(r["q_before"])) * F(r["dend_raw"]) * F(r["dz_raw"])
                for r in rows
            )
            n_bottom = F(rows[-1]["dn_out"]) * F(rows[-1]["dz_raw"])
            q_bottom = (
                F(rows[-1]["dq_out"]) * F(rows[-1]["dend_raw"]) * F(rows[-1]["dz_raw"])
            )
            n_out = sum(F(r["dn_out"]) * F(r["dz_raw"]) for r in rows[:-1])
            n_in = sum(F(r["dn_in"]) * F(r["dz_safe"]) for r in rows[1:])
            q_out = sum(
                F(r["dq_out"]) * F(r["dend_safe"]) * F(r["dz_raw"]) for r in rows[:-1]
            )
            q_in = sum(
                F(r["dq_in"]) * F(r["dend_safe"]) * F(r["dz_safe"]) for r in rows[1:]
            )
            selected.append(
                dict(
                    step=c["step"],
                    host_call=c["seq"],
                    ice_seq=b["seq"],
                    n=b["n"],
                    mstep=rows[0]["mstep"],
                    gate=rows[0]["gate"],
                    positive_ice_faces=sum(r["dn_out"] > 0 for r in rows[:-1]),
                    capped_n=caps_n,
                    capped_q=caps_q,
                    failures=failures,
                    number_departure=float(n_out),
                    number_arrival=float(n_in),
                    number_interface_relative=float((n_in - n_out) / n_out)
                    if n_out
                    else 0.0,
                    mass_departure=float(q_out),
                    mass_arrival=float(q_in),
                    mass_interface_relative=float((q_in - q_out) / q_out)
                    if q_out
                    else 0.0,
                    max_number_face_residual=max((abs(x) for x, _ in faces), default=0),
                    max_mass_face_residual=max((abs(y) for _, y in faces), default=0),
                    number_inventory_residual=float(dn_delta + n_bottom),
                    mass_inventory_residual=float(dq_delta + q_bottom),
                    number_bottom=float(n_bottom),
                    mass_bottom=float(q_bottom),
                )
            )
    result = dict(
        scope="fixed_capture_arithmetic_replay_only",
        s1_gate_closed=False,
        total_host_calls=len(calls),
        total_ice_blocks=len(blocks),
        selected_ice_blocks=len(selected),
        selected=selected,
    )
    print(json.dumps(result, indent=2))
    if a.out:
        Path(a.out).write_text(json.dumps(result, indent=2) + "\n")
    assert any(x["positive_ice_faces"] for x in selected), (
        "no nonzero ice transfer measured"
    )
    assert not any(x["failures"] for x in selected), "source arithmetic replay failed"


if __name__ == "__main__":
    main()
