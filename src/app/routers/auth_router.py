from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.auth_service import AuthService
from services.website_service import WebsiteService
from database_helper import DatabaseHelper
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["authentication"])
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

@router.delete("/auth/account")
async def delete_account(current_user = Depends(get_current_user)):
    """회원탈퇴 - 사용자 계정 완전 삭제"""
    try:
        from main import auth_service
        await auth_service.delete_user_account(current_user.id)
        
        return JSONResponse(
            status_code=200,
            content={"message": "계정이 성공적으로 삭제되었습니다"}
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"계정 삭제 API 오류: {e}")
        raise HTTPException(status_code=500, detail="계정 삭제 중 오류가 발생했습니다")

