# 아임웹 AI Agent API 문서

## 개요

아임웹 쇼핑몰 운영자를 위한 AI 어시스턴트 API입니다. 사용자 인증, 사이트 관리, 채팅 기능을 제공합니다.

## Base URL

```
http://localhost:8000
```

## 인증

모든 API 엔드포인트는 Bearer Token을 사용한 인증이 필요합니다.

```
Authorization: Bearer {token}
```

## 공통 응답 형식

### 성공 응답
```json
{
  "status": "success",
  "data": {...}
}
```

### 에러 응답
```json
{
  "status": "error",
  "message": "에러 메시지"
}
```

## API 엔드포인트

### 1. 헬스 체크

#### GET /health
서버 상태를 확인합니다.

**Response:**
```json
{
  "status": "healthy"
}
```

### 2. API 상태 확인

#### GET /api/v1/status
API 버전과 서비스 상태를 확인합니다.

**Response:**
```json
{
  "api_version": "v1",
  "service": "imweb-ai-agent-server"
}
```

### 3. 사이트 관리

#### POST /api/v1/imweb/site-code
아임웹 사이트 코드를 등록합니다.

**Request Body:**
```json
{
  "site_code": "string"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "사이트 코드가 성공적으로 처리되었습니다.",
  "site_code": "string"
}
```

#### GET /api/v1/sites
사용자의 연결된 사이트 목록을 조회합니다.

**Response:**
```json
{
  "sites": [
    {
      "id": "string",
      "site_code": "string",
      "site_name": "string",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "status": "success"
}
```

### 4. 채팅 스레드 관리

#### GET /api/v1/threads
사용자의 모든 채팅 스레드를 조회합니다.

**Response:**
```json
{
  "threads": [
    {
      "id": "string",
      "user_id": "string",
      "site_id": "string",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z",
      "last_message_at": "2024-01-01T00:00:00Z"
    }
  ],
  "status": "success"
}
```

#### POST /api/v1/threads
새로운 채팅 스레드를 생성합니다.

**Request Body:**
```json
{
  "firstMessage": "string",
  "siteId": "string"
}
```

**Response:**
```json
{
  "threadId": "string",
  "status": "success",
  "message": "스레드가 성공적으로 생성되었습니다."
}
```

#### GET /api/v1/threads/{thread_id}
특정 스레드의 정보를 조회합니다.

**Parameters:**
- `thread_id`: 스레드 ID (path parameter)

**Response:**
```json
{
  "thread": {
    "id": "string",
    "user_id": "string",
    "site_id": "string",
    "created_at": "2024-01-01T00:00:00Z",
    "updated_at": "2024-01-01T00:00:00Z",
    "last_message_at": "2024-01-01T00:00:00Z"
  },
  "status": "success"
}
```

#### DELETE /api/v1/threads/{thread_id}
특정 스레드를 삭제합니다.

**Parameters:**
- `thread_id`: 스레드 ID (path parameter)

**Response:**
```json
{
  "status": "success",
  "message": "스레드가 성공적으로 삭제되었습니다."
}
```

### 5. 메시지 관리

#### GET /api/v1/messages/{thread_id}
특정 스레드의 모든 메시지를 조회합니다.

**Parameters:**
- `thread_id`: 스레드 ID (path parameter)

**Response:**
```json
{
  "messages": [
    {
      "id": "string",
      "thread_id": "string",
      "user_id": "string",
      "message": "string",
      "message_type": "user|assistant|system",
      "metadata": "string",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "status": "success"
}
```

#### POST /api/v1/messages
새로운 메시지를 생성합니다. 사용자 메시지인 경우 자동으로 AI 응답을 생성합니다.

**Request Body:**
```json
{
  "thread_id": "string",
  "message": "string",
  "message_type": "user|assistant|system",
  "metadata": "string"
}
```

**Response:**
```json
{
  "user_message": {
    "id": "string",
    "thread_id": "string",
    "user_id": "string",
    "message": "string",
    "message_type": "user",
    "metadata": "string",
    "created_at": "2024-01-01T00:00:00Z"
  },
  "ai_message": {
    "id": "string",
    "thread_id": "string",
    "user_id": "string",
    "message": "string",
    "message_type": "assistant",
    "created_at": "2024-01-01T00:00:00Z"
  },
  "status": "success"
}
```

## 에러 코드

| 상태 코드 | 설명 |
|-----------|------|
| 400 | 잘못된 요청 |
| 401 | 인증 실패 |
| 403 | 접근 권한 없음 |
| 404 | 리소스를 찾을 수 없음 |
| 500 | 내부 서버 오류 |

## 사용 예시

### 1. 새로운 채팅 스레드 생성
```javascript
// 1. 새 스레드 생성
const createThreadResponse = await fetch('/api/v1/threads', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_TOKEN'
  },
  body: JSON.stringify({
    firstMessage: '안녕하세요, 쇼핑몰 관리에 대해 문의드립니다.',
    siteId: 'site_123'
  })
});

const threadData = await createThreadResponse.json();
console.log(threadData.threadId); // 생성된 스레드 ID
```

### 2. 메시지 전송 및 AI 응답 받기
```javascript
// 2. 메시지 전송
const sendMessageResponse = await fetch('/api/v1/messages', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer YOUR_TOKEN'
  },
  body: JSON.stringify({
    thread_id: threadData.threadId,
    message: '상품 등록 방법을 알려주세요.',
    message_type: 'user'
  })
});

const messageData = await sendMessageResponse.json();
console.log(messageData.user_message); // 사용자 메시지
console.log(messageData.ai_message);   // AI 응답
```

### 3. 스레드 메시지 조회
```javascript
// 3. 스레드의 모든 메시지 조회
const getMessagesResponse = await fetch(`/api/v1/messages/${threadData.threadId}`, {
  headers: {
    'Authorization': 'Bearer YOUR_TOKEN'
  }
});

const messagesData = await getMessagesResponse.json();
console.log(messagesData.messages); // 메시지 목록
```

## 프론트엔드 구현 가이드

### 1. 실시간 채팅 구현
```javascript
class ChatManager {
  constructor(token) {
    this.token = token;
    this.baseUrl = 'http://localhost:8000';
  }

  async createThread(siteId, firstMessage) {
    const response = await fetch(`${this.baseUrl}/api/v1/threads`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.token}`
      },
      body: JSON.stringify({
        firstMessage,
        siteId
      })
    });
    return await response.json();
  }

  async sendMessage(threadId, message) {
    const response = await fetch(`${this.baseUrl}/api/v1/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.token}`
      },
      body: JSON.stringify({
        thread_id: threadId,
        message,
        message_type: 'user'
      })
    });
    return await response.json();
  }

  async getMessages(threadId) {
    const response = await fetch(`${this.baseUrl}/api/v1/messages/${threadId}`, {
      headers: {
        'Authorization': `Bearer ${this.token}`
      }
    });
    return await response.json();
  }
}
```

### 2. React 컴포넌트 예시
```jsx
import React, { useState, useEffect } from 'react';

const ChatComponent = ({ token, siteId }) => {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [threadId, setThreadId] = useState(null);
  const [loading, setLoading] = useState(false);

  const chatManager = new ChatManager(token);

  const startChat = async (firstMessage) => {
    setLoading(true);
    try {
      const result = await chatManager.createThread(siteId, firstMessage);
      setThreadId(result.threadId);
      
      // 메시지 조회
      const messagesResult = await chatManager.getMessages(result.threadId);
      setMessages(messagesResult.messages);
    } catch (error) {
      console.error('채팅 시작 실패:', error);
    } finally {
      setLoading(false);
    }
  };

  const sendMessage = async () => {
    if (!input.trim() || loading) return;
    
    setLoading(true);
    try {
      const result = await chatManager.sendMessage(threadId, input);
      
      // 메시지 목록 업데이트
      setMessages(prev => [...prev, result.user_message]);
      if (result.ai_message) {
        setMessages(prev => [...prev, result.ai_message]);
      }
      
      setInput('');
    } catch (error) {
      console.error('메시지 전송 실패:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-container">
      <div className="messages">
        {messages.map((msg, index) => (
          <div key={index} className={`message ${msg.message_type}`}>
            <strong>{msg.message_type === 'user' ? '사용자' : 'AI'}:</strong>
            <p>{msg.message}</p>
          </div>
        ))}
      </div>
      
      <div className="input-area">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyPress={(e) => e.key === 'Enter' && sendMessage()}
          placeholder="메시지를 입력하세요..."
          disabled={loading}
        />
        <button onClick={sendMessage} disabled={loading || !input.trim()}>
          {loading ? '전송 중...' : '전송'}
        </button>
      </div>
    </div>
  );
};
```

이 API 문서는 프론트엔드 개발자가 쉽게 이해하고 구현할 수 있도록 실제 사용 예시와 함께 작성되었습니다.