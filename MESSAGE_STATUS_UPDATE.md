# 메시지 상태 기능 백엔드 업데이트

## 개요

메시지 상태 관리 기능이 백엔드에 구현되었습니다. 메시지 처리 상태를 실시간으로 추적할 수 있는 API와 시스템이 추가되었습니다.

## 데이터베이스 변경사항

### chat_messages 테이블

- `status` 필드 추가 (TEXT, DEFAULT 'completed')
- 허용 값: `'pending'`, `'in_progress'`, `'completed'`, `'error'`
- 기존 데이터: 자동으로 `'completed'` 상태로 설정

## API 변경사항

### 새로운 엔드포인트

**실시간 상태 스트리밍 (SSE)**

```
GET /api/v1/threads/{thread_id}/messages/status-stream
```

**메시지 상태 조회**

```
GET /api/v1/messages/{message_id}/status
```

**메시지 상태 업데이트**

```
PATCH /api/v1/messages/{message_id}/status
Body: {"status": "completed", "message": "...", "metadata": {}}
```

### 기존 API 변경

**메시지 목록 조회 응답에 status 필드 추가**

```
GET /api/v1/messages/{thread_id}
Response: messages[].status 필드 포함
```

## 상태 변화 플로우

```
사용자 메시지 전송 → 'completed' (즉시)
AI 메시지 생성 → 'pending' → 'in_progress' → 'completed'/'error'
```

## 메시지 상태 업데이트 방식

### 권장 구현 방식

1. **주 방식: SSE** - 스레드 연결 시 `/api/v1/threads/{thread_id}/messages/status-stream` 사용
2. **백업 방식: 폴링** - SSE 연결 실패 시 `/api/v1/messages/{message_id}/status`로 fallback

### 상태 변화 메커니즘

#### 자동 상태 변화 (시스템)

- **사용자 메시지**: 생성 즉시 'completed' 상태
- **AI 메시지**:
  - 생성 시 'pending' 상태로 시작
  - AI 처리 시작 시 'in_progress'로 변경
  - 응답 완료 시 'completed'로 변경
  - 오류 발생 시 'error'로 변경

#### 수동 상태 변화 (API)

- PATCH API로 메시지 상태 직접 업데이트 가능
- 상태 변경 시 SSE로 실시간 알림
- 권한 확인 (본인 스레드의 메시지만 수정 가능)

## SSE 이벤트 형식

```json
// 초기 메시지 상태
{"type": "initial", "message_id": "...", "status": "completed", "message": "...", "message_type": "user"}

// 상태 변화 알림  
{"type": "status_update", "message_id": "...", "status": "in_progress", "message": "..."}

// 연결 유지
{"type": "heartbeat"}
```
