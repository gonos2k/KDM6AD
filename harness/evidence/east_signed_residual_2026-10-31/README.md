# 동부 광학 부호 잔차와 상쇄: 오프라인 패킷 v1

기준 리비전은 PR #495 병합 `c186c752c70226d6c3fd72fe93e45ccaa9c14bed`다. PR #494의 content one-hot과 PR #495의 diameter one-hot 저장 결과 및 이전 K 캡처를 읽는다. RTTOV 또는 호스트 모델 호출은 없다. 원본 패킷의 검증기를 먼저 실행해 매니페스트, receipt, 원시 radiance, 저장 BT, preflight와 순위를 검사한다. 자기 포함 해시는 출처 인증이 아니며 Git 신뢰 리비전이 필요하다. 두 source manifest SHA-256은 각각 `77d943544bf94766ea4c26314f2f47943ddfcac5462a945f1128009c57e339a3`, `64762cd9dff7415cb8ef3221c2a6f173ceb8e679bdd674a080e26c0995ef3934`이다.

`results.json`은 GG/PP, 함량/직경, h=0.0001, 0.0002, 0.0004, 0.0008, 프로필 1–10, 채널 순서 wv073, ir087, ir096, ir105, ir112, ir123, ir133의 모든 70개 부호 잔차를 담는다. FD는 저장 BT의 `(BT+ - BT-)/(2h)`이고 K 예측은 각 프로필의 실제 직렬화된 `(x+ - x-)/(2h)`와 이전 K 배열 layer 39의 곱이다. 부호는 FD−K다. 연속 h 비율은 **큰 h 잔차 / 직전 작은 h 잔차**이며 분모가 정확히 0이면 null이다. 결과는 K per dimensionless perturbation이다. 저장 FD와 재계산 FD는 binary64 raw bits가 같아야 한다. 저장 및 재계산 K 곱은 두 binary64 피연산자의 정확한 유리수 곱과 비교하여 `gamma(2)*abs(product) + 2^-1074` 이내여야 한다. 이는 산술 반올림 한계이지 과학적 잔차 허용치가 아니다. NaN, 무한대, 0 방향 및 0 벡터 노름은 거부한다. 비율은 작은 분모에 민감하다.

기준 q와 D는 양 one-hot pins의 profile별 `content`, `diameter_um`, K는 이전 `GG_K`/`PP_K/values.npz`의 `hydro7`과 `deff7` 0 기반 layer 39다. q는 RTTOV hydrometeor content 좌표, D는 µm이고 각각의 K는 해당 좌표 단위당 K이다. layer 39는 반드시 최하층이 아니다. `Sq=q*K_hydro39`, `Sd=D*K_deff39`는 각각 같은 상대 변화 단위당 K이며 프로필별 7채널 벡터다. `cosine=dot(Sq,Sd)/(||Sq|| ||Sd||)`, `cancellation=1-||Sq+Sd||/(||Sq||+||Sd||)`, `sum_over_content=||Sq+Sd||/||Sq||`로 정의한다. 노름과 내적은 binary64 입력의 정확한 유리수 합으로 계산하고, 제곱근과 비율은 decimal 100자리·round-half-even 후 binary64로 변환한다. 따라서 BLAS 축약 순서에 의존하지 않는다. 동일한 상대 변화의 **K 선형 합성**이며 새 공동 RTTOV 실험이나 호스트 미세물리 과정의 응답이 아니다.

| 지점 | cosine 범위 | cancellation 범위 | sum_over_content 범위 |
|---|---:|---:|---:|
| GG | −0.990176 ~ −0.990083 | 0.887908 ~ 0.888400 | 0.205324 ~ 0.206160 |
| PP | −0.990124 ~ −0.990072 | 0.887483 ~ 0.887986 | 0.206013 ~ 0.206827 |

각 지점의 70개 모두 Sq<0, Sd>0이다. 잔차 L2 노름은 h 증가 순서로 GG 함량 1.066e−8, 4.012e−9, 2.356e−9, 1.692e−9; GG 직경 1.293e−8, 6.638e−9, 1.339e−8, 5.015e−8; PP 함량 9.891e−9, 4.170e−9, 2.545e−9, 2.101e−9; PP 직경 1.229e−8, 6.668e−9, 1.731e−8, 6.573e−8이다. 단일 실험의 경향이며 수렴 차수 또는 plateau의 증명이 아니다.

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 harness/evidence/east_signed_residual_2026-10-31/replay.py
python3 -m unittest discover -s harness/evidence/east_signed_residual_2026-10-31 -p 'test_*.py'
```

원래 실험의 RTTOV 실행과 연결 라이브러리는 receipt만으로 독립 인증되지 않는다. 원본의 고정 입력 및 구름 임계값은 전체 비공개 입력이 아니라 preflight에 귀속된다. KMA 변환은 원본 검증기의 실용적 binary64 반올림 한계를 따른다. 본 결과는 RTTOV의 국소 1차 K 증거로서 QNICE, 과정 귀속, 비용 함수, 고차 미분, 예보 성능을 확립하지 않는다.
