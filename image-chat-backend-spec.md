# 이미지 첨부 채팅 기능 백엔드 구현 명세서

## 개요
프론트엔드에서 이미지 첨부 기능이 추가되어, 백엔드에서 이미지 데이터를 처리하고 저장할 수 있도록 API를 수정해야 합니다.

## 변경사항 요약

### 1. 데이터베이스 스키마 변경
`messages` 테이블에 이미지 데이터를 저장하기 위한 컬럼 추가가 필요합니다.

```sql
ALTER TABLE messages ADD COLUMN image_data JSON;
```

- `image_data`: JSON 배열 형태로 다중 이미지 데이터를 저장
- NULL 허용 (텍스트만 있는 메시지의 경우)
- 단일 이미지의 경우: `["data:image/jpeg;base64,/9j/4AAQ..."]`
- 다중 이미지의 경우: `["data:image/jpeg;base64,/9j/4AAQ...", "data:image/png;base64,iVBORw0KGgo..."]`

### 2. API 요청/응답 변경

#### 채팅 메시지 전송 API 수정
**엔드포인트**: `POST /api/chat/send`

**기존 요청 형태**:
```json
{
  "thread_id": "string",
  "site_code": "string", 
  "message": "string",
  "script": "string",
  "auto_deploy": boolean
}
```

**새로운 요청 형태**:
```json
{
  "thread_id": "string",
  "site_code": "string",
  "message": "string", 
  "script": "string",
  "auto_deploy": boolean,
  "image_data": [  // 선택적 필드, 배열 형태
    "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA...",
    "data:image/png;base64,iVBORw0KGgo..."
  ]
}
```

#### 메시지 조회 API 응답 수정
**엔드포인트**: `GET /api/threads/{thread_id}/messages`

**기존 응답 형태**:
```json
{
  "status": "success",
  "data": [
    {
      "id": "string",
      "thread_id": "string", 
      "user_id": "string",
      "message": "string",
      "message_type": "user|assistant|system",
      "status": "pending|in_progress|completed|error",
      "metadata": "string",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

**새로운 응답 형태**:
```json
{
  "status": "success", 
  "data": [
    {
      "id": "string",
      "thread_id": "string",
      "user_id": "string", 
      "message": "string",
      "message_type": "user|assistant|system",
      "status": "pending|in_progress|completed|error",
      "metadata": "string",
      "image_data": [  // 선택적 필드, 배열 형태
        "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA...",
        "data:image/png;base64,iVBORw0KGgo..."
      ],
      "created_at": "2024-01-01T00:00:00Z"
    }
  ]
}
```

### 3. 구현 고려사항

#### 이미지 데이터 처리
1. **배열 형태 처리**: 단일/다중 이미지를 일관되게 배열로 처리
2. **Base64 검증**: 받은 이미지 데이터가 유효한 Base64 형식인지 검증
3. **이미지 형식 검증**: JPEG, PNG, GIF 등 허용된 이미지 형식인지 확인
4. **파일 크기 제한**: 압축된 이미지라도 최대 크기 제한 (예: 단일 이미지 5MB, 총 10MB)
5. **이미지 개수 제한**: 한 번에 첨부할 수 있는 이미지 개수 제한 (예: 최대 3개)
6. **보안 검증**: 이미지 데이터에 악성 코드가 포함되지 않았는지 검증

#### 저장 방식 옵션
**옵션 1: 데이터베이스 직접 저장 (현재 구현)**
```python
# 장점: 구현이 간단, 트랜잭션 보장
# 단점: DB 크기 증가, 성능 영향
def save_message_with_image(message_data):
    image_data_json = None
    if message_data.get('image_data'):
        # 배열 형태로 정규화
        images = message_data['image_data']
        if isinstance(images, str):
            images = [images]  # 단일 이미지를 배열로 변환
        image_data_json = json.dumps(images)
    
    query = """
    INSERT INTO messages (thread_id, user_id, message, message_type, image_data, created_at)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    cursor.execute(query, (
        message_data['thread_id'],
        message_data['user_id'], 
        message_data['message'],
        message_data['message_type'],
        image_data_json,  # JSON 배열로 저장
        datetime.utcnow()
    ))
```

**옵션 2: 파일 시스템/클라우드 저장 (권장)**
```python
# 장점: DB 성능 향상, 확장성
# 단점: 구현 복잡도 증가, 파일 관리 필요
import uuid
import os

def save_message_with_image(message_data):
    image_urls = []
    if message_data.get('image_data'):
        # 배열 형태로 정규화
        images = message_data['image_data']
        if isinstance(images, str):
            images = [images]  # 단일 이미지를 배열로 변환
            
        for image_data in images:
            # Base64 디코딩 후 파일로 저장
            image_base64 = image_data.split(',')[1]  # data:image/jpeg;base64, 제거
            image_bytes = base64.b64decode(image_base64)
            
            # 고유 파일명 생성
            file_id = str(uuid.uuid4())
            file_extension = image_data.split(';')[0].split('/')[-1]  # jpeg, png 등
            file_path = f"uploads/images/{file_id}.{file_extension}"
            
            # 파일 저장
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, 'wb') as f:
                f.write(image_bytes)
                
            image_urls.append(f"/api/images/{file_id}.{file_extension}")
    
    # DB에는 파일 URL 배열을 JSON으로 저장
    image_urls_json = json.dumps(image_urls) if image_urls else None
    query = """
    INSERT INTO messages (thread_id, user_id, message, message_type, image_urls, created_at)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
```

#### AI 모델 연동
이미지가 포함된 메시지를 AI 모델에 전달할 때:

```python
def send_to_ai_model(message, image_data=None):
    payload = {
        "message": message,
        "context": get_script_context()
    }
    
    if image_data:
        # 배열 형태로 정규화
        images = image_data if isinstance(image_data, list) else [image_data]
        
        # 이미지들을 AI 모델이 처리할 수 있는 형태로 변환
        payload["images"] = []
        for img_data in images:
            payload["images"].append({
                "type": "base64",
                "data": img_data
            })
    
    # AI 모델 API 호출
    response = ai_client.chat(payload)
    return response
```

### 4. 에러 처리

추가해야 할 에러 케이스:
- `400`: 이미지 데이터 형식 오류, 이미지 개수 초과
- `413`: 이미지 파일 크기 초과 (단일 또는 총합)
- `415`: 지원하지 않는 이미지 형식
- `500`: 이미지 처리 중 서버 오류

```python
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

def validate_image_data(image_data):
    if not image_data:
        return True
    
    # 배열 형태로 정규화
    images = image_data if isinstance(image_data, list) else [image_data]
    
    # 이미지 개수 제한
    if len(images) > 3:  # 최대 3개
        raise BadRequest("Too many images (max: 3)")
    
    total_size = 0
    
    for i, img_data in enumerate(images):
        try:
            # Base64 형식 검증
            if not img_data.startswith('data:image/'):
                raise BadRequest(f"Invalid image data format at index {i}")
                
            # 단일 이미지 크기 검증 (Base64는 원본의 약 1.33배)
            img_size = len(img_data)
            if img_size > 5 * 1024 * 1024 * 1.33:  # 5MB 제한
                raise RequestEntityTooLarge(f"Image {i+1} size too large (max: 5MB)")
            
            total_size += img_size
                
            # 이미지 형식 검증
            allowed_types = ['image/jpeg', 'image/png', 'image/gif']
            mime_type = img_data.split(';')[0].split(':')[1]
            if mime_type not in allowed_types:
                raise BadRequest(f"Unsupported image type at index {i}: {mime_type}")
                
        except Exception as e:
            if isinstance(e, (BadRequest, RequestEntityTooLarge)):
                raise
            raise BadRequest(f"Image validation failed at index {i}: {str(e)}")
    
    # 총 크기 검증
    if total_size > 10 * 1024 * 1024 * 1.33:  # 총 10MB 제한
        raise RequestEntityTooLarge("Total images size too large (max: 10MB)")
        
    return True
```

### 5. 프론트엔드에서 전송하는 데이터 형태

프론트엔드에서는 다음과 같은 형태로 이미지 데이터를 전송합니다:

```javascript
// 단일 이미지 첨부 시
const singleImageData = "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA...";

// 다중 이미지 첨부 시  
const multipleImageData = [
  "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEA...",
  "data:image/png;base64,iVBORw0KGgo..."
];

// API 호출 (단일/다중 이미지 모두 배열로 전송)
const imageData = Array.isArray(attachedImages) ? attachedImages : [attachedImages];

const response = await fetch('/api/chat/send', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    thread_id: threadId,
    site_code: siteCode,
    message: "이미지에 대한 설명이나 질문",
    script: currentScript,
    auto_deploy: false,
    image_data: imageData  // 항상 배열 형태로 전송
  })
});
```

### 6. 테스트 시나리오

1. **텍스트만 전송**: 기존 기능 정상 동작 확인
2. **단일 이미지만 전송**: 텍스트 없이 이미지 1개만 전송
3. **다중 이미지만 전송**: 텍스트 없이 이미지 여러 개 전송
4. **텍스트 + 단일 이미지**: 텍스트와 이미지 1개 함께 전송
5. **텍스트 + 다중 이미지**: 텍스트와 이미지 여러 개 함께 전송
6. **이미지 개수 초과**: 3개 초과 시 에러 처리
7. **대용량 이미지**: 단일/총합 크기 제한 초과 시 에러 처리
8. **잘못된 형식**: 잘못된 Base64 데이터 전송 시 에러 처리
9. **메시지 조회**: 저장된 이미지들이 올바르게 반환되는지 확인

### 7. 우선순위

1. **High**: 데이터베이스 스키마 변경 및 API 수정
2. **Medium**: 이미지 검증 로직 구현
3. **Low**: 파일 시스템 저장 방식으로 개선 (성능 최적화)

이 명세서를 참고하여 백엔드 구현을 진행해 주세요. 추가 질문이나 불분명한 부분이 있으면 언제든 문의해 주세요.