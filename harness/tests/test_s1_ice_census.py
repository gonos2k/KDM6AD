"""Fixed 40 s native selector-2 ice census."""

from hashlib import sha256
from pathlib import Path

from harness.replay_s1_dry_ice_faces import parse_host


HERE = Path(__file__).resolve().parents[1] / "evidence"
SHA = "b1f8dced9fcf9f2bd3a2e89b289e498b37eb1c1a66149d541f66832a49dbdd6c"


def test_all_expected_tile_calls_have_empty_ice_witness():
    path = HERE / "s1_ice_census_2026-09-30.log"
    assert sha256(path.read_bytes()).hexdigest() == SHA
    calls = parse_host(HERE / "s1_normalized_ice_tile_calls_2026-09-30.txt")
    rows = [line.split() for line in path.read_text().splitlines()]
    assert len(rows) == len(calls) == 4
    assert [c["step"] for c in calls] == [1, 1, 2, 2]
    assert sum(c["im"] * c["jm"] for c in calls) == 129920
    for seq, (row, call) in enumerate(zip(rows, calls), 1):
        assert len(row) == 12 and row[0] == "CENSUS"
        assert list(map(int, row[1:11])) == [
            seq, 1, call["im"] * call["jm"], 39,
            0, 0, 0, 0, -1, 1,
        ]
        assert float.fromhex(row[11]) == 0.0
