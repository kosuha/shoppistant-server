from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sites", tags=["sites"])
websites_router = APIRouter(prefix="/api/v1", tags=["websites"])
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

@router.get("/", response_model=None)
@router.get("", response_model=None)  
async def get_user_sites(user=Depends(get_current_user)):
    """사용자의 연결된 사이트 목록을 조회하는 API"""
    from main import db_helper
    
    try:
        user_sites = await db_helper.get_user_sites(user.id, user.id)
        
        # 사이트 정보 정리 (domain 필드 추가, 토큰 정보 제거)
        safe_sites = []
        for site in user_sites:
            safe_site = {
                "id": site.get("id"),
                "site_code": site.get("site_code"),
                "site_name": site.get("site_name"),
                "domain": site.get("primary_domain"),  # 🆕 추가
                "created_at": site.get("created_at"),
                "updated_at": site.get("updated_at")
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


@websites_router.post("/websites")
async def add_website(request: Request, user=Depends(get_current_user)):
    """새로운 웹사이트 추가 - 도메인 기반 단순 연동"""
    from main import imweb_service
    
    try:
        request_data = await request.json()
        domain = request_data.get("domain")
        
        if not domain:
            raise HTTPException(status_code=400, detail="도메인이 필요합니다.")
        
        # 서비스를 통해 웹사이트 추가
        result = await imweb_service.add_website(user.id, domain)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"웹사이트 추가 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@websites_router.get("/websites")
async def get_websites(user=Depends(get_current_user)):
    """사용자의 웹사이트 목록 조회"""
    from main import imweb_service
    
    try:
        result = await imweb_service.get_sites(user.id)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"]
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"웹사이트 목록 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@websites_router.delete("/websites/{site_id}")
async def delete_website(site_id: str, user=Depends(get_current_user)):
    """웹사이트 삭제"""
    from main import imweb_service
    
    try:
        result = await imweb_service.delete_site(user.id, site_id)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "웹사이트가 성공적으로 삭제되었습니다."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"웹사이트 삭제 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@websites_router.patch("/websites/{site_id}")
async def update_website(site_id: str, request: Request, user=Depends(get_current_user)):
    """웹사이트 정보 업데이트 (현재는 사이트 이름만 지원)"""
    from main import imweb_service
    
    try:
        request_data = await request.json()
        site_name = request_data.get("site_name")
        
        if not site_name:
            raise HTTPException(status_code=400, detail="site_name이 필요합니다.")
        
        result = await imweb_service.update_site_name(user.id, site_id, site_name)
        
        if not result["success"]:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": result["data"],
            "message": "웹사이트 정보가 성공적으로 업데이트되었습니다."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"웹사이트 업데이트 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })