# 🚀 AI Shop Assistant - 사이트 연동 시스템 개편 개발 문서

## 📋 개요

기존의 복잡한 아임웹 OAuth 토큰 관리 시스템을 제거하고, 도메인 기반의 단순한 사이트 연동 시스템으로 전환합니다.

---

## 🗑️ 제거된 기능들

### 1. OAuth 관련 API 엔드포인트 제거

```
❌ POST /api/v1/imweb/site-code (사이트 코드 등록)
❌ POST /api/v1/auth-code (OAuth 인증 코드 → 토큰 교환)
❌ POST /api/v1/tokens/refresh-all (모든 사이트 토큰 일괄 갱신)
❌ GET  /api/v1/tokens/status-all (모든 사이트 토큰 상태 조회)
❌ POST /api/v1/sites/{siteCode}/refresh-token (개별 사이트 토큰 갱신)
```

### 2. 토큰 관리 시스템 완전 제거

- OAuth 액세스 토큰 자동 갱신 로직
- 토큰 만료 시간 추적 및 갱신 스케줄링
- 리프레시 토큰 관리
- 토큰 유효성 검증 로직

### 3. 아임웹 OAuth 연동 제거

- 아임웹 OAuth 2.0 인증 플로우
- OAuth 콜백 처리 (/auth/callback)
- 아임웹 API 스코프 관리

---

## 📊 데이터베이스 스키마 변경사항

### 1. `user_sites` 테이블 수정 필요

```sql
-- 토큰 관련 컬럼들 제거 (선택사항)
ALTER TABLE user_sites DROP COLUMN IF EXISTS access_token;
ALTER TABLE user_sites DROP COLUMN IF EXISTS refresh_token;
ALTER TABLE user_sites DROP COLUMN IF EXISTS access_token_expires_at;
ALTER TABLE user_sites DROP COLUMN IF EXISTS refresh_token_expires_at;
ALTER TABLE user_sites DROP COLUMN IF EXISTS last_token_refresh;
```

### 2. 새로운 Site 엔티티 구조

```typescript
interface Site {
  id: string;
  site_code: string;
  site_name: string;
  domain: string;        // 🆕 새로 추가됨
  created_at: string;
  updated_at: string;
}
```

---

## 🔄 유지되는 API 엔드포인트

### 1. 사이트 관리

```
✅ POST   /api/v1/websites
✅ GET    /api/v1/sites
✅ DELETE /api/v1/sites/{siteId}
✅ PATCH  /api/v1/sites/{siteId}
```

### 2. 채팅 관리

```
✅ GET    /api/v1/threads
✅ POST   /api/v1/threads
✅ GET    /api/v1/threads/{threadId}
✅ DELETE /api/v1/threads/{threadId}
✅ GET    /api/v1/messages/{threadId}
✅ POST   /api/v1/messages
```

### 3. 시스템 상태

```
✅ GET /health
✅ GET /api/v1/status
```

---

## 🆕 변경된 API 스펙

### 1. POST /api/v1/websites (웹사이트 추가)

**기존과 동일하지만 OAuth 없이 처리**

**Request:**

```json
{
  "domain": "example.com"
}
```

**Response:**

```json
{
  "status": "success",
  "data": {
    "site_code": "ABC123",
    "script": "<script>...</script>"
  }
}
```

### 2. GET /api/v1/sites (사이트 목록 조회)

**domain 필드 추가됨**

**Response:**

```json
{
  "status": "success",
  "data": {
    "sites": [
      {
        "id": "site-uuid",
        "site_code": "ABC123",
        "site_name": "My Website",
        "domain": "example.com",    // 🆕 추가
        "created_at": "2023-01-01T00:00:00Z",
        "updated_at": "2023-01-01T00:00:00Z"
      }
    ]
  }
}
```

---

## 🔧 백엔드 구현 가이드

### 1. 사이트 연동 단순화

```python
# 기존: 복잡한 OAuth 토큰 관리
def add_website_with_oauth(domain):
    # OAuth 인증 → 토큰 저장 → 토큰 관리 시작
    pass

# 새로운 방식: 도메인 기반 단순 연동
def add_website_simple(domain):
    # 1. 도메인 검증
    # 2. 사이트 코드 생성
    # 3. 연동 스크립트 생성
    # 4. DB에 저장 (domain 포함)
    return {
        "site_code": generated_code,
        "script": generated_script
    }
```

### 2. 연결 상태 관리 단순화

```python
# 기존: 6가지 복잡한 상태
CONNECTION_STATUS = {
    'connected', 'disconnected', 'expired', 
    'checking', 'refreshing', 'deleted'
}

# 새로운 방식: 3가지 단순한 상태
CONNECTION_STATUS = {
    'connected',     # 정상 연결됨
    'disconnected',  # 연결 끊김
    'checking'       # 상태 확인 중
}
```

### 3. 토큰 관리 로직 제거

```python
# 제거할 기능들
- refresh_all_tokens()
- check_token_expiry()
- auto_refresh_scheduler()
- oauth_callback_handler()
- token_validation_middleware()
```

---

## ⚠️ 마이그레이션 주의사항

### 1. 기존 데이터 처리

- 기존 사이트들의 `domain` 필드를 어떻게 채울지 결정 필요
- 토큰 관련 데이터 백업 후 제거

### 2. API 호환성

- 기존 클라이언트와의 호환성 유지
- 점진적 마이그레이션 계획 수립

### 3. 에러 처리

- OAuth 관련 에러 응답 제거
- 새로운 에러 케이스 정의

---

## 🎯 구현 우선순위

### Phase 1 (필수)

1. ✅ `user_sites` 테이블에 `domain` 컬럼 추가 => primary_domain 존재
2. ✅ OAuth 관련 API 엔드포인트 제거
3. ✅ 토큰 관리 로직 제거

### Phase 2 (권장)

1. 🔄 기존 사이트 데이터의 `domain` 필드 채우기
2. 🔄 토큰 관련 테이블/컬럼 정리
3. 🔄 연결 상태 로직 단순화

### Phase 3 (최적화)

1. 📈 성능 최적화
2. 📝 API 문서 업데이트
3. 🧪 테스트 케이스 업데이트

---

**주요 변경사항**: OAuth 복잡성 제거 → 도메인 기반 단순 연동으로 전환
