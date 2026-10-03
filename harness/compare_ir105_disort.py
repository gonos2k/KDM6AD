"""Replay the frozen C5 IR105 transport boundary with optional pydisort 1.8.13.

Same optical tables and channel sources; an independent RTE implementation,
not independent spectroscopy or physical approval. This is a case tool.
"""

import argparse
import ctypes, json, math
from pathlib import Path
import torch
from pydisort import Disort, DisortOptions
import pydisort

ROOT = Path(pydisort.__file__).parent
library = next(iter(sorted((ROOT / "lib").glob("libdisort_release.*"))), None)
if library is None:
    raise RuntimeError("pydisort shared library unavailable")
lib = ctypes.CDLL(str(library))
p = lib.c_planck_func2
p.argtypes = [ctypes.c_double] * 3
p.restype = ctypes.c_double
# A fixed narrow band is only a numerical carrier for matched channel Planck radiances.
scale = 0.001


def temperature(b):
    lo, hi = 0.0, 2000.0
    for _ in range(65):
        mid = (lo + hi) / 2
        if p(900.0, 901.0, mid) < b * scale:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def read_capture(path):
    rows = [line.split() for line in Path(path).read_text().splitlines()]
    for tag, width, expected in (
        ("META", 0, [()]),
        ("AIR", 1, [(i,) for i in range(1, 65)]),
        ("CLOUD", 1, [(0,), (1,)]),
        ("DOMLAYER", 2, [(c, i) for c in (0, 1) for i in range(1, 64)]),
        ("MOMENT", 4, [(1, 59, 1, l) for l in range(32)]),
    ):
        keys = [tuple(map(int, r[1 : 1 + width])) for r in rows if r[0] == tag]
        if keys != expected:
            raise ValueError(f"Missing, repeated or reordered {tag} records")
    return rows


def check_endpoints(base, plus, minus):
    def fixed(rows):
        return [
            r if r[0] in ("META", "AIR", "CLOUD") else r[:5]
            for r in rows
            if r[0] in ("META", "AIR", "CLOUD", "DOMLAYER")
        ]

    if fixed(base) != fixed(plus) or fixed(base) != fixed(minus):
        raise ValueError("Endpoints change the frozen source/boundary/layer layout")


def run(path, n):
    rows = read_capture(path)
    meta = next(r for r in rows if r[0] == "META")
    mu, albedo, skin, cosmic = (
        float(meta[10]),
        float(meta[12]),
        float(meta[13]),
        float(meta[14]),
    )
    air_rows = [r for r in rows if r[0] == "AIR"]
    air = [float(r[2]) for r in air_rows]
    if [int(r[1]) for r in air_rows] != list(range(1, 65)):
        raise ValueError("Missing, repeated or reordered Planck levels")
    if tuple(map(int, meta[1:5])) != (13, 6, 6, 1) or len(air) != 64:
        raise ValueError(
            "Expected declared IR105/internal 6/profile 1, 64 Planck levels"
        )
    if tuple(map(int, meta[5:10])) != (32, 31, 63, 1, 1) or not 0 < mu <= 1:
        raise ValueError("Unexpected frozen solver setup or viewing cosine")
    if n not in (8, 16, 32):
        raise ValueError("Only retained moment orders 8, 16, 32 are supported")
    if (
        not all(math.isfinite(b) and b >= 0 for b in air + [skin, cosmic])
        or not 0 <= albedo < 1
    ):
        raise ValueError("Invalid Planck source or surface reflectance")
    total = 0.0
    detail = []
    for c in (0, 1):
        layers = [r for r in rows if r[0] == "DOMLAYER" and int(r[1]) == c]
        if [int(r[2]) for r in layers] != list(range(1, 64)):
            raise ValueError("Incomplete frozen 63-layer subcolumn")
        props = torch.zeros((1, 1, len(layers), n + 2), dtype=torch.float64)
        for k, r in enumerate(layers):
            # layer_od is post floor and pre delta-M; SSA is unscaled.
            props[0, 0, k, 0] = float(r[11])
            props[0, 0, k, 1] = float(r[7]) if int(r[3]) else 0.0
            # Clear map zero consumes fssa(0)=0; raw SSA may be unused/stale.
            lm = int(r[3])
            moments = {
                int(s[4]): float(s[5]) / (2 * int(s[4]) + 1)
                for s in rows
                if s[0] == "MOMENT" and int(s[1]) == c and int(s[2]) == lm
            }
            for l in range(1, n + 1):
                props[0, 0, k, l + 1] = (
                    float(r[8]) if l == 32 else moments[l] if lm else 0.0
                )
        if (
            not torch.isfinite(props).all()
            or (props[..., 0] <= 0).any()
            or (props[..., 1] < 0).any()
            or (props[..., 1] >= 1).any()
        ):
            raise ValueError("Invalid tau/SSA")
        absorption_tau = (props[0, 0, :, 0] * (1 - props[0, 0, :, 1])).sum().item()
        if absorption_tau >= 10:
            raise ValueError("C-DISORT absorption cutoff would change this comparison")
        # C-DISORT is top-down; upward=0 avoids reversing the captured arrays.
        op = (
            DisortOptions()
            .flags("lamber,planck,usrang,quiet")
            .nwave(1)
            .ncol(1)
            .upward(0)
        )
        op.ds().nlyr = len(layers)
        op.ds().nstr = n
        op.ds().nmom = n
        op.ds().nphase = n
        op.user_mu([mu]).user_phi([0.0]).wave_lower([900.0]).wave_upper([901.0])
        ds = Disort(op)
        t = lambda x: torch.tensor(x, dtype=torch.float64)
        ds.forward(
            props,
            temf=t([[temperature(b) for b in air]]),
            btemp=t([temperature(skin / (1 - albedo))]),
            ttemp=t([temperature(air[0])]),
            albedo=t([[albedo]]),
            temis=t([[1.0]]),
            fisot=t([[cosmic * scale]]),
            fbeam=t([[0.0]]),
            fluor=t([[0.0]]),
            umu0=t([1.0]),
            phi0=t([0.0]),
        )
        rad = ds.gather_rad()[0, 0, 0, 0, 0].item() / scale
        weight = float(next(r for r in rows if r[0] == "CLOUD" and int(r[1]) == c)[4])
        if not math.isfinite(rad) or weight < 0:
            raise ValueError("Invalid solver output/weight")
        total += weight * rad
        detail.append(
            {
                "column": c,
                "weight": weight,
                "radiance": rad,
                "tau": props[0, 0, :, 0].sum().item(),
                "absorption_tau": (props[0, 0, :, 0] * (1 - props[0, 0, :, 1]))
                .sum()
                .item(),
            }
        )
    if not math.isclose(sum(item["weight"] for item in detail), 1.0, abs_tol=1e-14):
        raise ValueError("Incomplete cloud-column weights")
    return {"streams": n, "radiance": total, "columns": detail}


def bt(rad):
    # Exact IR105 values from the pinned RTTOV coefficient file's FILTER_FUNCTIONS.
    wn, offset, slope = 966.1533839, 0.1026489494, 0.9996594440
    return (
        1.438776878 * wn / math.log1p(1.191042972e-5 * wn**3 / rad) - offset
    ) / slope


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--plus", type=Path)
    parser.add_argument("--minus", type=Path)
    parser.add_argument("--h", type=float, default=1e-4)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if bool(args.plus) != bool(args.minus) or not math.isfinite(args.h) or args.h <= 0:
        parser.error("Provide both endpoints and a positive finite h")
    if args.plus:
        check_endpoints(
            read_capture(args.base), read_capture(args.plus), read_capture(args.minus)
        )
    results = []
    for n in (8, 16, 32):
        result = run(args.base, n)
        result["bt_k"] = bt(result["radiance"])
        if args.plus:
            plus, minus = run(args.plus, n), run(args.minus, n)
            result["nc_direction_bt_fd"] = (
                bt(plus["radiance"]) - bt(minus["radiance"])
            ) / (2 * args.h)
            result["plus_radiance"] = plus["radiance"]
            result["minus_radiance"] = minus["radiance"]
        results.append(result)
    args.output.write_text(
        json.dumps(
            {
                "scope": "same-optics independent RTE implementation; no physical/observation approval",
                "results": results,
            },
            indent=2,
        )
        + "\n"
    )
