"""Offline replay of the native QI donor transient packet."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
import sys


PACKET = Path(__file__).resolve().parent
REPO = PACKET.parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
MANIFEST = PACKET / "manifest.json"


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    item = Path(relative)
    if item.is_absolute() or ".." in item.parts:
        raise ValueError("unsafe QI donor path")
    path = root / item
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("QI donor path escapes its root")
    return path


def _verify_files(root: Path, expected: dict[str, str]) -> None:
    if not isinstance(expected, dict) or not expected:
        raise ValueError("empty QI donor source inventory")
    for relative, digest in expected.items():
        if sha(_safe_file(root, relative).read_bytes()) != digest:
            raise ValueError(f"QI donor source/data changed: {relative}")


def main() -> int:
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema") != "kdm6.native_qi_donor_transient_manifest.v1":
        raise ValueError("QI donor manifest schema differs")
    _verify_files(PACKET, manifest["packet_files_sha256"])
    _verify_files(REPO, manifest["external_source_pins"])
    _verify_files(REPO, manifest["upstream_manifest_pins"])
    parent = importlib.import_module(
        "harness.evidence.native_qnc_live_guard_2026-10-30.replay")
    parent.main()
    from harness.analyze_qi_donor_transient import analyze  # noqa: PLC0415

    result = analyze(PACKET)
    raw = (json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if raw != (PACKET / "analysis.json").read_bytes():
        raise ValueError("QI donor analysis differs from published bytes")
    print("REPLAY_PASSED")
    print("analysis_sha256:")
    print(sha(raw))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
