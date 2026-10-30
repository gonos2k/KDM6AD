# QI/NI 경계 진단의 원래 고정 M0 직접 관측 비용

[미세물리 이후 QI/NI 경계 재적용](NATIVE_QI_POSTMICRO_BOUNDARY_PILOT_20261030.md)은 실제 호스트 체크포인트에서 α=0.25의 마지막 얼음 hard-moment 실패를 없앴다. 이번에는 **그 Control과 α 체크포인트에서 직접 RTTOV를 실행**해 원래 고정 M0의 53,906프로파일·377,342채널 셀을 모두 평가했다. 원래 Control의 공개 관측 배열을 같은 관측·마스크 기준으로 놓았다. [호출 자료와 오프라인 재현](../harness/evidence/native_qi_postmicro_direct_m0_2026-10-30/README.md)

두 사례 각각 원래 순서의 B512 블록 128개와 마지막 B452 한 개에서 direct 호출 **129회**, 총 **258회**를 완료했다. K 호출, 새 호스트 스텝, KDM 및 optimizer 호출은 이 관측 실행에서 0회다. 모든 원래 M0 셀에서 현재 프로파일 입력·RTTOV 품질이 유효하고 BT가 유한했다. 따라서 이 **진단 후보에 대해서는 전체 고정 지원 집합의 direct 비용이 정의된다.** 공개된 258개 attempt/result/capture 파일을 해시로 대조하고 전체 배열을 다시 구성한 뒤, 별도 산술 replay에서 Huber 합산을 재계산했다.

| 같은 관측·원래 M0의 Huber 비용 | 비용 | 원래 Control 대비 |
| --- | ---: | ---: |
| 원래 Control baseline | **11.007963317242059** | 0 |
| QNC guard + 경계 pilot Control | **11.008295588872157** | **+0.000332271630098191** |
| QNC guard + 경계 pilot α=0.25 | **11.007331464977474** | **−0.000631852264584509** |

**같은 pilot 규칙을 적용한 α−Control 비용 차이는 −0.0009641238946827002**다. 이는 원래 baseline 대비 차이와 다른 비교다. Huber의 선언값은 residual bias 0 K, scale 1 K, 전환점 1 K이며, 분자는 채널별·블록별 `math.fsum` 순서로 합산한 뒤 377,342셀로 나눈다. 원래 baseline 분자 `4,153,766.894054753`과 비용도 공개 배열에서 정확히 재현했다.

## BT 변화와 비교 기준

원래 Control 대비 pilot Control의 BT 비트가 달라진 M0 프로파일은 **11개·77채널 셀**이다. Pilot α는 **48,257개·337,714채널 셀**에서 달라진다. 따라서 영역 비용 차이를 경계의 한 얼음 셀에 귀속할 수 없다. [별도 BT 진단](../harness/evidence/native_qi_postmicro_direct_m0_2026-10-30/observation_diagnostics.json)

| IR105 모의 BT (K) | 원래 Control | Pilot Control | Pilot α=0.25 |
| --- | ---: | ---: | ---: |
| 남은 얼음 실패의 위치 `(1,168)` | 295.086844603 | 295.086844603 | 295.086844603 |
| 이전 QNC 표적 `(221,63)` | 285.822573426 | 286.148468954 | 285.822483468 |

여기서 `u=2⁻¹⁴⁹`는 binary32 subnormal 간격이다. 얼음 표적의 `QI=2u→0`은 hard moment 지원을 회복했지만, 이 위치의 IR105 BT는 기록된 세 **유효한** 결과에서 같다. Pilot 이전 α는 프로파일이 부적합해 direct BT가 없으므로 이 표는 QI 수정 전후의 BT 효과를 측정한 것이 아니다. QNC 표적의 pilot Control→pilot α 약 **−0.326 K**와 원래 Control→pilot α 약 **−0.000090 K**도 구분해야 한다. 전 영역의 작은 비용 감소를 특정 모멘트 교정이나 named KDM 과정의 인과적 효과로 분해한 결과는 아니다.

## 출처와 해석의 한계

오프라인 replay는 원래 baseline·관측·M0 해시, 두 packed BT 배열, 258개 청크의 원래 flat 범위·호출 영수증·capture 해시를 검증하고 각 capture의 값이 packed 배열과 비트 단위로 같은지 확인한다. 원래 지원 셀의 실제 validity·품질·유한 BT를 다시 검사한다. **이 replay의 모델 호출은 0회**이며, 위 258회 실제 RTTOV direct 실행과 구분한다. 비공개 RTTOV executable·계수·전체 체크포인트·원시 case 폴더는 공개 packet에 없고, 실행 당시 검증된 자산 해시와 일부 정확 소스 snapshot을 보존했다. 이 공개 해시가 그 비공개 실물을 독립 재실행했다는 뜻은 아니다.

호스트 체크포인트는 **2025-07-19 00:01:00**, KO 관측 bundle의 명목 slot은 **00:00**이다. 픽셀별 UTC는 검증되지 않았으며 시간 보간·보정은 수행하지 않았다. Native 39개 층의 중심 압력을 사용하고, interface 압력은 기존 계약대로 저장된 압력·geopotential·FNM/FNP에서 구성한다. RTTOV의 고정 clear upper prefix와 model-top/background 가정은 기존 baseline에서 유지한 것이며 외부 모델장을 대체 입력으로 쓰지 않았다.

이 결과는 **관측 공간의 고정 지원 진단**이다. 늦은 경계 연산은 Control·α 각각 외곽 QICE 약 1.2만, QNICE 약 7천 원소를 덮어쓰며 외부 경계 증감량을 만든다. QNICE의 host/커널 단위 연결, 실제 제어체적의 질량·수량 수지와 host 얼음 유효반경 진단의 후속 일관성은 아직 인증되지 않았다. Checkpoint→RTTOV 경로는 현재 QI/NI로 광학 입력을 재구성하지만, 그 비용이 물리적 보존 또는 전체 host JVP/VJP 검증을 대신하지 않는다. 따라서 **분석 수용과 두 번째 동화는 보류**한다.
