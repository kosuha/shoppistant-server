from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from services.auth_service import AuthService
from services.imweb_service import ImwebService
from database_helper import DatabaseHelper
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["authentication"])
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

@router.post("/tokens")
async def set_access_token(
    request: Request, 
    user=Depends(get_current_user)
):
    """사용자의 아임웹 API 액세스 토큰을 설정하는 API"""
    from main import imweb_service, db_helper
    
    try:
        request_data = await request.json()
        site_code = request_data.get("site_code")
        access_token = request_data.get("access_token")
        
        if not site_code or not access_token:
            raise HTTPException(status_code=400, detail="사이트 코드와 액세스 토큰이 필요합니다.")
        
        # 기존 사이트 확인
        existing_site = await db_helper.get_user_site_by_code(user.id, site_code)
        
        if existing_site:
            success = await db_helper.update_user_site_tokens(user.id, site_code, access_token)
            if not success:
                raise HTTPException(status_code=500, detail="토큰 업데이트에 실패했습니다.")
        else:
            site_data = await db_helper.create_user_site(user.id, site_code, access_token=access_token)
            if not site_data:
                raise HTTPException(status_code=500, detail="사이트 생성에 실패했습니다.")
        
        # 로그 기록
        await db_helper.log_system_event(
            user_id=user.id,
            event_type='token_set',
            event_data={'site_code': site_code, 'action': 'manual_set'}
        )
        
        # 사이트 정보 업데이트
        try:
            site_info_result = await imweb_service.fetch_site_info_from_imweb(access_token)
            if site_info_result["success"]:
                site_data = site_info_result["data"]
                imweb_site_name = site_data.get('unitList')[0].get('name')
                if imweb_site_name:
                    await db_helper.update_site_name(user.id, site_code, imweb_site_name)
        except Exception as name_update_error:
            logger.warning(f"사이트 이름 자동 업데이트 실패: {name_update_error}")
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "액세스 토큰이 저장되었습니다."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"토큰 설정 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.post("/imweb/site-code")
async def api_imweb_site_code(request: Request, user=Depends(get_current_user)):
    """클라이언트로부터 받은 ImWeb 사이트 코드를 처리하는 API"""
    from main import db_helper
    
    try:
        request_data = await request.json()
        site_code = request_data.get("site_code")

        if not site_code:
            raise HTTPException(status_code=400, detail="사이트 코드가 필요합니다.")

        # 기존 사이트가 있는지 확인
        existing_site = await db_helper.get_user_site_by_code(user.id, site_code)
        
        if not existing_site:
            # 새로운 사이트 코드 저장
            site_data = await db_helper.create_user_site(user.id, site_code)
            if not site_data:
                raise HTTPException(status_code=500, detail="사이트 생성에 실패했습니다.")
            
            # 로그 기록
            await db_helper.log_system_event(
                user_id=user.id,
                event_type='site_connected',
                event_data={'site_code': site_code}
            )

        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "사이트 코드가 성공적으로 처리되었습니다.",
            "data": {"site_code": site_code}
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.post("/auth-code")
async def auth_code(request: Request, user=Depends(get_current_user)):
    """OAuth 인가 코드로 토큰 발급"""
    from main import imweb_service, db_helper
    
    try:
        request_data = await request.json()
        auth_code = request_data.get("auth_code")
        site_code = request_data.get("site_code")

        if not auth_code or not site_code:
            raise HTTPException(status_code=400, detail="인증 코드와 사이트 코드가 필요합니다.")
        
        # OAuth 토큰 발급
        token_result = await imweb_service.get_oauth_token(auth_code)
        if not token_result["success"]:
            raise HTTPException(status_code=500, detail=token_result["error"])
        
        access_token = token_result["access_token"]
        refresh_token = token_result["refresh_token"]
        
        # 데이터베이스에 사용자 사이트 정보 저장
        existing_site = await db_helper.get_user_site_by_code(user.id, site_code)
        
        if existing_site:
            success = await db_helper.update_user_site_tokens(user.id, site_code, access_token, refresh_token)
            if not success:
                raise HTTPException(status_code=500, detail="토큰 업데이트에 실패했습니다.")
        else:
            site_data = await db_helper.create_user_site(user.id, site_code, access_token=access_token, refresh_token=refresh_token)
            if not site_data:
                raise HTTPException(status_code=500, detail="사이트 생성에 실패했습니다.")
        
        # 로그 기록
        await db_helper.log_system_event(
            user_id=user.id,
            event_type='oauth_token_received',
            event_data={'site_code': site_code, 'source': 'oauth_flow'}
        )
        
        # 아임웹에 연동 완료 요청
        integration_result = await imweb_service.complete_integration(access_token)
        if not integration_result["success"]:
            if integration_result.get("error_code") == 404:
                raise HTTPException(status_code=404, detail="이미 연동된 사이트입니다.")
            raise HTTPException(status_code=500, detail=integration_result["error"])
        
        # 사이트 정보 업데이트
        try:
            site_info_result = await imweb_service.fetch_site_info_from_imweb(access_token)
            if site_info_result["success"]:
                site_data = site_info_result["data"]
                imweb_site_name = site_data.get('unitList')[0].get('name')
                if imweb_site_name:
                    await db_helper.update_site_name(user.id, site_code, imweb_site_name)
        except Exception as name_update_error:
            logger.warning(f"사이트 이름 자동 업데이트 실패: {name_update_error}")
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "토큰이 성공적으로 발급되었습니다."
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.post("/tokens/refresh-all")
async def refresh_all_tokens(user=Depends(get_current_user)):
    """사용자의 모든 사이트 토큰 일괄 갱신"""
    from main import imweb_service, db_helper
    
    try:
        user_sites = await db_helper.get_user_sites(user.id, user.id)
        if not user_sites:
            return JSONResponse(status_code=200, content={
                "status": "success",
                "message": "갱신할 사이트가 없습니다.",
                "results": []
            })
        
        refresh_results = []
        
        for site in user_sites:
            site_code = site.get('site_code')
            refresh_token = site.get('refresh_token')
            
            if not site_code or not refresh_token:
                refresh_results.append({
                    "site_code": site_code,
                    "success": False,
                    "error": "리프레시 토큰이 없습니다."
                })
                continue
            
            # 토큰 복호화
            decrypted_refresh_token = db_helper._decrypt_token(refresh_token)
            
            # 토큰 갱신 시도
            refresh_result = await imweb_service.refresh_imweb_token(decrypted_refresh_token)
            
            if refresh_result["success"]:
                # 새 토큰으로 데이터베이스 업데이트
                update_success = await db_helper.update_user_site_tokens(
                    user.id, 
                    site_code,
                    refresh_result["access_token"],
                    refresh_result["refresh_token"]
                )
                
                if update_success:
                    refresh_results.append({
                        "site_code": site_code,
                        "success": True,
                        "message": "토큰 갱신 성공"
                    })
                    
                    # 로그 기록
                    await db_helper.log_system_event(
                        user_id=user.id,
                        event_type='token_refreshed',
                        event_data={'site_code': site_code, 'action': 'bulk_refresh'}
                    )
                else:
                    refresh_results.append({
                        "site_code": site_code,
                        "success": False,
                        "error": "데이터베이스 업데이트 실패"
                    })
            else:
                refresh_results.append({
                    "site_code": site_code,
                    "success": False,
                    "error": refresh_result["error"]
                })
        
        success_count = sum(1 for result in refresh_results if result["success"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": f"{len(refresh_results)}개 사이트 중 {success_count}개 토큰 갱신 완료",
            "data": {"sites": refresh_results}
        })
        
    except Exception as e:
        logger.error(f"전체 토큰 갱신 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })


@router.get("/tokens/status-all")
async def get_all_tokens_status(user=Depends(get_current_user)):
    """모든 사이트 토큰 상태 조회"""
    from main import imweb_service, db_helper
    
    try:
        user_sites = await db_helper.get_user_sites(user.id, user.id)
        
        token_statuses = []
        for site in user_sites:
            # 아임웹에서 사이트 이름을 가져와서 업데이트
            await imweb_service.update_site_info_from_imweb(user.id)

            token_statuses.append({
                "site_code": site.get("site_code"),
                "site_name": site.get("site_name"),
                "has_access_token": bool(site.get("access_token")),
                "has_refresh_token": bool(site.get("refresh_token")),
                "last_updated": site.get("updated_at")
            })
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "tokens": token_statuses
        })
        
    except Exception as e:
        logger.error(f"토큰 상태 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })