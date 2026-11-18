# QI post-microphysics pilot direct M0 cost, 2026-10-30

격리된 QI/NI 경계 pilot의 실제 Control·α 체크포인트를 원래 129개 B512 블록에서 RTTOV direct로 평가했다. 두 사례 각각 129호출·K 0호출이며, 원래 M0의 53,906프로파일·377,342채널 셀이 전부 유효하다. 같은 관측·마스크의 Huber 비용은 원래 Control **11.007963317242059**, pilot Control **11.008295588872157**, pilot α **11.007331464977474**이고, pilot α−Control은 **−0.0009641238946827002**다. [수치·한계 보고서](../../docs/NATIVE_QI_POSTMICRO_DIRECT_M0_20261030.md) · [258개 호출 자료 재현 패킷](../../harness/evidence/native_qi_postmicro_direct_m0_2026-10-30/README.md)

얼음 경계 표적 `(1,168)`의 IR105 BT는 세 결과 모두 295.086844603 K로 같으므로 `QI=2u→0` 지원 회복 자체에 국소 BT 개선을 배정할 수 없다. Pilot α는 원래 Control 대비 M0의 48,257프로파일에서 BT가 바뀐다. 비용은 관측 공간 진단이며, 넓은 경계 QICE/QNICE 덮어쓰기의 물리 수지·단위, host 얼음 진단 일관성 및 새 경계 연산의 미분 계약을 입증하지 않는다. 관측 bundle 00:00 명목 시각과 모델 00:01:00, 미확인 pixel UTC 조건도 유지한다. 분석 수용·두 번째 동화는 아직 없다.
