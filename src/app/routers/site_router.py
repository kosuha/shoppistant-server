from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from services.imweb_service import ImwebService
from database_helper import DatabaseHelper
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sites", tags=["sites"])
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

@router.get("/")
async def get_user_sites(user=Depends(get_current_user)):
    """사용자의 연결된 사이트 목록을 조회하는 API"""
    from main import imweb_service, db_helper
    
    try:
        print(f"[ROUTER] 사용자 사이트 조회 요청: user={user}")
        user_sites = await db_helper.get_user_sites(user.id, user.id)
        
        # 민감한 정보 제거 (토큰 정보 숨김)
        safe_sites = []
        for site in user_sites:
            site_name = site.get("site_name")
            if site.get("access_token"):
                try:
                    site_info = await imweb_service.fetch_site_info_from_imweb(site["access_token"])
                    if site_info["success"]:
                        site_name = site_info["data"].get('unitList')[0].get('name', site.get("site_name"))
                except Exception as e:
                    logger.warning(f"사이트 이름 조회 실패: {e}")

            safe_site = {
                "id": site.get("id"),
                "site_code": site.get("site_code"),
                "site_name": site_name,
                "created_at": site.get("created_at"),
                "updated_at": site.get("updated_at"),
                "token_configured": bool(site.get("access_token"))
            }
            safe_sites.append(safe_site)
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": {"sites": safe_sites},
            "message": "사이트 목록 조회 성공"
        })
        
    except Exception as e:
        logger.error(f"[ROUTER] 사용자 사이트 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })