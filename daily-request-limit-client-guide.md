# 일일 요청 제한 클라이언트 처리 가이드

## 개요
멤버십 레벨에 따라 AI 메시지 전송에 일일 요청 제한이 적용됩니다. 클라이언트에서 이 제한을 적절히 처리하는 방법을 안내합니다.

## 멤버십별 일일 요청 제한

| 멤버십 레벨 | 일일 요청 수 |
|------------|-------------|
| FREE (0)   | 10회        |
| BASIC (1)  | 20회        |
| PREMIUM (2)| 100회       |
| MAX (3)    | 무제한(-1)   |

## API 응답 처리

### 1. 정상 응답 (200 OK)
요청이 성공적으로 처리된 경우입니다.

```json
{
  "success": true,
  "data": {
    "message": "AI 응답 내용...",
    "thread_id": "uuid",
    "message_id": "uuid"
  }
}
```

### 2. 요청 제한 초과 (429 Too Many Requests)
일일 요청 제한을 초과한 경우입니다.

```json
{
  "success": false,
  "error": "일일 요청 제한을 초과했습니다. (제한: 10회)",
  "status_code": 429
}
```

## 클라이언트 처리 방법

### 1. JavaScript/TypeScript 예제

```javascript
async function sendMessage(message, threadId) {
  try {
    const response = await fetch('/api/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${accessToken}`
      },
      body: JSON.stringify({
        message: message,
        thread_id: threadId
      })
    });

    const data = await response.json();

    if (response.status === 429) {
      // 요청 제한 초과 처리
      handleRateLimitExceeded(data);
      return null;
    }

    if (!response.ok) {
      throw new Error(data.error || '메시지 전송 실패');
    }

    return data;
  } catch (error) {
    console.error('메시지 전송 오류:', error);
    throw error;
  }
}

function handleRateLimitExceeded(errorData) {
  // 1. 사용자에게 알림 표시
  showNotification({
    type: 'warning',
    title: '일일 요청 제한 초과',
    message: errorData.error,
    actions: [
      {
        text: '멤버십 업그레이드',
        onClick: () => redirectToMembershipPage()
      },
      {
        text: '내일 다시 시도',
        onClick: () => closeNotification()
      }
    ]
  });

  // 2. 메시지 입력 UI 비활성화
  disableMessageInput();

  // 3. 업그레이드 유도 UI 표시
  showUpgradePrompt();
}
```

### 2. React 컴포넌트 예제

```jsx
import React, { useState } from 'react';

const ChatInput = ({ threadId, onMessageSent }) => {
  const [message, setMessage] = useState('');
  const [isRateLimited, setIsRateLimited] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!message.trim() || isRateLimited) return;

    setLoading(true);
    try {
      const response = await sendMessage(message, threadId);
      
      if (response) {
        setMessage('');
        onMessageSent(response);
      }
    } catch (error) {
      if (error.status === 429) {
        setIsRateLimited(true);
      }
    } finally {
      setLoading(false);
    }
  };

  if (isRateLimited) {
    return (
      <div className="rate-limit-message">
        <h3>일일 요청 제한 초과</h3>
        <p>오늘의 메시지 전송 횟수를 모두 사용했습니다.</p>
        <div className="upgrade-options">
          <button onClick={() => window.location.href = '/membership'}>
            멤버십 업그레이드
          </button>
          <p className="reset-time">
            내일 0시에 요청 횟수가 초기화됩니다.
          </p>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="text"
        value={message}
        onChange={(e) => setMessage(e.target.value)}
        placeholder="메시지를 입력하세요..."
        disabled={loading}
      />
      <button type="submit" disabled={loading || !message.trim()}>
        {loading ? '전송 중...' : '전송'}
      </button>
    </form>
  );
};
```

## 사용자 경험 개선 방안

### 1. 요청 횟수 표시
사용자가 현재 사용량을 인지할 수 있도록 표시합니다.

```javascript
// 멤버십 정보 조회 API
async function getMembershipInfo() {
  const response = await fetch('/membership/limits', {
    headers: { 'Authorization': `Bearer ${accessToken}` }
  });
  return response.json();
}

// 사용량 표시 컴포넌트
const UsageIndicator = () => {
  const [usage, setUsage] = useState(null);

  useEffect(() => {
    getMembershipInfo().then(data => {
      const { daily_requests } = data.limits;
      const remaining = daily_requests === -1 ? '무제한' : 
        `${daily_requests - data.usage.current_requests}/${daily_requests}`;
      setUsage(remaining);
    });
  }, []);

  return (
    <div className="usage-indicator">
      남은 요청: {usage}
    </div>
  );
};
```

### 2. 예방적 알림
제한에 가까워지면 미리 알림을 표시합니다.

```javascript
function checkUsageWarning(currentUsage, limit) {
  const warningThreshold = Math.max(1, Math.floor(limit * 0.8)); // 80%
  
  if (currentUsage >= warningThreshold && currentUsage < limit) {
    showWarningNotification({
      message: `일일 요청 ${limit - currentUsage}회 남았습니다.`,
      action: '멤버십 업그레이드하기'
    });
  }
}
```

### 3. 오프라인 모드 지원
요청이 제한되었을 때 임시로 메시지를 저장해 두었다가 다음날 자동 전송하는 기능을 제공할 수 있습니다.

```javascript
// 로컬 스토리지에 대기 중인 메시지 저장
function queueMessageForTomorrow(message, threadId) {
  const queuedMessages = JSON.parse(localStorage.getItem('queuedMessages') || '[]');
  queuedMessages.push({
    message,
    threadId,
    queuedAt: new Date().toISOString()
  });
  localStorage.setItem('queuedMessages', JSON.stringify(queuedMessages));
}

// 자정 후 대기 중인 메시지 자동 전송
function checkAndSendQueuedMessages() {
  const queuedMessages = JSON.parse(localStorage.getItem('queuedMessages') || '[]');
  
  if (queuedMessages.length > 0) {
    // 사용자에게 확인 후 전송
    showQueuedMessagesDialog(queuedMessages);
  }
}
```

## 에러 처리 체크리스트

- [x] 429 상태 코드 감지
- [x] 사용자 친화적 오류 메시지 표시
- [x] 메시지 입력 UI 비활성화
- [x] 멤버십 업그레이드 유도
- [x] 요청 제한 해제 시간 안내 (다음날 0시)
- [x] 현재 사용량 표시
- [x] 예방적 경고 알림
- [x] 로컬 스토리지를 활용한 메시지 대기열 (선택사항)

## 멤버십 업그레이드 유도

요청 제한에 걸린 사용자를 적절히 상위 멤버십으로 유도하는 것이 중요합니다:

1. **명확한 혜택 제시**: 상위 등급의 요청 한도를 명시
2. **원클릭 업그레이드**: 결제 페이지로 바로 연결
3. **체험 기회 제공**: 24시간 무료 체험 등
4. **할인 쿠폰**: 첫 결제 시 할인 혜택

이러한 방식으로 처리하면 사용자 경험을 해치지 않으면서도 효과적으로 요청 제한을 관리할 수 있습니다.