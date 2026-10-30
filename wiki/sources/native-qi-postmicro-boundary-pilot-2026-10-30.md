# QI/NI post-microphysics boundary pilot, 2026-10-30

기존 QNC live guard를 유지한 격리 호스트에서, 미세물리·zero-out·finish 타일 루프 뒤 QI와 NI 각각에 원래 `flow_dep_bdy`를 다시 적용했다. α의 서쪽 표적 `(1,168,33)` QI는 `00000002→00000000`, NI는 0을 유지했고, 원래 고정 (M_0)의 53,906프로파일·377,342채널 셀 모두 hard moment 조건을 통과했다. Control도 손실 0이며, 두 사례의 pilot-on trace off/on 체크포인트가 같다. [수치·범위 보고서](../../docs/NATIVE_QI_POSTMICRO_BOUNDARY_PILOT_20261030.md) · [공개 패킷](../../harness/evidence/native_qi_postmicro_boundary_2026-10-30/README.md)

이 결과는 국소 값만의 변경이 아니다. 전 영역 원시비트 비교에서 Control QICE/QNICE 12,190/7,143개, α 12,183/7,142개가 바뀌고 모두 외곽 경계에 있다. 경계 덮어쓰기는 외부 증감이며 물리적 보존이나 KDM 미분 계약의 증거가 아니다. 이번 패킷에는 전체 (M_0) RTTOV 비용, 승인된 분석 또는 두 번째 동화가 없다. 넓은 경계 변화와 기존 host 광학 진단의 일관성, 실제 미분을 검증하기 전까지 opt-in 진단으로만 둔다.
