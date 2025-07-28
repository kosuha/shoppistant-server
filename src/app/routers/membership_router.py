"""
멤버십 관련 API 라우터
사용자 멤버십 조회, 업그레이드, 연장 등의 엔드포인트 제공
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.responses import success_response, error_response
from schemas import (
    MembershipUpgradeRequest, 
    MembershipExtendRequest,
    MembershipResponse,
    MembershipStatusResponse,
    BatchCleanupResult
)

logger = logging.getLogger(__name__)

# 라우터 생성
router = APIRouter(prefix="/api/v1/membership", tags=["membership"])
security = HTTPBearer()

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    from main import auth_service
    return await auth_service.verify_auth(credentials)

# 멤버십 서비스 전역 변수 (main.py에서 설정됨)
membership_service = None

def set_dependencies(user_dependency, membership_svc):
    """의존성 설정 (main.py에서 호출)"""
    global membership_service
    membership_service = membership_svc

@router.get("", response_model=MembershipResponse)
async def get_membership(
    current_user = Depends(get_current_user)
):
    """현재 사용자의 멤버십 정보 조회"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.id
        membership_data = await membership_service.get_user_membership(user_id)
        
        if membership_data is None:
            return error_response(
                message="멤버십 시스템에 접근할 수 없습니다. 관리자에게 문의하세요.",
                error_code="MEMBERSHIP_SYSTEM_ERROR"
            )
        
        return success_response(
            data=membership_data,
            message="멤버십 정보 조회 성공"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"멤버십 조회 실패: {e}")
        return error_response(
            message="멤버십 조회 중 오류가 발생했습니다",
            error_code="MEMBERSHIP_FETCH_ERROR"
        )

@router.get("/status", response_model=MembershipStatusResponse)
async def get_membership_status(
    current_user = Depends(get_current_user)
):
    """현재 사용자의 멤버십 상태 상세 조회"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.id
        status_data = await membership_service.get_membership_status(user_id)
        
        if status_data.get('status') == 'error':
            return error_response(
                message="멤버십 상태 조회 실패",
                error_code="MEMBERSHIP_STATUS_ERROR",
                data=status_data
            )
        
        return success_response(
            data=status_data,
            message="멤버십 상태 조회 성공"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"멤버십 상태 조회 실패: {e}")
        return error_response(
            message="멤버십 상태 조회 중 오류가 발생했습니다",
            error_code="MEMBERSHIP_STATUS_ERROR"
        )

@router.post("/upgrade", response_model=MembershipResponse)
async def upgrade_membership(
    request: MembershipUpgradeRequest,
    current_user = Depends(get_current_user)
):
    """멤버십 업그레이드"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.id
        
        # 업그레이드 수행
        result = await membership_service.upgrade_membership(
            user_id=user_id,
            target_level=request.target_level,
            duration_days=request.duration_days
        )
        
        if not result:
            return error_response(
                message="멤버십 업그레이드에 실패했습니다",
                error_code="MEMBERSHIP_UPGRADE_FAILED"
            )
        
        return success_response(
            data=result,
            message=f"멤버십이 레벨 {request.target_level}로 업그레이드되었습니다"
        )
        
    except ValueError as e:
        return error_response(
            message=str(e),
            error_code="INVALID_MEMBERSHIP_LEVEL"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"멤버십 업그레이드 실패: {e}")
        return error_response(
            message="멤버십 업그레이드 중 오류가 발생했습니다",
            error_code="MEMBERSHIP_UPGRADE_ERROR"
        )

@router.post("/extend", response_model=MembershipResponse)
async def extend_membership(
    request: MembershipExtendRequest,
    current_user = Depends(get_current_user)
):
    """멤버십 기간 연장"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        user_id = current_user.id
        
        # 멤버십 연장 수행
        result = await membership_service.extend_membership(
            user_id=user_id,
            days=request.extend_days
        )
        
        if not result:
            return error_response(
                message="멤버십 연장에 실패했습니다",
                error_code="MEMBERSHIP_EXTEND_FAILED"
            )
        
        return success_response(
            data=result,
            message=f"멤버십이 {request.extend_days}일 연장되었습니다"
        )
        
    except ValueError as e:
        return error_response(
            message=str(e),
            error_code="INVALID_EXTEND_REQUEST"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"멤버십 연장 실패: {e}")
        return error_response(
            message="멤버십 연장 중 오류가 발생했습니다",
            error_code="MEMBERSHIP_EXTEND_ERROR"
        )

@router.get("/check/{required_level}")
async def check_membership_permission(
    required_level: int,
    current_user = Depends(get_current_user)
):
    """특정 멤버십 레벨 권한 확인"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        if required_level < 0 or required_level > 2:
            return error_response(
                message="유효하지 않은 멤버십 레벨입니다 (0-2)",
                error_code="INVALID_MEMBERSHIP_LEVEL"
            )
        
        user_id = current_user.id
        has_permission = await membership_service.check_permission(user_id, required_level)
        
        return success_response(
            data={
                "user_id": user_id,
                "required_level": required_level,
                "has_permission": has_permission
            },
            message="권한 확인 완료"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"권한 확인 실패: {e}")
        return error_response(
            message="권한 확인 중 오류가 발생했습니다",
            error_code="PERMISSION_CHECK_ERROR"
        )

# 관리자용 엔드포인트
@router.post("/admin/cleanup", response_model=BatchCleanupResult)
async def batch_cleanup_expired_memberships(
    current_user = Depends(get_current_user)
):
    """만료된 멤버십 일괄 정리 (관리자 전용)"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        # TODO: 관리자 권한 확인 로직 추가
        # 현재는 모든 인증된 사용자가 접근 가능하도록 설정
        
        result = await membership_service.batch_cleanup_expired_memberships()
        
        if not result.get('success'):
            return error_response(
                message="배치 정리 실패",
                error_code="BATCH_CLEANUP_FAILED",
                data=result
            )
        
        return success_response(
            data=result,
            message=f"만료된 멤버십 {result.get('downgraded_count', 0)}건이 정리되었습니다"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"배치 정리 실패: {e}")
        return error_response(
            message="배치 정리 중 오류가 발생했습니다",
            error_code="BATCH_CLEANUP_ERROR"
        )