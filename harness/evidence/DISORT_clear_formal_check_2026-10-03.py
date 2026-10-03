import math
import numpy as np
from pathlib import Path

rows = [
    s.split()
    for s in (Path(__file__).parent / "DISORT_ir105_base_2026-10-03.tsv")
    .read_text()
    .splitlines()
]
b = np.array([float(r[2]) for r in rows if r[0] == "AIR"])
tau = np.array([float(r[11]) for r in rows if r[0] == "DOMLAYER" and r[1] == "0"])
meta = next(r for r in rows if r[0] == "META")
mu = float(meta[10])
alb = float(meta[12])
skin = float(meta[13])
cosmic = float(meta[14])


def layer(I, t, B0, B1, m):
    e = math.exp(-t / m)
    return I * e + B0 * (1 - e) + (B1 - B0) * (1 - m * (1 - e) / t)


def formal(n, clip=False):
    q, w = np.polynomial.legendre.leggauss(n // 2)
    q = (q + 1) / 2
    w = w / 2
    down = []
    for m in q:
        I = cosmic + b[0]
        for t, B0, B1 in zip(tau, b[:-1], b[1:]):
            I = layer(I, t, B0, B0 if clip and t <= 1e-4 else B1, m)
        down.append(I)
    I = skin + 2 * alb * np.dot(w * q, down)
    for t, B0, B1 in zip(tau[::-1], b[1:][::-1], b[:-1][::-1]):
        I = layer(I, t, B1 if clip and t <= 1e-4 else B0, B1, mu)
    return I


for n in (8, 16, 32, 64):
    print(n, formal(n), formal(n, True))
