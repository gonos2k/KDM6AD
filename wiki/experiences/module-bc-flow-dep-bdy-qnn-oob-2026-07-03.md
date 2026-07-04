---
title: module_bc.F flow_dep_bdy_qnn OOB 버그 (np≥2 비재현·NaN의 근원)
type: experience
date_modified: 2026-07-03
provenance:
  sources:
    - BUGREPORT_module_bc_flow_dep_bdy_qnn.md (프로젝트 루트, 상세 리포트)
---
# module_bc.F flow_dep_bdy_qnn OOB 버그

KDM6/KDM6AD 공통(np≥2)의 run-to-run 비재현과 조건부 QNCCN NaN 폭주의 근원.
`flow_dep_bdy_qnn`(20250113 CCN 경계 프로파일 확장)의 3중 결함:
(1) `dz8w(i,j,k)` 전치 읽기(선언은 (i,k,j)) → 북단 랭크에서 배열 밖 3.5-5MB 힙 OOB,
(2) `xland` 더미 선언 `(ims:ime,kms:kme)` 오류 → j 접근 전부 OOB,
(3) z_sum이 컬럼별 적분이 아닌 행-누적 + 분기-조건부 누적.

판별 사다리: mp37 np2 자기재현 FAIL → WSM6 np2 PASS(호스트 결백) → 순정 빌드 FAIL →
numtiles=1 FAIL → NaN 최초 좌표 j=281(도메인 북단행) → 3축 코드 감사로 확정.
증폭기: [[KDM6]] `module_mp_kdm6.F:3219/:1966`의 FP-정확-동등 게이트(nc→nccn 전량 덤프).
오인 경로: mp137 래퍼 NaN 가드가 먼저 발화 + rank-abort의 소켓 연쇄 → "mp137 MPI 구조
결함"/"MPI 전송 문제"로 보였음 — 실제로는 업스트림 공용 경계 루틴 버그.

수정: 전치/선언/컬럼-적분 3종 (mp37·mp137 공용 경로 → 페어 bitwise 무손상).
상세: 프로젝트 루트 `BUGREPORT_module_bc_flow_dep_bdy_qnn.md`.
관련: [[KDM6AD Forward Parity]], [[kdm6ad-10step-bitwise-achieved-2026-07-02]]
