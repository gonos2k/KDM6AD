# QI lower-owner outflow terms, 2026-10-30

남은 얼음 실패의 경계 donor `(2,168,33)` 아래 셀 `(2,168,32)`에서 limiter의 `FLUX_OUT` 여섯 면을 제한기 시작 전 실제 저장값으로 분해했다. Control의 아래쪽 수직 correction face는 양수 `01B121C9`라 정확한 저장 입력 식의 유출량에 약 `1.02038e-34`를 더한다. α의 같은 face는 음수 `8036BE12`여서 그 유출 항은 0이다. 다른 바뀐 PRE 면의 유출 기여 차이는 서쪽 X의 약 `−1.06e-47`뿐이다. Source-grouped f32 계산은 두 저장 `FLUX_OUT` 단어와 같은 `PH_LOW` 단어를 재현한다. [원시 실행·재생 패킷](../../harness/evidence/native_qi_outflow_terms_2026-10-30/README.md) · [수치 분석](../../docs/NATIVE_QI_OUTFLOW_TERMS_20261030.md)

k=32 수직 face의 low-order 값은 두 실행 모두 음의 0이고, 높은 차수 `flux3`에 들어가는 k=30·31 QI 입력과 `ROM`은 다르다. 저장 stencil의 분리/FMA 후보는 양쪽 PRE 단어와 양립하지만 실제 명령열을 특정하지 않는다. 네 완료 호스트 실행에서 trace off/on 체크포인트·ACK와 부모 기록이 같다. 이 계측은 수정 후보가 아니므로 α의 고정 (M_0)에는 얼음 한 프로파일·7채널 손실이 남아 있다. QI/NI 물리 수지, 일반 수정과 전체 RTTOV 비용은 미완료다.
