from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.thread_service import ThreadService
from schemas import ChatMessageUpdate
from utils.image_validator import ImageValidator
from core.responses import success_response, error_response
import logging
from typing import Any

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["threads", "messages"])
security = HTTPBearer()

"""
스레드/메시지 라우터
"""

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

def get_thread_service() -> ThreadService:
    """ThreadService 인스턴스를 가져오는 의존성"""
    from main import thread_service
    return thread_service


async def ensure_membership(user=Depends(get_current_user)):
    """멤버십이 있어야 접근 가능한 엔드포인트에서 사용"""
    from main import db_helper
    membership = await db_helper.get_user_membership(user.id)
    # membership_level > 0 이어야 구독 사용자로 간주
    if not membership or int(membership.get('membership_level', 0)) <= 0:
        raise HTTPException(status_code=403, detail="구독 후 이용 가능한 기능입니다.")
    return user


@router.get("/threads")
async def get_threads(
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """사용자의 모든 스레드 목록을 조회하는 API"""
    
    try:
        result = await thread_service.get_user_threads(user.id)
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(data=result["data"], message="스레드 목록 조회 성공")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 조회 실패: {e}")
        return error_response(message=str(e))


"""
update_message_status 엔드포인트가 파일 내에 중복 정의되어 있어 하나만 유지합니다.
아래 단일 구현을 사용합니다.
"""


@router.post("/threads", status_code=201)
async def create_thread(
    request: Request,
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """새로운 채팅 스레드를 생성하는 API"""
    
    try:
        request_data = await request.json()
        site_code = request_data.get("siteId")
        
        result = await thread_service.create_thread(user.id, site_code)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(data=result["data"], message="스레드가 성공적으로 생성되었습니다.")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 생성 실패: {e}")
        return error_response(message=str(e))


@router.get("/wallet")
async def get_wallet(
    user=Depends(get_current_user)
):
    """간단한 지갑 조회 (클라이언트 편의)"""
    try:
        from main import db_helper
        wallet = await db_helper.get_user_wallet(user.id)
        return success_response(data=wallet or {"balance_usd": 0, "total_spent_usd": 0}, message="지갑 조회 성공")
    except Exception as e:
        logger.error(f"지갑 조회 실패: {e}")
        return error_response(message=str(e))


 


@router.get("/threads/{thread_id}")
async def get_thread(
    thread_id: str,
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """특정 스레드의 상세 정보를 조회하는 API"""
    
    try:
        result = await thread_service.get_thread_by_id(user.id, thread_id)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(data=result["data"], message="스레드 조회 성공")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 조회 실패: {e}")
        return error_response(message=str(e))


 


@router.delete("/threads/{thread_id}")
async def delete_thread(
    thread_id: str,
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """특정 스레드를 삭제하는 API"""
    
    try:
        result = await thread_service.delete_thread(user.id, thread_id)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(message=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 삭제 실패: {e}")
        return error_response(message=str(e))


 


@router.put("/threads/{thread_id}/title")
async def update_thread_title(
    thread_id: str,
    request: Request,
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """스레드 제목을 업데이트하는 API"""
    
    try:
        request_data = await request.json()
        new_title = request_data.get("title", "").strip()
        
        result = await thread_service.update_thread_title(user.id, thread_id, new_title)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(data=result["data"], message=result["message"])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 제목 업데이트 실패: {e}")
        return error_response(message=str(e))


 


# 메시지 관련 엔드포인트들
@router.get("/messages/{thread_id}")
async def get_messages(
    thread_id: str,
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """특정 스레드의 모든 메시지를 조회하는 API"""
    
    try:
        result = await thread_service.get_thread_messages(user.id, thread_id)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(data=result["data"], message="메시지 목록 조회 성공")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메시지 조회 실패: {e}")
        return error_response(message=str(e))


@router.patch("/messages/{message_id}/status")
async def update_message_status(
    message_id: str,
    update_data: ChatMessageUpdate,
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """메시지 상태를 업데이트하는 API"""
    try:
        result = await thread_service.update_message_status(
            user_id=user.id,
            message_id=message_id,
            status=update_data.status,
            message=update_data.message,
            metadata=update_data.metadata
        )
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(data=result.get("data"), message=result.get("message", "메시지 상태가 성공적으로 업데이트되었습니다."))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메시지 상태 업데이트 실패: {e}")
        return error_response(message=str(e))

@router.post("/messages", status_code=201)
async def create_message(
    request: Request,
    user=Depends(ensure_membership),
    thread_service: ThreadService = Depends(get_thread_service)
):
    """새로운 메시지를 생성하는 API"""
    try:
        request_data = await request.json()
        thread_id = request_data.get("thread_id")
        message = request_data.get("message")
        message_type = request_data.get("message_type", "user")
        metadata = request_data.get("metadata")
        site_code = request_data.get("site_code")
        auto_deploy = request_data.get("auto_deploy", False)
        image_data = request_data.get("image_data")
        
        # 이미지 데이터 검증
        if image_data:
            ImageValidator.validate_image_data(image_data)

        result = await thread_service.create_message(user.id, site_code, thread_id, message, message_type, metadata, auto_deploy, image_data)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        return success_response(data=result["data"], message=result["message"]) 
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메시지 생성 실패: {e}")
        return error_response(message=str(e))


# 파일 내 단일 구현만 유지