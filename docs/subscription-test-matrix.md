# 통합 테스트 매트릭스 (구독·환불·크레딧)

본 문서는 멤버십/크레딧 결제 흐름 전반에 대한 통합 테스트 시나리오를 정리합니다. 최근 변경 사항(멤버십 사용자 전용 크레딧 구매 가드 등)이 반영되어 있으며, 각 시나리오는 수동/자동화 테스트 전략과 기대 결과를 포함합니다.

## 테스트 준비 사항

- **환경**: Staging 이상 환경에서 Paddle Billing Webhook을 테스트용 엔드포인트에 연결
- **테스트 계정**: 멤버십 미가입 사용자, 멤버십 활성 사용자, Paddle 테스트 결제 수단
- **도구**:
  - Paddle CLI 또는 대시보드에서 이벤트 시뮬레이션
  - `supabase` 대시보드 혹은 DB 조회 도구 (결과 확인)
  - `pytest` (자동화 스크립트 실행 시)

## 시나리오 매트릭스

| ID | 시나리오 | 사전 조건 | 테스트 절차 | 기대 결과 | 자동화 메모 |
| --- | --- | --- | --- | --- | --- |
| S1 | 신규 멤버십 결제 성공 | 사용자 미가입, Paddle 가격 ID 설정 | 1. 웹 체크아웃에서 멤버십 상품 선택<br>2. Paddle 결제 완료<br>3. Webhook `/api/v1/webhooks/paddle` 호출 확인 | `membership_service.upgrade_membership` 호출, DB 멤버십 레벨=1, 만료일+30일 설정, 응답 `results.membership.success=true` | Webhook payload를 pytest에서 모킹해 `paddle_router` 직접 호출 가능 |
| S2 | 중복 결제 이벤트 무시 | S1 수행 완료, 동일 `event_id` 사용 | 1. 같은 webhook payload 재전송 | 응답 `duplicate=true`, DB 변경 없음 | pytest에서 `db_helper.has_processed_webhook_event` 모킹 필요 |
| S3 | 멤버십 해지(만료 전) | 멤버십 레벨=1, 만료일 미래 | 1. Paddle 구독 취소 이벤트 전송<br>2. `/api/v1/membership/status` 조회 | `cancel_at_period_end=True`, 즉시 다운그레이드 없음 | 추가 자동화 필요 (미구현) |
| S4 | 만료 시 자동 무료 플랜 | S3 이후 만료일 경과 | 1. 만료 cron(혹은 수동 스크립트) 실행<br>2. DB `membership_level` 확인 | 레벨이 0으로 전환되고 `force_downgrade_to_free` 로그 기록 | 만료 시뮬레이션은 단위 테스트로 `membership_service.extend/cancel` 사용 권장 |
| S5 | 결제 환불 시 멤버십 다운그레이드 | 활성 멤버십, 환불 이벤트 준비 | 1. Paddle 환불 이벤트 전달<br>2. `/api/v1/webhooks/paddle` 응답 확인 | `results.membership_refund.success=true`, DB 레벨=0 | pytest에서 환불 payload로 검증 가능 |
| S6 | 크레딧 결제 - 멤버십 필요 | 멤버십 레벨=0 사용자 | 1. 웹에서 크레딧 상품 선택<br>2. 결제 버튼 클릭 | 버튼 비활성화 + 경고 문구 노출, API 요청 차단 | Playwright로 UI 검증 가능 |
| S7 | 크레딧 결제 성공 (멤버십 보유) | 멤버십 레벨=1, Paddle 크레딧 Price ID 설정 | 1. 웹에서 크레딧 결제 진행<br>2. Webhook 처리 후 `wallet` 조회 | `results.credits.success=true`, `credit_wallet` 트랜잭션 기록 | pytest에서 webhook payload 모킹으로 검증 |
| S8 | 환불 시 크레딧 회수 | S7 이후 환불 이벤트 | 1. Paddle 환불 이벤트 전송 | `results.credits_refund.success=true`, `debit_wallet` 호출 | pytest에서 환불 payload 모킹 |
| S9 | 테스트용 지갑 충전 API 권한 | 멤버십 레벨=0, `Authorization` 헤더 준비 | 1. `POST /api/v1/membership/wallet/credit` 호출 | `MEMBERSHIP_REQUIRED` 에러 반환 | pytest의 FastAPI TestClient로 호출 가능 |
| S10 | 테스트용 지갑 충전 API 성공 | 멤버십 레벨=1 | 1. `POST /api/v1/membership/wallet/credit` 호출<br>2. `wallet.balance` 확인 | 잔액 증가, 트랜잭션 기록 | pytest TestClient 활용 |

## 자동화 권장 사항

- **Webhook 레벨 테스트**: `FastAPI TestClient`와 `pytest`로 `paddle_router`를 직접 호출하도록 payload fixture를 구성
- **서비스 레벨 테스트**: `membership_service` 및 `db_helper`를 Mock하여 멤버십 연장/해지 로직을 검증
- **UI 회귀 테스트**: Playwright에서 멤버십 보유 여부에 따른 버튼 활성화 상태와 메시지를 스냅샷으로 검증

## 확인 체크리스트

- [ ] 테스트용 Paddle Price ID 및 Webhook 시크릿 환경 변수 구성
- [ ] 테스트 사용자 계정의 멤버십/지갑 상태 초기화
- [ ] Webhook 호출마다 `event_id`가 유니크한지 확인
- [ ] 실패 시 로그 및 `results.*.error` 필드 확인
- [ ] 수동 테스트 결과를 Confluence/노션 등에 기록

---

문서 버전: 2025-10-24 / 작성자: Codex Assist (자동 생성)  
추가 케이스나 자동화 스크립트 개선 사항은 MR 리뷰 시 업데이트하세요.
