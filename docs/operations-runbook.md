# 운영 대응 가이드 (멤버십 · 크레딧 결제)

본 문서는 Paddle 결제와 Supabase 연동을 사용하는 SITE TOPPING 서비스의 운영자가 구독/환불/크레딧 관련 상황에 대응할 수 있도록 정리한 런북입니다. 결제 흐름 진단 결과와 최신 가드 정책(멤버십 사용자 전용 크레딧 구매)을 반영했습니다.

---

## 1. 모니터링 체크리스트

| 주기 | 항목 | 방법 |
| --- | --- | --- |
| 매일 | Paddle 결제 실패 이벤트 | Paddle Dashboard > Events 또는 Webhook 로그 |
| 매일 | Supabase `system_logs` 중 `membership_*`, `wallet_*` 이벤트 | Supabase SQL 혹은 로깅 대시보드 |
| 주 1회 | TestUser 멤버십 상태 확인 | `GET /api/v1/membership/status` (Bearer 토큰 필요) |
| 배포 직후 | Webhook 서명 검증 정상 동작 여부 | `curl`로 샘플 이벤트 전송 후 400/200 응답 확인 |

> Paddle Webhook 서명 실패가 발생하면 즉시 환경 변수 `PADDLE_WEBHOOK_SECRET` 및 인증서 만료 여부를 확인합니다.

---

## 2. 주요 플로우 대응

### 2.1 신규 구독 확인
1. Paddle 대시보드에서 결제 성공 이벤트 확인  
2. `system_logs`에서 `membership_upgrade` 이벤트 존재 여부 확인  
3. 고객이 웹에서 멤버십 페이지를 열어 만료일/차기 결제일이 표시되는지 확인

문제 발생 시:
- Webhook 재전송 (Paddle Dashboard > Events > Resend)
- `main.py`에서 `membership_service` 및 `db_helper`가 초기화되었는지 로깅 확인

### 2.2 멤버십 해지 요청
1. 고객이 웹 UI에서 해지를 진행하면 서버가 `PADDLE_API_KEY`를 사용해 `POST /subscriptions/{id}/cancel` API를 호출한다. 호출 성공 시 Paddle 구독이 `canceled` 상태로 전환된다.  
2. 같은 요청 흐름에서 `user_memberships` 레코드가 `cancel_at_period_end=true`, `cancel_requested_at=<now>`로 업데이트된다.  
3. 만료일까지는 혜택 유지, 만료일 경과 후 자동 `force_downgrade_to_free`

장애 대응 체크리스트:
- API 호출 실패 시 사용자는 해지 에러를 보게 된다. 서버 로그에서 `[PADDLE] API request failed` 메시지를 확인하고 `PADDLE_API_KEY`, `PADDLE_API_BASE_URL` 환경변수를 검증한다.  
- Paddle Dashboard에서 `Cancel Subscription`을 수동 실행한 뒤 `system_logs`에 수기 메모를 남긴다.  
- Supabase `user_memberships`에서 `cancel_at_period_end`를 수동 보정해야 하는 경우, API 호출 성공 여부를 먼저 확인한다.

### 2.3 환불 처리
1. Paddle에서 환불 실행 (부분 환불은 현재 비지원)  
2. Webhook `refund` 이벤트가 `membership_refund` 혹은 `credits_refund` 섹션에서 `success=true`인지 확인  
3. 고객에게 멤버십 다운그레이드 또는 크레딧 회수 안내

에러 로그 대응:
- `service_unavailable`: 서버 재기동 또는 의존성 주입 확인  
- `credit_failed`: Supabase RPC `credit_wallet`가 실패한 경우 → DB 측 로그 조사

### 2.4 크레딧 충전 및 권한
- 멤버십 레벨 0 사용자는 크레딧 구매/충전 시도 시 UI와 API에서 차단  
- 운영자가 테스트 목적으로 충전해야 할 경우:
  ```bash
  curl -X POST https://{api-base}/api/v1/membership/wallet/credit \
    -H "Authorization: Bearer <admin-or-test-token>" \
    -H "Content-Type: application/json" \
    -d '10'
  ```
  - 응답 `error_code=MEMBERSHIP_REQUIRED` 발생 시 사용자 멤버십 레벨을 먼저 확인 후 조치

---

## 3. 비상 대응 시나리오

| 상황 | 증상 | 즉각 조치 | 후속 조치 |
| --- | --- | --- | --- |
| Webhook 장애 | Paddle 결제 성공했지만 멤버십 미반영 | Paddle Dashboard에서 이벤트 재전송, 서버 로그 확인 | 로그 파일 보관, `system_logs`에 수동 이벤트 추가 |
| Paddle Price ID 변경 | 체크아웃에서 `configuration` 오류 | `.env`의 `PADDLE_PRICE_ID_*` 업데이트 | 배포 후 S1~S3 테스트 재수행 |
| Paddle Product ID 변경 | 결제 승인 후 멤버십/크레딧 미지급 | `.env`의 `PADDLE_PRODUCT_ID_*` 업데이트 | 신규 결제 흐름 수동 확인 |
| Supabase 연결 실패 | 모든 결제 처리 실패, `service_unavailable` | 데이터베이스 연결 상태 확인, 필요 시 재부팅 | 장애 리포트 작성 및 재발 방지책 검토 |

---

## 4. 관리자 UI 활용 절차

1. **접속**: `/admin` 경로로 이동하면 AuthProvider가 세션을 확인합니다.  
   - 비로그인/비관리자 계정 → `/account?redirect=/admin` 또는 `/admin/unauthorized`로 안내  
   - 관리자 권한이 있는 계정 → Admin Shell 로딩 (좌측 네비 + 상단 헤더)
2. **대시보드**: 기본 KPI와 최근 이벤트는 UI 레벨에서 플레이스홀더로 표시되며, API 연동 후 자동 업데이트 예정.
3. **사용자(User) 관리**
   - `/admin/users` 진입 → 검색/필터/페이지네이션으로 사용자 조회  
   - 행 선택 → 우측 패널에서 멤버십/지갑 정보 확인 및 수동 조치 실행  
   - 조치 수행 시 토스트 알림 확인 후, `system_logs`에 `admin_action` 이벤트 기록되어야 함.
4. **이벤트(Event) 대시보드**
   - `/admin/events`에서 기간, 타입, 상태로 필터링  
   - 이벤트 선택 시 상세 패널에서 멤버십/지갑 영향과 원본 payload 확인  
   - 재처리가 필요한 경우 `Replay event` 버튼 클릭 → 확인 후 실행 → 성공 알림 및 로그 검토
5. **운영 체크리스트**
   - 관리자 조치 후 반드시 `system_logs`에서 감사 로그 기록 확인  
   - 재처리/환불 등 고위험 작업 시 Slack/티켓 시스템에 내역 보고  
   - UI와 백엔드 API가 동기화되지 않은 경우 수동 조치(직접 DB/Edit) 대신 개발팀에 문의

---

---

## 4. 참고 자료 및 절차

- **테스트 매트릭스**: [`subscription-test-matrix.md`](./subscription-test-matrix.md)
- **자동화 테스트 실행**: `cd site-topping-server && pytest src/app/tests` (추가한 테스트 파일 기준)
- **로그 위치**: FastAPI 애플리케이션 로그는 `stdout` 기반, 인프라별 수집 경로 확인 필요
- **Paddle 테스트 결제**: Billing Sandbox 모드 사용, 결제 카드 `4242 4242 4242 4242`

---

## 5. 변경 이력

| 일시 | 변경 내용 | 작성자 |
| --- | --- | --- |
| 2025-10-24 | 최초 작성 – 통합 테스트/가드 정책 반영 | Codex Assist |

추가 운영 정책이나 예외 케이스가 정의되면 본 문서를 업데이트하고, 관련 자동화 스크립트/테스트도 함께 갱신하세요.
