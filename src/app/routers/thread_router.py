from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.thread_service import ThreadService
from services.auth_service import AuthService
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["threads", "messages"])
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

def get_thread_service() -> ThreadService:
    """ThreadService 인스턴스를 가져오는 의존성"""
    from main import thread_service
    return thread_service


@router.get("/threads")
async def get_threads(
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    print(f"[ROUTER] get_threads 스레드 조회 요청: user={user.id}")
    """사용자의 모든 스레드 목록을 조회하는 API"""
    
    try:
        result = await thread_service.get_user_threads(user.id)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"],
            "message": "스레드 목록 조회 성공"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.post("/threads")
async def create_thread(
    request: Request,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """새로운 채팅 스레드를 생성하는 API"""
    
    try:
        request_data = await request.json()
        site_code = request_data.get("siteId")
        
        result = await thread_service.create_thread(user.id, site_code)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        
        return JSONResponse(status_code=201, content={
            "status": "success",
            "message": "스레드가 성공적으로 생성되었습니다.",
            "data": result["data"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    print(f"[ROUTER] get_thread 스레드 조회 요청: thread_id={thread_id}, user={user.id}")
    """특정 스레드의 상세 정보를 조회하는 API"""
    
    try:
        result = await thread_service.get_thread_by_id(user.id, thread_id)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"],
            "message": "스레드 조회 성공"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """특정 스레드를 삭제하는 API"""
    
    try:
        result = await thread_service.delete_thread(user.id, thread_id)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": result["message"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 삭제 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.put("/threads/{thread_id}/title")
async def update_thread_title(
    thread_id: str,
    request: Request,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """스레드 제목을 업데이트하는 API"""
    
    try:
        request_data = await request.json()
        new_title = request_data.get("title", "").strip()
        
        result = await thread_service.update_thread_title(user.id, thread_id, new_title)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"],
            "message": result["message"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 제목 업데이트 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


# 메시지 관련 엔드포인트들
@router.get("/messages/{thread_id}")
async def get_messages(
    thread_id: str,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """특정 스레드의 모든 메시지를 조회하는 API"""
    
    try:
        result = await thread_service.get_thread_messages(user.id, thread_id)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"],
            "message": "메시지 목록 조회 성공"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메시지 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.post("/messages")
async def create_message(
    request: Request,
    user=Depends(get_current_user),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """새로운 메시지를 생성하는 API"""
    print(f"[ROUTER] create_message 메시지 생성 요청: user={user.id}")
    try:
        request_data = await request.json()
        thread_id = request_data.get("thread_id")
        message = request_data.get("message")
        message_type = request_data.get("message_type", "user")
        metadata = request_data.get("metadata")

        result = await thread_service.create_message(user.id, thread_id, message, message_type, metadata)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])

        return JSONResponse(status_code=201, content={
            "status": "success",
            "data": result["data"],
            "message": result["message"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })