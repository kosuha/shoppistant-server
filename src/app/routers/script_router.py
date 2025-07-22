from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sites/{site_id}/scripts", tags=["scripts"])


def get_current_user():
    # 의존성 주입 함수는 main.py에서 설정할 예정
    pass


@router.get("/")
async def get_site_scripts(site_id: str, user=Depends(get_current_user)):
    """특정 사이트의 현재 스크립트를 조회하는 API"""
    from main import script_service
    
    try:
        result = await script_service.get_site_scripts(user.id, site_id)
        
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
async def deploy_site_scripts(site_id: str, request: Request, user=Depends(get_current_user)):
    """특정 사이트에 스크립트를 배포하는 API"""
    from main import script_service
    
    try:
        request_data = await request.json()
        
        result = await script_service.deploy_site_scripts(user.id, site_id, request_data)
        
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