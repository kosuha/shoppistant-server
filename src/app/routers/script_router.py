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


async def ensure_membership(user=Depends(get_current_user)):
    """구독 멤버십 보유 사용자만 접근 허용"""
    from main import db_helper
    membership = await db_helper.get_user_membership(user.id)
    if not membership:
        raise HTTPException(status_code=403, detail="구독 후 이용 가능한 기능입니다.")
    return user


@router.get("/", response_model=None)
@router.get("", response_model=None)
async def get_site_scripts(site_code: str, user=Depends(get_current_user)):
    """특정 사이트의 현재 스크립트를 조회하는 API"""
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
async def deploy_site_scripts(site_code: str, request: Request, user=Depends(ensure_membership)):
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
            "message": result["data"].get("message", "스크립트 배포 성공")
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스크립트 배포 API 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


# 별도 라우터: 스크립트/CSS 모듈 제공용 (인증 불필요)
module_router = APIRouter(prefix="/api/v1/sites/{site_code}", tags=["script-module"])

@module_router.get("/styles", response_class=None)
async def get_site_styles_module(site_code: str):
    """특정 사이트의 CSS를 제공하는 API (인증 불필요)"""
    from main import script_service
    from fastapi.responses import Response
    
    try:
        # 사이트 코드로 스크립트 조회 (공개 접근)
        script_data = await script_service.db_helper.get_site_script_by_code_public(site_code)
        
        if not script_data:
            # CSS가 없으면 빈 CSS 반환
            css_content = "/* No active styles found for this site */"
        else:
            css_content = script_data.get('css_content', '/* Empty styles */')
        
        # 사이트 도메인 조회하여 CORS Origin 설정
        site_domain = await script_service.db_helper.get_site_domain_by_code_public(site_code)
        cors_origin = site_domain if site_domain else "*"  # 도메인이 없으면 모든 도메인 허용
        
        # Content-Type을 text/css로 설정
        return Response(
            content=css_content,
            media_type="text/css",
            headers={
                "Cache-Control": "public, max-age=300",  # 5분간 캐시
                "Access-Control-Allow-Origin": cors_origin,  # 사이트별 CORS 허용
                "Access-Control-Allow-Methods": "GET",
                "Access-Control-Allow-Headers": "*"
            }
        )
        
    except Exception as e:
        logger.error(f"CSS 모듈 제공 API 실패: {e}")
        # 에러 상황에서도 유효한 CSS 반환
        error_css = f"/* CSS loading error: {str(e)} */"
        return Response(
            content=error_css,
            media_type="text/css",
            status_code=200  # CSS 로딩 에러를 방지하기 위해 200 반환
        )

@module_router.get("/script", response_class=None)
async def get_site_script_module(site_code: str):
    """특정 사이트의 JavaScript를 모듈 형태로 제공하는 API (인증 불필요)"""
    from main import script_service
    from fastapi.responses import Response
    
    try:
        # 사이트 코드로 스크립트 조회 (공개 접근)
        script_data = await script_service.db_helper.get_site_script_by_code_public(site_code)
        
        if not script_data:
            # JS가 없으면 빈 스크립트 반환
            js_content = "// No active script found for this site"
        else:
            # JavaScript는 script_content 컬럼 사용
            js_content = script_data.get('script_content', '// Empty script')
        
        # 사이트 도메인 조회하여 CORS Origin 설정
        site_domain = await script_service.db_helper.get_site_domain_by_code_public(site_code)
        cors_origin = site_domain if site_domain else "*"  # 도메인이 없으면 모든 도메인 허용
        
        # Content-Type을 application/javascript로 설정
        return Response(
            content=js_content,
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
        # 에러 상황에서도 유효한 JavaScript 반환
        error_script = f"// Script loading error: {str(e)}\nconsole.error('Script loading failed: {str(e)}');"
        return Response(
            content=error_script,
            media_type="application/javascript",
            status_code=200  # 스크립트 로딩 에러를 방지하기 위해 200 반환
        )