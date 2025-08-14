from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.thread_service import ThreadService
import logging
import json
import asyncio
from typing import Dict, Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["sse", "real-time"])
security = HTTPBearer()

# 메시지 상태 변화를 추적하기 위한 전역 저장소
message_status_subscribers: Dict[str, list] = {}

# SSE 연결 관리를 위한 전역 변수
active_sse_connections = set()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

async def get_current_user_from_token(token: str):
    """URL 파라미터 토큰으로부터 현재 사용자 정보를 가져오는 함수"""
    from main import auth_service
    from fastapi.security import HTTPAuthorizationCredentials
    
    try:
        # 토큰을 HTTPAuthorizationCredentials 형태로 변환
        credentials = HTTPAuthorizationCredentials(
            scheme="Bearer",
            credentials=token
        )
        return await auth_service.verify_auth(credentials)
    except Exception as e:
        logger.error(f"토큰 인증 실패: {e}")
        raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")

def get_thread_service() -> ThreadService:
    """ThreadService 인스턴스를 가져오는 의존성"""
    from main import thread_service
    return thread_service


@router.get("/threads/{thread_id}/messages/status-stream")
async def stream_message_status(
    thread_id: str,
    token: Optional[str] = Query(None, description="JWT 인증 토큰 (URL 파라미터)"),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """메시지 상태 변화를 실시간으로 스트리밍하는 SSE 엔드포인트
    
    두 가지 인증 방식을 지원:
    1. Authorization 헤더 (기본)
    2. URL 파라미터 token (SSE용)
    """
    
    # 인증 방식 결정 - URL 파라미터 토큰이 있으면 우선 사용
    user = None
    if token:
        try:
            user = await get_current_user_from_token(token)
        except HTTPException:
            # URL 파라미터 토큰 인증 실패 시 401 반환
            return StreamingResponse(
                iter([f"data: {json.dumps({'error': 'Invalid token'})}\n\n"]),
                media_type="text/event-stream",
                status_code=401,
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "*",
                    "Access-Control-Allow-Credentials": "false",
                }
            )
    else:
        # Authorization 헤더 방식은 FastAPI의 의존성 주입으로 처리되지 않으므로
        # 수동으로 처리해야 함
        return StreamingResponse(
            iter([f"data: {json.dumps({'error': 'Token required for SSE'})}\n\n"]),
            media_type="text/event-stream",
            status_code=401,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Allow-Credentials": "false",
            }
        )
    
    async def event_stream():
        connection_id = id(asyncio.current_task())
        active_sse_connections.add(connection_id)
        
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
                    # metadata가 JSON 문자열이면 파싱
                    metadata = message.get('metadata', {})
                    if isinstance(metadata, str):
                        try:
                            metadata = json.loads(metadata)
                        except (json.JSONDecodeError, TypeError):
                            metadata = {}
                    
                    yield f"data: {json.dumps({
                        'type': 'initial',
                        'message_id': message['id'],
                        'status': message.get('status', 'completed'),
                        'message': message['message'],
                        'message_type': message['message_type'],
                        'created_at': message['created_at'],
                        'metadata': metadata
                    })}\n\n"
            
            # 구독자 목록에 추가
            if thread_id not in message_status_subscribers:
                message_status_subscribers[thread_id] = []
            
            queue = asyncio.Queue()
            message_status_subscribers[thread_id].append(queue)
            
            try:
                while connection_id in active_sse_connections:
                    # shutdown 신호 확인
                    from main import shutdown_event
                    if shutdown_event.is_set():
                        break
                    
                    # 큐에서 상태 변화 대기
                    try:
                        status_update = await asyncio.wait_for(queue.get(), timeout=5.0)
                        yield f"data: {json.dumps(status_update)}\n\n"
                    except asyncio.TimeoutError:
                        # 연결 유지를 위한 heartbeat
                        yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
                        
            except asyncio.CancelledError:
                raise
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
        finally:
            # 연결 정리
            active_sse_connections.discard(connection_id)
    
    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Credentials": "false",
            "X-Accel-Buffering": "no",  # Nginx 버퍼링 비활성화
        }
    )


@router.options("/threads/{thread_id}/messages/status-stream")
async def stream_message_status_options(thread_id: str):
    """SSE 엔드포인트에 대한 CORS preflight 요청 처리"""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Credentials": "false",
            "Access-Control-Max-Age": "3600",
        }
    )


# 메시지 상태 브로드캐스트 함수
async def broadcast_message_status(thread_id: str, message_id: str, status: str, message: str = None, metadata: dict = None):
    """메시지 상태 변화를 모든 구독자에게 브로드캐스트"""
    if thread_id in message_status_subscribers:
        status_update = {
            'type': 'status_update',
            'message_id': message_id,
            'status': status,
            'message': message,
            'metadata': metadata or {},
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


async def cleanup_all_sse_connections():
    """모든 SSE 연결을 정리하는 함수"""
    
    # 모든 활성 연결을 비활성화
    connections_to_clean = active_sse_connections.copy()
    active_sse_connections.clear()
    
    # 구독자 목록도 정리
    message_status_subscribers.clear()
    
