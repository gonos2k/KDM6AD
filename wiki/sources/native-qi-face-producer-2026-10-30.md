# QI face producer, 2026-10-30

남은 QI 실패의 donor `(2,168,33)`에서 control·α의 제한 전/low-order 여섯 면과 상태·metric 입력은 같다. 아래 이웃 `(2,168,32)`의 `FLUX_OUT`과 limiter 분기가 달라져, 공통 아래 correction face `80000060`이 control에서는 음의 0으로 줄고 α에서는 그대로 남는다. α의 실제 Z 누적 경향 `000021A3`은 이 제한 후 면으로 source-compatible f32 재현된다. [수치·수용 범위](../../docs/NATIVE_QI_FACE_PRODUCER_20261030.md) · [실행·재생 패킷](../../harness/evidence/native_qi_face_producer_2026-10-30/README.md)

네 호스트 실행의 trace off/on 체크포인트와 이전 QNC/QI donor 실행의 체크포인트가 같다. 아래 이웃의 유출 총량을 구성한 여섯 면과 높은 차수 수직 flux stencil은 아직 미기록이므로 물리적 QI/NI 보존이나 수정 규칙은 확정하지 않았다. 원래 (M_0)에는 얼음 한 프로파일·7채널이 남아 전체 RTTOV 비용과 분석 수용은 미완료다.
