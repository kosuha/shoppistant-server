# Playwright MCP 서버 통합

## 개요

이 프로젝트는 이제 두 개의 MCP 서버를 지원합니다:
1. **아임웹 MCP 서버** (포트 8001): 아임웹 API 도구들 제공
2. **Playwright MCP 서버** (포트 8002): 브라우저 자동화 도구들 제공

## 아키텍처

```
Main Server (8000)
├── Gemini AI API
├── Imweb MCP Server (8001)
│   ├── site_info
│   ├── member_info
│   ├── community
│   ├── promotion
│   └── product
└── Playwright MCP Server (8002)
    ├── browser_navigate
    ├── browser_click
    ├── browser_type
    ├── browser_get_text
    ├── browser_screenshot
    ├── browser_wait_for
    └── browser_evaluate
```

## 새로 추가된 브라우저 도구들

### 1. browser_navigate
웹페이지로 이동합니다.
```json
{
  "url": "https://example.com"
}
```

### 2. browser_click
엘리먼트를 클릭합니다.
```json
{
  "selector": "button#submit"
}
```

### 3. browser_type
입력 필드에 텍스트를 입력합니다.
```json
{
  "selector": "input[name='username']",
  "text": "myusername"
}
```

### 4. browser_get_text
엘리먼트의 텍스트를 가져옵니다.
```json
{
  "selector": ".product-title"
}
```

### 5. browser_screenshot
현재 페이지의 스크린샷을 찍습니다.
```json
{
  "fullPage": true
}
```

### 6. browser_wait_for
엘리먼트가 나타날 때까지 기다립니다.
```json
{
  "selector": ".loading-complete",
  "timeout": 30000
}
```

### 7. browser_evaluate
JavaScript 코드를 실행합니다.
```json
{
  "script": "document.title"
}
```

## 사용 예시

사용자가 AI 에이전트에게 다음과 같이 요청할 수 있습니다:

1. **경쟁사 가격 조사**: "네이버 쇼핑에서 '무선 이어폰' 가격을 조사해주세요"
2. **웹사이트 테스트**: "우리 쇼핑몰 로그인 기능이 제대로 작동하는지 테스트해주세요"
3. **스크린샷 캡처**: "경쟁사 홈페이지 스크린샷을 찍어주세요"
4. **자동 데이터 수집**: "특정 사이트에서 상품 정보를 수집해주세요"

## 환경 설정

`.env` 파일에 다음 환경 변수를 추가해야 합니다:

```env
PLAYWRIGHT_MCP_SERVER_URL=http://playwright-mcp-server:8002
```

## 배포

Docker Compose를 사용하여 모든 서비스를 한번에 배포할 수 있습니다:

```bash
docker-compose up -d
```

## 헬스 체크

다음 엔드포인트에서 모든 MCP 서버의 연결 상태를 확인할 수 있습니다:

```bash
curl http://localhost:8000/health
```

응답 예시:
```json
{
  "status": "success",
  "data": {
    "database": {"connected": true},
    "imweb_mcp_client": "connected",
    "playwright_mcp_client": "connected",
    "timestamp": "2024-01-01T12:00:00Z"
  },
  "message": "헬스 체크 성공"
}
```

## 주의사항

1. Playwright MCP 서버는 브라우저를 실행하므로 추가 메모리와 CPU 리소스가 필요합니다.
2. 브라우저 자동화 시 웹사이트의 robots.txt와 이용약관을 준수해야 합니다.
3. 요청 빈도를 적절히 제한하여 서버에 과부하를 주지 않도록 주의해야 합니다.