from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse, Response
import logging

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from core.factory import ServiceFactory
from core.responses import success_response, error_response, BusinessException
from core.interfaces import IScriptService, IAuthService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sites/{site_code}/scripts", tags=["scripts"])
security = HTTPBearer()

# 의존성 주입 함수들
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성 - 리팩토링 버전"""
    auth_service = ServiceFactory.get_auth_service()
    return await auth_service.verify_auth(credentials)

def get_script_service() -> IScriptService:
    """스크립트 서비스 의존성"""
    return ServiceFactory.get_script_service()

@router.get("/", response_model=None)
@router.get("", response_model=None)
async def get_site_scripts(
    site_code: str, 
    user=Depends(get_current_user),
    script_service: IScriptService = Depends(get_script_service)
):
    """특정 사이트의 현재 스크립트를 조회하는 API - 리팩토링 버전"""
    logger.info(f"스크립트 조회 요청: site_code={site_code}, user={user.id}")
    
    try:
        result = await script_service.get_site_scripts(user.id, site_code)
        
        if not result["success"]:
            status_code = result.get("status_code", 500)
            error_msg = result.get("error", "알 수 없는 오류")
            raise HTTPException(status_code=status_code, detail=error_msg)
        
        return JSONResponse(
            status_code=200, 
            content=success_response(
                data=result["data"],
                message="스크립트 조회 성공"
            ).dict()
        )
        
    except HTTPException:
        raise
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"스크립트 조회 API 실패: {e}")
        raise HTTPException(status_code=500, detail="스크립트 조회 중 오류가 발생했습니다")

@router.post("/deploy")
async def deploy_site_scripts(
    site_code: str, 
    request: Request, 
    user=Depends(get_current_user),
    script_service: IScriptService = Depends(get_script_service)
):
    """특정 사이트에 스크립트를 배포하는 API - 리팩토링 버전"""
    logger.info(f"스크립트 배포 요청: site_code={site_code}, user={user.id}")
    
    try:
        request_data = await request.json()
        
        result = await script_service.deploy_site_scripts(user.id, site_code, request_data)
        
        if not result["success"]:
            status_code = result.get("status_code", 500)
            error_msg = result.get("error", "알 수 없는 오류")
            raise HTTPException(status_code=status_code, detail=error_msg)
        
        return JSONResponse(
            status_code=200, 
            content=success_response(
                data=result["data"],
                message=result.get("message", "스크립트 배포 성공")
            ).dict()
        )
        
    except HTTPException:
        raise
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except Exception as e:
        logger.error(f"스크립트 배포 API 실패: {e}")
        raise HTTPException(status_code=500, detail="스크립트 배포 중 오류가 발생했습니다")

# 별도 라우터: 스크립트 모듈 제공용 (인증 불필요)
module_router = APIRouter(prefix="/api/v1/sites/{site_code}", tags=["script-module"])

@module_router.get("/script", response_class=None)
async def get_site_script_module(
    site_code: str,
    script_service: IScriptService = Depends(get_script_service)
):
    """특정 사이트의 스크립트를 모듈 형태로 제공하는 API (인증 불필요) - 리팩토링 버전"""
    
    try:
        # 사이트 코드로 스크립트 조회 (공개 접근)
        db_helper = ServiceFactory.get_db_helper()
        script_data = await db_helper.get_site_script_by_code_public(site_code)
        
        if not script_data:
            # 스크립트가 없으면 빈 스크립트 반환
            script_content = "// No active script found for this site"
        else:
            script_content = script_data.get('script_content', '// Empty script')
        
        # 사이트 도메인 조회하여 CORS Origin 설정
        site_domain = await db_helper.get_site_domain_by_code_public(site_code)
        cors_origin = site_domain if site_domain else "*"  # 도메인이 없으면 모든 도메인 허용
        
        # Content-Type을 application/javascript로 설정
        return Response(
            content=script_content,
            media_type="application/javascript",
            headers={
                "Cache-Control": "public, max-age=300",  # 5분간 캐시
                "Access-Control-Allow-Origin": cors_origin,  # 사이트별 CORS 허용
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except Exception as e:
        logger.error(f"스크립트 모듈 제공 API 실패: {e}")
        return Response(
            content="// Error loading script",
            media_type="application/javascript",
            status_code=500
        )

# 기존 호환성을 위한 함수들 (deprecated)
async def get_current_user_legacy(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """레거시 호환성을 위한 함수"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)
