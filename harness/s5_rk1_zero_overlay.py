#!/usr/bin/env python3
"""Opt-in RK1 zero-store candidate for the pinned private small-step source."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re


SOURCE_SHA = "cabf1a177d50fb0096db79644af20cfe6d75217dbe63ab406a7e29bb54c17634"
GUARD = "KDM6AD_S5_RK1_ZERO"
STORES = {
    "U": "      u_2(i,k,j) = ((c1h(k)*muus(i,j)+c2h(k))*u_1(i,k,j)-(c1h(k)*muu(i,j)+c2h(k))*u_2(i,k,j))/msfuy(i,j)\n",
    "V": "      v_2(i,k,j) = ((c1h(k)*muvs(i,j)+c2h(k))*v_1(i,k,j)-(c1h(k)*muv(i,j)+c2h(k))*v_2(i,k,j))*msfvx_inv(i,j)\n",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def block(name: str, original: str) -> str:
    variable = "u_2" if name == "U" else "v_2"
    return (f"#ifdef {GUARD}\n! S5_ZERO_BEGIN:{name}\n"
            "      IF (rk_step == 1) THEN\n"
            f"        {variable}(i,k,j) = 0.\n"
            "      ELSE\n"
            f"{original}"
            "      ENDIF\n"
            "#else\n"
            f"{original}"
            f"! S5_ZERO_END:{name}\n#endif\n")


def render(source: str) -> str:
    result = source
    for name, original in STORES.items():
        if result.count(original) != 1:
            raise ValueError(f"{name} RK store occurs {result.count(original)} times")
        result = result.replace(original, block(name, original), 1)
    return result


def strip(overlay: str) -> str:
    result = overlay
    for name, original in STORES.items():
        pattern = re.compile(
            rf"(?ms)^#ifdef {GUARD}\n! S5_ZERO_BEGIN:{name}\n"
            rf".*?^! S5_ZERO_END:{name}\n#endif\n")
        if len(pattern.findall(result)) != 1:
            raise ValueError(f"missing or duplicate {name} RK zero block")
        result = pattern.sub(original, result, count=1)
    if GUARD in result or "S5_ZERO_" in result:
        raise ValueError("orphan RK zero marker")
    return result


def generate(source: Path, output: Path) -> tuple[str, str]:
    raw = source.read_bytes()
    if sha(raw) != SOURCE_SHA:
        raise ValueError("private small-step source differs from the S5 pin")
    overlay = render(raw.decode("ascii"))
    if strip(overlay).encode("ascii") != raw:
        raise ValueError("RK candidate does not strip to the pinned source")
    output.write_text(overlay, encoding="ascii")
    return sha(raw), sha(overlay.encode("ascii"))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("output", type=Path)
    args = ap.parse_args()
    source_sha, overlay_sha = generate(args.source, args.output)
    print(f"source_sha256={source_sha}")
    print(f"overlay_sha256={overlay_sha}")


if __name__ == "__main__":
    main()
