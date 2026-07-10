"""CVT FD 검증 하니스 (tests 전용) — 도출된 허용오차 + 매끄러움 자기검증.

고정 상수 허용오차(1e-5) 단독 대신: FD 반올림 바닥(noise)을 J 크기에서 도출하고,
h와 h/2의 중앙차분이 서로 일치하는지 먼저 검사한다(창을 관통해 합성된 kink에
프로브가 걸리면 flaky 대신 즉시 시끄럽게 실패 → 프로브 지점을 옮기라는 신호).
기울기 게이트는 계층형: FD가 지지하는 곳은 1e-5 상대, 그 아래는 noise 절대.
"""
from __future__ import annotations

from kdm6.da_cvt import U64


def fd_check(j_fn, v0, idx, g_val, *, h=1.0e-5) -> str:
    """∂J/∂v[idx] 해석해 g_val을 중앙 FD로 대조. 반환 "strong"|"weak" 계층.

    j_fn: v(텐서) -> float J.  프로브가 비매끄러우면 AssertionError (이동 요망).
    """
    def probe(hh):
        vp = v0.clone(); vp[idx] += hh
        vm = v0.clone(); vm[idx] -= hh
        jp, jm = j_fn(vp), j_fn(vm)
        return (jp - jm) / (2.0 * hh), max(abs(jp), abs(jm))

    fd_h, jmax_h = probe(h)
    fd_h2, jmax_h2 = probe(h / 2.0)
    noise = 100.0 * U64 * max(jmax_h, jmax_h2) / (2.0 * h)
    assert abs(fd_h - fd_h2) <= max(1.0e-4 * abs(fd_h), 3.0 * noise), (
        "probe non-smooth — move the probe point", idx, fd_h, fd_h2, noise)
    assert abs(g_val - fd_h) <= max(1.0e-5 * abs(fd_h), 2.0 * noise), (
        idx, g_val, fd_h, noise)
    return "strong" if 1.0e-5 * abs(fd_h) > 2.0 * noise else "weak"
