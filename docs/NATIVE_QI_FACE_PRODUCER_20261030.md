# 남은 QI 경향의 적용 면과 limiter 분기

이전 QI donor 기록은 `(i,j,k)=(2,168,33)`에서 α의 RK3 `ADVECT_TEND=000021A3`이 저장되고 QI `00000002`가 된다는 데까지 연결했다. 이번에는 **그 경향을 만드는 실제 제한 후 면**을 기록했다. Control·α 각각 trace off/on의 네 20초 호스트 실행은 대응하는 이전 체크포인트와 ACK가 같고, 기존 QI donor·QNC face/RK 기록도 바이트 단위로 유지됐다. [공개 패킷](../harness/evidence/native_qi_face_producer_2026-10-30/README.md)

Donor의 제한 전 correction 여섯 면, low-order 여섯 면, `FIELD`·`FIELD_OLD`, 질량·metric·시간 입력은 두 실험에서 원시 비트까지 같다. 달라진 적용 면은 **아래쪽 수직 correction face 하나**다.

| 값 | Control | α=0.25 |
| --- | --- | --- |
| 아래 correction face PRE | `80000060` | `80000060` |
| 아래 LOW | 음의 0 | 음의 0 |
| 아래 correction face POST | **음의 0** | **`80000060`** |
| 아래 이웃 `(2,168,32)`의 `PH_LOW` | `01821C4D` | 동일 |
| 같은 이웃의 `FLUX_OUT` | `0707A41E` | `004C147C` |
| 같은 이웃의 limiter | 활성, scale `22B0552B` | 비활성, scale 1 |
| Donor의 Z 직후 `ADVECT_TEND` | 0 | **`000021A3`** |

아래 이웃 k=32에서 이 면은 위쪽 outgoing correction이다. Control은 `FLUX_OUT>PH_LOW`이므로 scale을 곱하고, 그 결과가 f32 음의 0으로 반올림된다. α는 `FLUX_OUT<PH_LOW`라 제한기를 통과하지 않아 같은 PRE face를 그대로 적용한다. 실제 저장된 면과 `RDZW`로 계산한 α의 Z 기여는 정확 산술에서 subnormal ULP **8611.28173828125개**이고, source-compatible f32 순서의 결과 `000021A3`은 실제 Z 직후·최종 RK 입력의 단어와 같다. X·Y 방향 계산은 그 저장 단어를 바꾸지 않는다.

따라서 이번 선택 지점의 QI 양수는 **donor 자체의 limiter scale 또는 마지막 RK 저장만으로 설명되지 않는다.** 아래 이웃의 limiter branch가 달라진 뒤 수직 공유면의 적용값이 갈린다. 서쪽 경계 i=1은 이 QI limiter 평가 범위 밖이라 owner가 `SEEN=false`로 기록되며, 그 셀의 미계산 `PH_LOW`를 수지에 넣지 않았다.

남은 상류 질문은 아래 이웃의 `FLUX_OUT` 차이를 만든 **그 셀의 여섯 면과 높은 차수 수직 flux의 stencil·속도**다. 이 패킷은 donor 면만 기록했으므로 그 합을 독립 분해하거나 물리적 QI/NI 질량·수량 보존을 주장할 수 없다. 같은 경계 복사 뒤 α donor는 미세물리에서 0이 되지만 표적은 `00000002`가 남는다는 이전 관찰도 유지된다. 임의의 subnormal 제거 또는 QNC scale을 QI에 적용하는 수정은 여기서 정당화되지 않는다.

현재 α는 원래 고정 (M_0)의 얼음 1개 프로파일·7채널을 잃는다. 다음 수정 후보는 아래 이웃의 실제 유출·가용량과 수신 셀, QI/NI 쌍, 경계 적용량, 반올림 및 미분 계약을 함께 설명한 뒤 실행해야 한다. 전체 (M_0)가 유지되기 전에는 직접 RTTOV 전체 비용, 분석 수용이나 두 번째 동화를 주장하지 않는다.
