# 남은 QI 실패: donor의 첫 subnormal 생성 경계

선택한 QNC 보정 호스트는 액체 실패 53개 프로파일을 회복했지만, `(i,j,k)=(1,168,33)`의 QI/NI 한 프로파일·7채널을 잃는다. 앞선 경계 기록은 i=1 표적이 i=2 donor의 QI `00000002`를 복사한다는 데까지 도달했다. 이번에는 그 donor를 control·α의 RK1/2/3 QI 갱신과 미세물리 전후에서 같이 기록했다. [공개 원시 기록과 재생](../harness/evidence/native_qi_donor_transient_2026-10-30/README.md)

네 번의 20초 전체 호스트 실행에서 trace off/on 및 이전 V7 체크포인트 해시가 사례별로 같다. 새 계측은 `solve_em.o`만 바꾸고 QNC face/RK 기록도 이전 V7과 바이트 단위로 같다. 다음 결과는 **실행 중 기록한 raw f32 값**이며 QI의 물리적 질량 수지를 완성한 것은 아니다.

| `(2,168,33)` donor | Control | α=0.25 |
| --- | --- | --- |
| RK1·RK2 후 QI | 음의 0 | 음의 0 |
| RK3 QI 갱신 직전 | 음의 0 | 음의 0 |
| RK3 QI tendency 호출 후 `ADVECT_TEND` | 0 | **`000021A3`** |
| RK3 QI 갱신 직후 | 0 | **`00000002`** |
| 미세물리 후 donor QI | 0 | 0 |

RK3의 두 실행은 저장된 `MOIST_OLD=0`, `MOIST_TEND=0`, `MSFTY`와 `DT_RK`가 같다. `MU_NEW` 비트는 다르지만 `C1H=−0`, `C2H=95000`이므로 정확 산술 old/new 질량 계수는 양쪽 모두 95000이다. 저장 피연산자를 정확 실수로 해석한 α 갱신값은 subnormal ULP의 **약 1.76214배**이며, 최근접 짝수 f32 반올림과 source-compatible separate 연산은 모두 `00000002`를 준다. 이번 기록에서 QI 결과의 첫 비트 차이는 RK3 QI 갱신 직후, 그 입력 경향의 첫 차이는 RK3 tendency 호출 뒤다. 실제 컴파일된 FMA 명령열이나 `ADVECT_TEND=000021A3`을 만든 면별 항을 식별한 것은 아니다.

RK3 경계 호출은 두 실험에서 모두 발생했다. `specified=true`, `have_bcs_moist=false`, `periodic_x=false`, `spec_zone=1`이며, i=1의 같은 음수 `ru_m` 조건에서 i=2 donor가 선택된다. Control은 0을, α는 `00000002`를 표적에 복사한다. α의 donor는 뒤의 미세물리 구간에서 0이 되지만 경계 표적은 `00000002`가 남는다. 따라서 READY40과 최종 donor가 모두 0이라는 사실만으로 중간 값이 없었다고 판단하면 안 된다.

QI 루프에서 같이 읽은 NI는 그 뒤 scalar 루프의 동시 RK 갱신 결과가 아니다. 최종 체크포인트의 NI=0은 별도 확인값이다. 이번 근거로 subnormal QI를 일괄 삭제하거나 기존 (M_0) 조건을 느슨하게 만들 수 없다. 다음에는 RK3 QI 이류 경향을 구성한 **실제 면·제한계수와 양쪽 셀의 적용량**을 기록해 이 작은 양수의 수치·질량 수지를 설명한 뒤 수정 후보의 물리·미분 계약을 검토해야 한다. 전체 (M_0)가 유지되기 전에는 전체 RTTOV 비용이나 분석 수용으로 진행하지 않는다.
