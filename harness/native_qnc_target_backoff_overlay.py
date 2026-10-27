"""Render an isolated QNC/RK3 one-ULP donor-scale host probe.

The active private host source is read but never edited. This diagnostic is
limited to one native cell and does not define a general limiter correction.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


BASE_SHA256 = "234e39590fe2b864df8c1e038014e502cd0db662ebf2578dea41a60141dd09ec"
ANCHOR = (
    "     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN\n"
    "       scale = max(0.,ph_low(i,k,j)/(flux_out(i,k,j)+eps))\n"
    "     if (s15_here) s15_pd_scale=scale\n"
)
REPLACEMENT = (
    "     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN\n"
    "       scale = max(0.,ph_low(i,k,j)/(flux_out(i,k,j)+eps))\n"
    "       IF (qnc_trace_selected .AND. qnc_trace_rk.EQ.3 .AND. &\n"
    "           i.EQ.221 .AND. k.EQ.6 .AND. j.EQ.63 .AND. &\n"
    "           scale.GT.0. .AND. scale.LT.1.) scale=NEAREST(scale,-1.)\n"
    "     if (s15_here) s15_pd_scale=scale\n"
)
CONTEXT = (
    "qnc_trace_selected = .NOT.moist_step .AND. species .EQ. qnc_species &",
    "qnc_trace_rk = rk",
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def inject(source: str) -> str:
    if any(mark not in source for mark in CONTEXT) or source.count(ANCHOR) != 1:
        raise ValueError("pinned QNC context or positive-definite limiter site differs")
    return source.replace(ANCHOR, REPLACEMENT, 1)


def render(raw: bytes) -> bytes:
    if sha(raw) != BASE_SHA256:
        raise ValueError("private shared-face producer source SHA differs")
    result = inject(raw.decode("ascii")).encode("ascii")
    if result == raw:
        raise ValueError("backoff overlay made no change")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source
    output = args.output
    if output.exists() or output.is_symlink() or source.resolve() == output.resolve():
        raise FileExistsError("backoff probe requires a fresh output distinct from source")
    rendered = render(source.read_bytes())
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(rendered)
    print(json.dumps({"status": "TARGET_QNC_BACKOFF_OVERLAY_WRITTEN",
                      "source_sha256": BASE_SHA256, "overlay_sha256": sha(rendered),
                      "target_ijk_one_based": [221, 63, 6], "rk": 3,
                      "scale_operation": "NEAREST(scale,-1.) in original REAL kind"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
