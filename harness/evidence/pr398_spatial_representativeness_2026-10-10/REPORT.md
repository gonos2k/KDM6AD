# PR398: 고정 후보 주변의 공간적 대표성

기준은 열린 PR398의 검토 head `bf00721b`입니다. 고정 AMI `(320,48)`,
VIIRS `(205,27)`, native `(j86,i48)`을 유지하고, 기존 원본 영상과 완료된
native 예보만 읽었습니다. 새 자료 취득·native 적분·KDM M·RTTOV H·최적화는
수행하지 않았습니다. 앞선 예산·gradient·시간·시선 중심 검증은 종결 범위를 유지합니다.

**관측의 액상 판정은 중심 한 표본에만 국한되지 않았습니다. 반면 고정 native
3×3은 세 시각 모두 무구름이었습니다. AMI window 채널에는 상당한 공간 변화가
있어, 같은 구름상 코드만으로 균일한 복사장이나 완전 운량을 가정할 수 없습니다.**

## 실제 표본과 결과

선택은 [공통 사전 선언](PREDECLARED.json)과 값 검사 전 만든
[native 좌표 범위](NATIVE_PATCH_GEOGRAPHY.json)에 고정했습니다.
VIIRS 영역은 native3×3 **중심들의** 위경도 bounding box이며 정확한 셀 경계·
면적 또는 센서 footprint가 아닙니다. AMI5×5와 VIIRS 선택 영역도 서로 다릅니다.

| 자료 | 실제 확인 | 해석 |
| --- | --- | --- |
| Native3×3 × 세 시각 | 27개 column/time, 모두 QC·NC0; 최대 액상 qv/qs95.1460–95.9879% | 주변9셀에서도 현재 저장 상태는 포화에 미달. 27개 독립 사건은 아님 |
| AMI5×5 × 7채널 | 175개 BT, DQF0; fill·비양의 radiance0; 원래 중심 BT 완전 일치 | 같은 후보의 작은 공간분포 확인 |
| VIIRS nominal 중심 좌표 선택 | 103개 표본 모두 CloudPhase1/CloudType2 | 기존 product-family 해석의 액상 코드; 면적 운량·단층·높이 균일성은 미확인 |
| VIIRS QA 원시 byte | 0은94개, 5는9개 | 0의 기존 가족 규약 해석과, 범위 밖5의 미해결을 구분 |

Native 저장시각은05:56:00·05:57:00·05:57:40이며39개 중심층·40개 interface,
raw T/Q/수상체·수농도, native 압력·지오포텐셜·층 두께와 지면을 보존했습니다.
중심 column은 기존 intake의 같은 시각과 일치했습니다. [27개 표](NATIVE_PATCH_TABLE_v3.md)와
[native 결과](NATIVE_PATCH_RESULT_v3.json)는 무가중 QC 합을 LWP로 부르지 않으며,
원시 number 필드를 관측된 CCN 공급량이나 검정된 수농도로 변환하지 않습니다.

AMI IR105의5×5 BT는 다음과 같습니다. 행318–322, 열46–50 순서이고 중심은
세 번째 행·열의291.3026K입니다.

| row \ col | 46 | 47 | 48 | 49 | 50 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 318 | 292.8870 | 292.9771 | 292.8998 | 291.8508 | 291.2895 |
| 319 | 293.7085 | 293.2215 | 292.3054 | 291.7727 | 291.0667 |
| 320 | 293.1701 | 292.5901 | **291.3026** | 290.6461 | 290.5143 |
| 321 | 291.4072 | 290.7646 | 289.8129 | 289.4003 | 289.2401 |
| 322 | 289.6800 | 289.4003 | 289.1466 | 289.0664 | 288.9325 |

관측 IR105 범위는288.9325–293.7085K, 폭4.7760K입니다. 앞선 모의 native-H의
세 시각 IR105 변화폭0.00702K·두 중심 기하 차이0.000295K보다 큽니다. 이 비교는 공간 변화의
규모를 보여주며, 다른 위치의 BT를 현재 모델 중심에 대한 잔차로 쓰거나 가장
좋은 이웃으로 후보를 교체하지 않았습니다.

[전체 AMI 표](AMI_PATCH_5x5.csv)는 각 픽셀의 DN·radiance 추정·BT·DQF를 별도로
보존합니다. Radiance는 원본과 paired table의 offset+gain×DN이며 기존 decoder의
`mW m^-2 sr^-1 per cm^-1` 규약을 따릅니다. BT를 평균해 radiance로 바꾸지 않았고,
공간 산포로 sigma/R을 검정하지 않았습니다. Paired 계수는 원본과 대조했지만
2025 FD/SRF 버전의 독립 검증은 아직 없습니다.

## QA와 서로 다른 공간 영역

Native 중심 범위는 위도35.367634–35.463676, 경도122.084351–122.202209입니다.
AMI 패치 중심 범위는 위도35.368860–35.469697, 경도122.086914–122.187481로
다릅니다. 동일 픽셀 수나 주변 패치가 같은 물리적 응답영역을 뜻하지 않습니다.
VIIRS nominal 중심 선택은 parallax 보정 좌표나 면적 가중치를 적용하지 않았습니다.
기존 중심의 product parallax 정보는 이 범위의 확정된 공간 정합으로 확대하지 않습니다.

`CloudPhaseFlag`는 파일에서 fill=-128, valid_range=[0,1]을 선언하지만 선택한
9개 원시 byte가5입니다. [별도 QA audit](OBSERVATION_PATCH_QA_AUDIT.json)는 이
범위 불일치를 미해결로 기록하고 원래 결과·NPZ·byte를 변경하지 않았습니다.
비영 byte의 비트 의미를 추정하지 않았습니다. 94개의0은 기존 sibling-platform
product-family 자료에 근거한 high-quality 해석이며,103개 전부를 같은 품질로
승인한 것이 아닙니다. [범주 수](VIIRS_PATCH_CATEGORY_COUNTS.csv)는 표본 수이고
면적 운량이 아닙니다.
[103개 위치·범주·QA·view angle 표](VIIRS_PATCH_SAMPLES.csv)는 같은 보존 배열에서
직접 전사했습니다. [전사 출처](VIIRS_SAMPLE_TABLE_PROVENANCE.json)를 별도로
기록했으며 새로운 추출이나 원래 결과 변경은 없습니다.

VIIRS view zenith는68.829–69.053°입니다. 픽셀 UTC, 검증된 물리 footprint,
운정고도 기준면과 높이의 주변 분포는 여전히 미확인입니다. 전체 CloudHeight
원본이 없어 중심 높이 값을 주변103개에 복사하지 않았습니다.

## 다음 원인 분기와 미사용 자료

작은 영역에서 액상 판정이 연속되고 모델은 모두 맑다는 결과를 회귀 근거로
고정합니다. 다음에는 기존 native T/Q·수직 구조·구름 생성 조건과 관측의 높이·
광학 두께·부분운량·시간 대응을 함께 확인하는 것이 타당합니다. 현재 자료만으로
PBL·수송·미세물리·지면·기체 중 한 원인으로 귀속하지 않습니다. 액상 코드의
공간적 일관성과 IR105의 공간적 불균질성이 함께 있으므로 단순한 단일 원인
분류나 구름분율 강제, seed·sigma·bias 조정은 하지 않았습니다.

[로컬 가용성 조사](NATIVE_5KM_AVAILABILITY_v3.json)는 조사 대상84개 예보 경로의
초기시각 suffix가 모두 기존2025-07-19임을 확인했습니다. 원래 IC·boundary와
기존 기록의 Times도 같은 사건입니다. 다른 날짜 두 사건의 native IC/예보는
**조사한 로컬 범위에서 확보되지 않았습니다.** 모든84개 예보의 물리적 유효성을
새로 승인하거나 사용자 장비 전체에 다른 사건이 없다고 결론낸 것은 아닙니다.
다른 사건의 자료 가용성·QA·시공간 기준을 정한 뒤 별도 모델 실행 범위를 정해야
합니다. 기존 사건의 다른 실행본이나 시각을 독립 사건으로 대신하지 않습니다.

## 검증·보존·수행 범위

Native V1 준비에서 전체8Times와 선택3Times의 비교 오류가 발생했습니다.
Dataset을 열기 전 실패했고 실제 marker/result는 생성되지 않았습니다.
[실패 기록](NATIVE_PATCH_ATTEMPT1_SETUP_FAILURE.json)을 유지했으며, V2는
미실행 계획, 실제 추출은 독립된V3 계획·source hash·결과로 구분했습니다.
V3는 원본8Times와 선택1/4/6을 읽어 확인했습니다. Times-only preflight와
추출 전·후의 크기/mtime은 모두 같습니다. 이 stat 대조는 파일 전체의
cryptographic identity 증명이 아닙니다. 실행 소스의 명시적 pre-marker stat
동일성 assertion 부족은 실제 기록의 별도 비교로 한정해 확인했고 재추출하지 않았습니다.

관측 추출 전의 import 순서·VIIRS index/record 변수 분리도 정정했습니다.
원래 관측 결과는 그대로 유지하고 QA 해석만 별도 audit로 추가했습니다.
[Green](SPATIAL_GREEN_REVIEW.md)·[Red](SPATIAL_RED_REVIEW.md)가 소스·범위·실제
배열과 표를 검토했고, root도 해시·shape·BT decoder 일치·QA 수·native 집계를
보존 배열에서 대조했습니다. 새 M/H 호출은 없습니다. Ruff·py_compile를 확인하며,
전체 저장소 pytest·native build는 이번 로컬 작업에서 수행하지 않았습니다.

[Canonical 보존 receipt](LOCAL_PRESERVATION.json)는 선택 배열과 정확한 실행
source·계획·결과·QA·reader를537339바이트의24개 파일로 보존합니다.
`host/research_evidence/pr398_spatial_20261010/`은0700, 파일은0600이며 원본은
덮어쓰지 않았습니다. 원래2.54GB 예보와 위성 전체 원본은 다시 복사하지 않았습니다.

Graphify code 갱신과 scoped 문서 semantic 갱신을 수행했습니다. 기존 unique ID를
유지한17061개 node·29554개 edge에서 관련 wiki–checklist 관계와 label/confidence를
확인했습니다. 일반 query의 제한적인 coverage는 실제 소스 확인으로 보완했으며,
전체 과학적·semantic coverage를 인증한 것은 아닙니다.

점수는56/75, 약75%를 유지합니다. 공간적 적용범위는 더 명확해졌지만,
새 독립 사건·확정 footprint·검정된 B/R·전체 물·열 flux 수지를 확보한 것은 아닙니다.
