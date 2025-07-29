# 이미지 첨부 채팅 기능 구현 완료

## 구현 개요

프론트엔드에서 이미지를 첨부하여 채팅할 수 있는 기능을 백엔드에서 완전히 구현했습니다. 사용자가 Base64 형식의 이미지를 전송하면 AI가 이미지를 분석하여 적절한 응답을 생성합니다.

## 주요 변경사항

### 1. 데이터베이스 스키마 변경
- `chat_messages` 테이블에 `image_data` 컬럼 추가 (JSON 타입)
- 다중 이미지를 배열 형태로 저장 가능

### 2. 데이터 모델 업데이트
**파일**: `src/app/schemas.py`
- `ChatMessage` 모델에 `image_data` 필드 추가
- `ChatMessageCreate` 모델에 `image_data` 필드 추가
- 타입: `Optional[List[str]]` (Base64 이미지 문자열 배열)

### 3. 데이터베이스 헬퍼 수정
**파일**: `src/app/database_helper.py`
- `create_message()` 메서드에 `image_data` 매개변수 추가
- 이미지 데이터를 JSON 형태로 데이터베이스에 저장

### 4. AI 서비스 개선
**파일**: `src/app/services/ai_service.py`
- `generate_gemini_response()` 메서드에 `image_data` 매개변수 추가
- Base64 이미지를 디코딩하여 Gemini API에 전달
- `types.Part.from_bytes()`를 사용하여 이미지 데이터 처리
- 프롬프트에 이미지 설명 추가

### 5. 스레드 서비스 업데이트
**파일**: `src/app/services/thread_service.py`
- `create_message()` 메서드에 `image_data` 매개변수 추가
- AI 응답 생성 시 이미지 데이터를 AI 서비스에 전달

### 6. API 엔드포인트 수정
**파일**: `src/app/routers/thread_router.py`
- `/api/v1/messages` POST 엔드포인트에서 `image_data` 처리
- 이미지 검증 로직 적용

### 7. 이미지 검증 시스템
**파일**: `src/app/utils/image_validator.py`
- 이미지 형식 검증 (JPEG, PNG, GIF, WebP)
- 파일 크기 제한 (단일: 5MB, 총합: 10MB)
- 이미지 개수 제한 (최대 3개)
- Base64 유효성 검증
- 이미지 헤더 시그니처 검증

## API 사용법

### 메시지 전송 (이미지 포함)
```http
POST /api/v1/messages
Authorization: Bearer <token>
Content-Type: application/json

{
  "thread_id": "thread-uuid",
  "site_code": "site-code",
  "message": "이미지에 대한 설명이나 질문",
  "image_data": [
    "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA...",
    "data:image/png;base64,iVBORw0KGgo..."
  ],
  "auto_deploy": false
}
```

### 메시지 조회 (이미지 포함)
```http
GET /api/v1/messages/{thread_id}
Authorization: Bearer <token>
```

**응답 예시:**
```json
{
  "status": "success",
  "data": {
    "messages": [
      {
        "id": "message-uuid",
        "thread_id": "thread-uuid",
        "user_id": "user-uuid",
        "message": "이미지를 첨부합니다.",
        "message_type": "user",
        "status": "completed",
        "metadata": {},
        "image_data": [
          "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA..."
        ],
        "created_at": "2024-01-01T00:00:00Z"
      }
    ]
  }
}
```

## 검증 규칙

### 이미지 형식
- 지원 형식: JPEG, PNG, GIF, WebP
- Base64 인코딩 필수
- 형식: `data:image/[type];base64,[data]`

### 크기 제한
- 단일 이미지: 최대 5MB
- 총 이미지 크기: 최대 10MB
- 최대 이미지 개수: 3개

### 오류 응답
- `400 Bad Request`: 이미지 형식 오류, 개수 초과
- `413 Payload Too Large`: 파일 크기 초과
- `415 Unsupported Media Type`: 지원하지 않는 이미지 형식

## AI 처리

### Gemini API 연동
- 이미지 데이터를 `types.Part.from_bytes()`로 변환
- 텍스트와 이미지를 함께 전달
- AI가 이미지를 분석하여 적절한 응답 생성

### 프롬프트 개선
- 이미지가 첨부된 경우 프롬프트에 이미지 설명 추가
- AI가 이미지를 고려하여 스크립트 작성 또는 질문 답변

## 테스트

### 테스트 스크립트
**파일**: `test_image_chat.py`
- 이미지 검증 로직 테스트
- API 요청 형식 확인
- 실행: `python test_image_chat.py`

### 테스트 시나리오
1. 텍스트만 전송 (기존 기능 유지)
2. 단일 이미지 첨부
3. 다중 이미지 첨부 (최대 3개)
4. 텍스트 + 이미지 함께 전송
5. 크기 제한 초과 시 오류 처리
6. 잘못된 형식 이미지 오류 처리

## 데이터베이스 마이그레이션

### SQL 명령어
```sql
ALTER TABLE chat_messages ADD COLUMN image_data JSON;
```

**파일**: `add_image_data_column.sql`

## 보안 고려사항

### 이미지 검증
- 파일 시그니처 검증으로 실제 이미지 파일 확인
- Base64 디코딩 안전성 검증
- 메모리 사용량 제한으로 DoS 공격 방지

### 저장 방식
- 현재: 데이터베이스에 JSON으로 직접 저장
- 향후 개선 가능: 파일 시스템 또는 클라우드 스토리지 활용

## 성능 최적화

### 현재 구현
- 이미지 데이터를 데이터베이스에 직접 저장
- 간단한 구조로 빠른 개발 가능

### 향후 개선 방안
- 이미지 파일을 별도 스토리지에 저장
- 데이터베이스에는 파일 경로만 저장
- CDN을 통한 이미지 서빙 최적화

## 호환성

### 기존 기능
- 텍스트 전용 메시지는 기존과 동일하게 작동
- `image_data` 필드가 없는 요청도 정상 처리
- 기존 메시지 조회 시 `image_data`는 `null`로 반환

### 프론트엔드 요구사항
- 이미지를 Base64로 인코딩하여 전송
- 배열 형태로 다중 이미지 지원
- 오류 응답 처리 (400, 413, 415)

이미지 첨부 채팅 기능이 완전히 구현되어 프론트엔드에서 즉시 사용할 수 있습니다.