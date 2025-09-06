"""
멤버십 관련 API 라우터
사용자 멤버십 조회, 업그레이드, 연장 등의 엔드포인트 제공
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.responses import success_response, error_response
from core.membership_config import MembershipConfig
from core.token_calculator import TokenUsageCalculator
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

@router.get("/wallet")
async def get_wallet(current_user = Depends(get_current_user)):
    """사용자 지갑 잔액 및 요약 조회"""
    try:
        from main import db_helper
        wallet = await db_helper.get_user_wallet(current_user.id)
        if not wallet:
            return success_response(data={"balance_usd": 0, "total_spent_usd": 0}, message="지갑 생성됨")
        return success_response(data=wallet, message="지갑 조회 성공")
    except Exception as e:
        logger.error(f"지갑 조회 실패: {e}")
        return error_response(message="지갑 조회 실패", error_code="WALLET_FETCH_ERROR")

@router.get("/wallet/transactions")
async def list_wallet_transactions(limit: int = 20, current_user = Depends(get_current_user)):
    try:
        from main import db_helper
        txs = await db_helper.get_token_transactions(current_user.id, limit)
        return success_response(data={"transactions": txs}, message="거래 내역 조회 성공")
    except Exception as e:
        logger.error(f"거래 내역 조회 실패: {e}")
        return error_response(message="거래 내역 조회 실패", error_code="WALLET_TX_FETCH_ERROR")

@router.post("/wallet/credit")
async def credit_wallet(amount_usd: float, current_user = Depends(get_current_user)):
    """테스트/운영용 크레딧 충전 엔드포인트 (권한 체크는 별도 구성 필요)"""
    try:
        from main import db_helper
        res = await db_helper.credit_wallet(current_user.id, amount_usd)
        if not res:
            return error_response(message="충전에 실패했습니다", error_code="WALLET_CREDIT_FAILED")
        wallet = await db_helper.get_user_wallet(current_user.id)
        return success_response(data={"wallet": wallet, "transaction": res}, message="충전 성공")
    except Exception as e:
        logger.error(f"충전 실패: {e}")
        return error_response(message="충전 실패", error_code="WALLET_CREDIT_ERROR")

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

        # 유효 레벨은 0~3 (MAX=3)
        if required_level < 0 or required_level > 3:
            return error_response(
                message="유효하지 않은 멤버십 레벨입니다 (0-3)",
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

@router.get("/config")
async def get_membership_config(
    current_user = Depends(get_current_user)
):
    """현재 사용자의 멤버십 설정 정보 조회"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        from main import db_helper
        
        # 멤버십 정보 조회
        membership = await db_helper.get_user_membership(current_user.id)
        if not membership:
            return error_response(message="멤버십 가입 후 이용 가능합니다.", error_code="NO_MEMBERSHIP")
        membership_level = membership.get('membership_level', 0)
        
        # 멤버십 설정 정보 가져오기
        membership_info = MembershipConfig.get_membership_info(membership_level)
        
        # 사용량 정보 추가
        user_sites = await db_helper.get_user_sites(current_user.id, current_user.id)
        current_sites = len(user_sites)
        
        # 업그레이드 정보
        upgrade_info = MembershipConfig.get_next_level_benefits(membership_level)
        
        return success_response(
            data={
                **membership_info,
                "usage": {
                    "current_sites": current_sites,
                    "expires_at": membership.get('expires_at') if membership else None,
                    "created_at": membership.get('created_at') if membership else None,
                    "updated_at": membership.get('updated_at') if membership else None
                },
                "upgrade_info": upgrade_info
            },
            message="멤버십 설정 정보 조회 성공"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"멤버십 설정 정보 조회 실패: {e}")
        return error_response(
            message="멤버십 설정 정보 조회 중 오류가 발생했습니다",
            error_code="MEMBERSHIP_CONFIG_ERROR"
        )

@router.get("/features/{feature_name}")
async def check_feature_access(
    feature_name: str,
    current_user = Depends(get_current_user)
):
    """특정 기능에 대한 접근 권한 확인"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        from main import db_helper
        
        membership = await db_helper.get_user_membership(current_user.id)
        if not membership:
            return error_response(message="멤버십 가입 후 이용 가능합니다.", error_code="NO_MEMBERSHIP")
        membership_level = membership.get('membership_level', 0)
        
        # 기능 접근 권한 확인
        has_access = MembershipConfig.can_use_feature(membership_level, feature_name)
        
        required_level = None
        if not has_access:
            # 필요한 최소 레벨 찾기
            for level in range(membership_level + 1, 4):
                if MembershipConfig.can_use_feature(level, feature_name):
                    required_level = level
                    break
        
        return success_response(
            data={
                "feature": feature_name,
                "has_access": has_access,
                "current_level": membership_level,
                "required_level": required_level
            },
            message="기능 접근 권한 확인 완료"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"기능 접근 권한 확인 실패: {e}")
        return error_response(
            message="기능 접근 권한 확인 중 오류가 발생했습니다",
            error_code="FEATURE_ACCESS_CHECK_ERROR"
        )

@router.get("/limits")
async def get_membership_limits(
    current_user = Depends(get_current_user)
):
    """멤버십별 제한사항 조회"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        from main import db_helper
        
        membership = await db_helper.get_user_membership(current_user.id)
        if not membership:
            return error_response(message="멤버십 가입 후 이용 가능합니다.", error_code="NO_MEMBERSHIP")
        membership_level = membership.get('membership_level', 0)
        
        features = MembershipConfig.get_features(membership_level)
        
        # 현재 사용량 조회
        user_sites = await db_helper.get_user_sites(current_user.id, current_user.id)
        current_sites = len(user_sites)
        
        return success_response(
            data={
                "membership_level": membership_level,
                "limits": {
                    "max_sites": features.max_sites,
                    "max_image_uploads": features.max_image_uploads,
                    "max_thread_history": features.max_thread_history,
                    "concurrent_requests": features.concurrent_requests,
                    "thinking_budget": features.thinking_budget
                },
                "usage": {
                    "current_sites": current_sites
                },
                "ai_settings": {
                    "model": features.ai_model,
                    "thinking_budget": features.thinking_budget
                }
            },
            message="멤버십 제한사항 조회 성공"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"멤버십 제한사항 조회 실패: {e}")
        return error_response(
            message="멤버십 제한사항 조회 중 오류가 발생했습니다",
            error_code="MEMBERSHIP_LIMITS_ERROR"
        )

@router.get("/pricing/models")
async def get_model_pricing():
    """지원되는 AI 모델별 가격 정보 조회"""
    try:
        supported_models = TokenUsageCalculator.get_supported_models()
        pricing_info = {}
        
        for model in supported_models:
            pricing_info[model] = TokenUsageCalculator.get_model_pricing_info(model)
        
        return success_response(
            data={
                "supported_models": supported_models,
                "pricing_info": pricing_info,
                "currency": "USD per million tokens",
                "exchange_rate": f"1 USD = {TokenUsageCalculator.USD_TO_KRW_RATE} KRW (approximate)"
            },
            message="모델별 가격 정보 조회 성공"
        )
        
    except Exception as e:
        logger.error(f"모델 가격 정보 조회 실패: {e}")
        return error_response(
            message="모델 가격 정보 조회 중 오류가 발생했습니다",
            error_code="MODEL_PRICING_ERROR"
        )

@router.post("/pricing/estimate")
async def estimate_cost(
    request: dict,
    current_user = Depends(get_current_user)
):
    """토큰 수에 따른 예상 비용 계산"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        # 요청 파라미터 검증
        input_tokens = request.get('input_tokens', 0)
        output_tokens = request.get('output_tokens', 0)
        model_name = request.get('model_name', 'gemini-2.5-pro')
        input_type = request.get('input_type', 'text_image_video')
        
        if input_tokens < 0 or output_tokens < 0:
            return error_response(
                message="토큰 수는 음수일 수 없습니다",
                error_code="INVALID_TOKEN_COUNT"
            )
        
        # 단일 모델 비용 계산
        if model_name and model_name != 'all':
            cost_info = TokenUsageCalculator.estimate_cost(
                input_tokens, output_tokens, model_name, input_type
            )
            
            return success_response(
                data=cost_info,
                message=f"{model_name} 모델 예상 비용 계산 완료"
            )
        
        # 모든 모델 비교
        comparison = TokenUsageCalculator.compare_model_costs(
            input_tokens, output_tokens, input_type
        )
        
        return success_response(
            data={
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "input_type": input_type,
                "model_comparison": comparison
            },
            message="모든 모델 비용 비교 완료"
        )
        
    except Exception as e:
        logger.error(f"비용 예상 계산 실패: {e}")
        return error_response(
            message="비용 예상 계산 중 오류가 발생했습니다",
            error_code="COST_ESTIMATION_ERROR"
        )

@router.get("/usage/models")
async def get_model_usage_stats(
    current_user = Depends(get_current_user),
    days: int = 30
):
    """사용자의 AI 모델별 사용량 통계 조회"""
    try:
        if not current_user:
            raise HTTPException(status_code=401, detail="인증이 필요합니다")
        
        from main import db_helper
        
        # 지정된 기간 내의 AI 메시지 조회
        from datetime import datetime, timedelta
        
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # AI 메시지만 조회 (assistant 타입이고 ai_model 정보가 있는 것)
        client = db_helper._get_client(use_admin=True)
        result = client.table('chat_messages').select(
            'ai_model, cost_usd, created_at'
        ).eq('user_id', current_user.id).eq('message_type', 'assistant').gte(
            'created_at', cutoff_date
        ).not_.is_('ai_model', 'null').execute()
        
        # 모델별 통계 계산
        model_stats_dict = {}
        total_messages = 0
        total_cost = 0.0
        
        if result.data:
            for row in result.data:
                model = row['ai_model']
                cost = float(row['cost_usd'] or 0)
                created_at = row['created_at']
                
                if model not in model_stats_dict:
                    model_stats_dict[model] = {
                        "model": model,
                        "message_count": 0,
                        "total_cost_usd": 0.0,
                        "costs": [],
                        "first_used": created_at,
                        "last_used": created_at
                    }
                
                model_stats_dict[model]["message_count"] += 1
                model_stats_dict[model]["total_cost_usd"] += cost
                model_stats_dict[model]["costs"].append(cost)
                
                # 날짜 업데이트
                if created_at < model_stats_dict[model]["first_used"]:
                    model_stats_dict[model]["first_used"] = created_at
                if created_at > model_stats_dict[model]["last_used"]:
                    model_stats_dict[model]["last_used"] = created_at
                
                total_messages += 1
                total_cost += cost
        
        # 평균 계산 및 정리
        model_stats = []
        for stats in model_stats_dict.values():
            avg_cost = sum(stats["costs"]) / len(stats["costs"]) if stats["costs"] else 0
            final_stats = {
                "model": stats["model"],
                "message_count": stats["message_count"],
                "total_cost_usd": round(stats["total_cost_usd"], 6),
                "avg_cost_usd": round(avg_cost, 6),
                "total_cost_krw": round(stats["total_cost_usd"] * TokenUsageCalculator.USD_TO_KRW_RATE, 2),
                "first_used": stats["first_used"],
                "last_used": stats["last_used"]
            }
            model_stats.append(final_stats)
        
        # 비용 순으로 정렬
        model_stats.sort(key=lambda x: x["total_cost_usd"], reverse=True)
        
        return success_response(
            data={
                "period_days": days,
                "total_messages": total_messages,
                "total_cost_usd": round(total_cost, 6),
                "total_cost_krw": round(total_cost * TokenUsageCalculator.USD_TO_KRW_RATE, 2),
                "model_stats": model_stats,
                "query_date": datetime.now().isoformat()
            },
            message=f"최근 {days}일간 모델별 사용량 통계 조회 성공"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"모델 사용량 통계 조회 실패: {e}")
        return error_response(
            message="모델 사용량 통계 조회 중 오류가 발생했습니다",
            error_code="MODEL_USAGE_STATS_ERROR"
        )