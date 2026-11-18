# QI donor transient, 2026-10-30

선택한 QNC 보정 뒤 남은 고정 (M_0) 한 프로파일의 빙상 불일치를 i=2 donor까지 되짚었다. Control·α의 QI donor는 RK1·RK2 후 음의 0이고 RK3 직전에도 같다. RK3 QI tendency 뒤에는 저장된 `ADVECT_TEND`가 control 0, α `000021A3`이며, RK3 QI 갱신은 각각 0과 subnormal `00000002`를 저장한다. 동일한 X-start 조건에서 그 단어가 i=1 표적에 복사된다. 뒤의 미세물리에서 α donor는 0이 되지만 표적은 `00000002`를 유지한다. [분석과 한계](../../docs/NATIVE_QI_DONOR_TRANSIENT_20261030.md) · [실행·원시 자료](../../harness/evidence/native_qi_donor_transient_2026-10-30/README.md)

네 호스트 실행의 trace off/on 체크포인트와 V7 부모 체크포인트는 같다. 저장 RK 피연산자의 정확 산술과 source-compatible f32 계산은 α의 donor 출력 `00000002`를 재현한다. 아직 그 양의 이류 경향을 만드는 면별 항, 물리적 QI/NI 수지, 수정된 host map의 JVP/VJP는 확인하지 않았다. 전체 (M_0)에서는 얼음 한 프로파일·7채널이 계속 탈락하므로 RTTOV 전체 비용과 분석 수용은 보류다.
