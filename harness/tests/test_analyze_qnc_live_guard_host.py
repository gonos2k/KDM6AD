from __future__ import annotations

import hashlib
import json
import shutil

import pytest

from harness.analyze_qnc_live_guard_host import PACKET, analyze


def test_replay_rejects_one_sided_live_face_change_even_with_updated_trace_receipt(tmp_path):
    copy = tmp_path / "packet"
    shutil.copytree(PACKET, copy, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    path = copy / "data/control/faces.tsv"
    lines = path.read_text().splitlines()
    header = next(line for line in lines if line.startswith("# VAL ")).split()[1:]
    face_index = header.index("FX_POST_EAST")
    target = "VAL 1 20 20 3 91 4 94 "
    matches = [n for n, line in enumerate(lines) if line.startswith(target)]
    assert len(matches) == 1
    parts = lines[matches[0]].split()
    parts[face_index] = f"{int(parts[face_index], 16) ^ 1:08X}"
    lines[matches[0]] = " ".join(parts)
    path.write_text("\n".join(lines) + "\n")

    execution_path = copy / "receipts/execution_summary.json"
    receipt = json.loads(execution_path.read_text())
    receipt["runs"]["control"]["on"]["trace_files_sha256"]["qnc_candidate_faces"] = (
        hashlib.sha256(path.read_bytes()).hexdigest())
    execution_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    with pytest.raises(ValueError, match="applied shared face differs"):
        analyze(copy)
