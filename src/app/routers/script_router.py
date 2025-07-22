from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
import logging

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sites/{site_code}/scripts", tags=["scripts"])
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)


@router.get("/")
async def get_site_scripts(site_code: str, user=Depends(get_current_user)):
    """특정 사이트의 현재 스크립트를 조회하는 API"""
    print(f"[ROUTER] get_site_scripts 스크립트 조회 요청: site_code={site_code}, user={user.id}")
    from main import script_service
    
    try:
        result = await script_service.get_site_scripts(user.id, site_code)
        
        if not result["success"]:
            raise HTTPException(status_code=result.get("status_code", 500), detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"],
            "message": "스크립트 조회 성공"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스크립트 조회 API 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.post("/deploy")
async def deploy_site_scripts(site_code: str, request: Request, user=Depends(get_current_user)):
    """특정 사이트에 스크립트를 배포하는 API"""
    from main import script_service
    
    try:
        request_data = await request.json()
        
        result = await script_service.deploy_site_scripts(user.id, site_code, request_data)
        
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
        logger.error(f"스크립트 배포 API 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })