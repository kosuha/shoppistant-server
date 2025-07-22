# Backend API Development Requirements

## 🎯 프로젝트 개요
AI Shop Assistant 백엔드 API 개발을 위한 요구사항 문서입니다.

## 🔧 새로 추가할 API 엔드포인트

### 1. 스크립트 조회 API
**GET** `/api/v1/sites/{siteId}/scripts`

**목적:** 아임웹 사이트의 현재 header, body, footer 스크립트 조회

**요청:**
- Headers: `Authorization: Bearer {access_token}`
- Path Parameters:
  - `siteId`: 사이트 ID (string)

**응답:**
```json
{
  "status": "success",
  "data": {
    "header": "<script>console.log('header');</script>",
    "body": "<script>console.log('body');</script>",
    "footer": "<script>console.log('footer');</script>"
  }
}
```

**오류 응답:**
```json
{
  "status": "error", 
  "message": "사이트를 찾을 수 없습니다."
}
```

### 2. 스크립트 배포 API
**POST** `/api/v1/sites/{siteId}/scripts/deploy`

**목적:** 편집된 스크립트를 아임웹 사이트에 배포

**요청:**
- Headers: `Authorization: Bearer {access_token}`
- Path Parameters:
  - `siteId`: 사이트 ID (string)
- Body:
```json
{
  "header": "<script>console.log('new header');</script>",
  "body": "<script>console.log('new body');</script>", 
  "footer": "<script>console.log('new footer');</script>"
}
```

**응답:**
```json
{
  "status": "success",
  "data": {
    "deployed_at": "2025-07-22T10:30:00Z",
    "site_code": "site123"
  }
}
```

**오류 응답:**
```json
{
  "status": "error",
  "message": "스크립트 배포에 실패했습니다.",
  "error_code": "DEPLOY_FAILED"
}
```

## 🤖 AI 채팅 스크립트 연동 업데이트

### 기존 `/api/v1/messages` 엔드포인트 수정
**POST** `/api/v1/messages`

**변경사항:** 
1. **요청 metadata 필드 활용** - 현재 스크립트 상태 전달
2. **응답 metadata 필드 활용** - AI가 수정한 스크립트 반환

**요청 (기존 + 추가):**
```json
{
  "thread_id": "thread123",
  "message": "헤더에 구글 애널리틱스 코드를 추가해줘",
  "message_type": "user",
  "metadata": "{\"current_scripts\":{\"header\":\"<script>console.log('old');</script>\",\"body\":\"\",\"footer\":\"\"}}"
}
```

**응답 (기존 + 추가):**
```json
{
  "status": "success",
  "data": {
    "user_message": {
      "id": "msg123",
      "message": "헤더에 구글 애널리틱스 코드를 추가해줘",
      "message_type": "user",
      "created_at": "2025-07-22T10:30:00Z"
    },
    "ai_message": {
      "id": "msg124", 
      "message": "헤더에 구글 애널리틱스 코드를 추가했습니다.",
      "message_type": "assistant",
      "metadata": "{\"script_updates\":{\"header\":\"<script>gtag('config', 'GA-123');</script>\"}}",
      "created_at": "2025-07-22T10:30:05Z"
    }
  }
}
```

## 🔒 구현 요구사항

### 1. 스크립트 조회 기능
- **아임웹 API 연동** - 실제 사이트의 현재 스크립트 설정 조회
- **권한 검증** - 사용자가 해당 사이트 접근 권한 보유 확인
- **토큰 관리** - 아임웹 OAuth 토큰 만료시 자동 갱신
- **오류 처리** - 네트워크 오류, 권한 오류 등 적절한 응답

### 2. 스크립트 배포 기능
- **아임웹 API 연동** - 실제 사이트에 스크립트 적용
- **유효성 검사** - 서버에서 스크립트 형식 재검증
- **배포 로그** - 배포 성공/실패 이력 저장
- **롤백 지원** - 배포 실패시 이전 상태로 복원

### 3. AI 채팅 스크립트 연동
- **컨텍스트 파싱** - `metadata.current_scripts`에서 현재 스크립트 상태 추출
- **프롬프트 강화** - AI에게 현재 스크립트 상태를 컨텍스트로 전달
- **코드 추출** - AI 응답에서 `<script>` 태그 감싸진 코드 파싱
- **응답 포맷팅** - 파싱된 스크립트를 `metadata.script_updates`로 반환

### 4. 보안 및 검증
- **입력 검증:**
  - 스크립트 크기 제한 (각 스크립트당 최대 100KB)
  - `<script>` 태그 형식 검증
  - XSS 방지 기본 패턴 검사

- **권한 검증:**
  - 사용자-사이트 매핑 확인
  - 아임웹 OAuth 토큰 유효성 검사
  - 사이트별 스크립트 수정 권한 확인

### 5. 오류 처리 및 로깅
- **API 오류 처리:**
  - 아임웹 API 호출 실패 (네트워크, 권한, 서비스 장애)
  - 토큰 만료 시 자동 갱신 시도
  - 재시도 로직 (최대 3회)

- **로깅:**
  - 스크립트 조회/배포 액션 로깅
  - 사용자별 스크립트 변경 이력
  - AI 스크립트 수정 로그
  - 오류 발생 상세 로그

## 🏗️ 기술적 세부사항

### 아임웹 API 연동
- **스크립트 조회:** 아임웹 API를 통해 사이트 스크립트 설정 조회
- **스크립트 배포:** 아임웹 API를 통해 스크립트 업데이트
- **OAuth 토큰 관리:** 기존 토큰 갱신 로직 활용

### 응답 파싱 로직
```python
def parse_ai_response_for_scripts(ai_response: str) -> dict:
    """AI 응답에서 <script> 태그를 파싱하여 추출"""
    script_updates = {}
    
    # <script> 태그 패턴 매칭
    script_pattern = r'<script[^>]*>(.*?)</script>'
    scripts = re.findall(script_pattern, ai_response, re.DOTALL | re.IGNORECASE)
    
    # 헤더/바디/푸터 키워드로 분류
    for script in scripts:
        if 'header' in ai_response.lower():
            script_updates['header'] = f'<script>{script}</script>'
        elif 'body' in ai_response.lower():
            script_updates['body'] = f'<script>{script}</script>'
        elif 'footer' in ai_response.lower():
            script_updates['footer'] = f'<script>{script}</script>'
    
    return script_updates
```

## 📋 구현 순서 및 우선순위

### Phase 1 (High Priority)
1. **스크립트 조회 API** - 현재 상태 확인 필수
2. **스크립트 배포 API** - 핵심 기능
3. **AI 채팅 메타데이터 처리** - 스크립트 컨텍스트 전달/수신

### Phase 2 (Medium Priority)  
4. **유효성 검사 강화** - 서버 측 검증 로직
5. **오류 처리 개선** - 재시도 및 롤백 로직
6. **로깅 시스템** - 상세 액션 로그

### Phase 3 (Low Priority)
7. **배포 이력 관리** - 스크립트 변경 히스토리
8. **성능 최적화** - 캐싱 및 배치 처리

## 🧪 테스트 케이스

### API 테스트
```bash
# 스크립트 조회
curl -X GET "http://localhost:8000/api/v1/sites/test123/scripts" \
  -H "Authorization: Bearer token123"

# 스크립트 배포  
curl -X POST "http://localhost:8000/api/v1/sites/test123/scripts/deploy" \
  -H "Authorization: Bearer token123" \
  -H "Content-Type: application/json" \
  -d '{"header":"<script>console.log(\"test\");</script>"}'
```

### AI 채팅 테스트
```bash
# AI에게 스크립트 수정 요청
curl -X POST "http://localhost:8000/api/v1/messages" \
  -H "Authorization: Bearer token123" \
  -H "Content-Type: application/json" \
  -d '{
    "thread_id": "thread123",
    "message": "헤더에 구글 애널리틱스 추가해줘",
    "message_type": "user", 
    "metadata": "{\"current_scripts\":{\"header\":\"\",\"body\":\"\",\"footer\":\"\"}}"
  }'
```

## 📝 참고사항
- 프론트엔드 코드는 이미 이 API 구조에 맞춰 구현 완료
- `ScriptManager.ts`와 `ChatManager.ts`에서 해당 엔드포인트 호출 준비됨
- 아임웹 API 문서 확인 후 실제 스크립트 관련 엔드포인트 매핑 필요
- 현재 임시 데이터로 동작하는 부분들을 실제 API 연동으로 교체 예정