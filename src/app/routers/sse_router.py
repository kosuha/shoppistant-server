from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.thread_service import ThreadService
import logging
import json
import asyncio
from typing import Dict

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["sse", "real-time"])
security = HTTPBearer()

# 메시지 상태 변화를 추적하기 위한 전역 저장소
message_status_subscribers: Dict[str, list] = {}

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

def get_thread_service() -> ThreadService:
    """ThreadService 인스턴스를 가져오는 의존성"""
    from main import thread_service
    return thread_service


@router.get("/threads/{thread_id}/messages/status-stream")
async def stream_message_status(
    thread_id: str,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """메시지 상태 변화를 실시간으로 스트리밍하는 SSE 엔드포인트"""
    
    async def event_stream():
        try:
            # 스레드 권한 확인
            thread = await thread_service.get_thread_by_id(user.id, thread_id)
            if not thread["success"]:
                yield f"data: {json.dumps({'error': 'Thread not found'})}\n\n"
                return
            
            # 현재 스레드의 모든 메시지 상태 전송
            messages_result = await thread_service.get_thread_messages(user.id, thread_id)
            if messages_result["success"]:
                for message in messages_result["data"]["messages"]:
                    yield f"data: {json.dumps({
                        'type': 'initial',
                        'message_id': message['id'],
                        'status': message.get('status', 'completed'),
                        'message': message['message'],
                        'message_type': message['message_type'],
                        'created_at': message['created_at']
                    })}\n\n"
            
            # 구독자 목록에 추가
            if thread_id not in message_status_subscribers:
                message_status_subscribers[thread_id] = []
            
            queue = asyncio.Queue()
            message_status_subscribers[thread_id].append(queue)
            
            try:
                while True:
                    # 큐에서 상태 변화 대기
                    try:
                        status_update = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(status_update)}\n\n"
                    except asyncio.TimeoutError:
                        # 연결 유지를 위한 heartbeat
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                        
            except Exception as e:
                logger.error(f"SSE 스트림 오류: {e}")
            finally:
                # 구독자 목록에서 제거
                if thread_id in message_status_subscribers:
                    try:
                        message_status_subscribers[thread_id].remove(queue)
                        if not message_status_subscribers[thread_id]:
                            del message_status_subscribers[thread_id]
                    except ValueError:
                        pass
                        
        except Exception as e:
            logger.error(f"SSE 이벤트 스트림 오류: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
        }
    )


# 메시지 상태 브로드캐스트 함수
async def broadcast_message_status(thread_id: str, message_id: str, status: str, message: str = None):
    """메시지 상태 변화를 모든 구독자에게 브로드캐스트"""
    if thread_id in message_status_subscribers:
        status_update = {
            'type': 'status_update',
            'message_id': message_id,
            'status': status,
            'message': message,
            'timestamp': asyncio.get_event_loop().time()
        }
        
        # 모든 구독자에게 상태 변화 알림
        for queue in message_status_subscribers[thread_id][:]:  # 복사본으로 순회
            try:
                await queue.put(status_update)
            except Exception as e:
                logger.error(f"브로드캐스트 실패: {e}")
                # 실패한 큐는 제거
                try:
                    message_status_subscribers[thread_id].remove(queue)
                except ValueError:
                    pass


@router.get("/messages/{message_id}/status")
async def get_message_status(
    message_id: str,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """특정 메시지의 현재 상태를 조회하는 폴링 엔드포인트"""
    try:
        from database_helper import DatabaseHelper
        from main import db_helper
        
        # 메시지 조회
        client = db_helper._get_client(use_admin=True)
        result = client.table('chat_messages').select('*').eq('id', message_id).execute()
        
        if not result.data:
            return {"success": False, "error": "메시지를 찾을 수 없습니다.", "status_code": 404}
            
        message_data = result.data[0]
        
        # 스레드 소유권 확인
        thread = await thread_service.get_thread_by_id(user.id, message_data['thread_id'])
        if not thread["success"]:
            return {"success": False, "error": "메시지에 접근할 권한이 없습니다.", "status_code": 403}
        
        return {
            "success": True,
            "data": {
                "message_id": message_id,
                "status": message_data.get('status', 'completed'),
                "message": message_data['message'],
                "message_type": message_data['message_type'],
                "created_at": message_data['created_at'],
                "metadata": message_data.get('metadata', {})
            }
        }
        
    except Exception as e:
        logger.error(f"메시지 상태 조회 실패: {e}")
        return {"success": False, "error": str(e), "status_code": 500}