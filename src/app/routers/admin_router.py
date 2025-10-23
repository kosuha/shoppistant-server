"""
관리자 전용 API 라우터
"""
from typing import Optional, Sequence, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Query, Path
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.responses import success_response
from schemas.admin import (
    MembershipGrantRequest,
    MembershipExtendRequest,
    CreditAdjustRequest,
    RefundRequest,
    EventReplayRequest,
)
from routers.paddle_router import process_paddle_payload

# 의존성 주입 대상 서비스들
auth_service = None  # type: ignore
membership_service = None  # type: ignore
db_helper = None  # type: ignore

# HTTP Bearer 인증 스키마
security = HTTPBearer(auto_error=False)

# 허용되는 관리자 역할
ADMIN_ROLES: Sequence[str] = ("admin", "super_admin", "owner")


def set_dependencies(auth_svc, membership_svc=None, db_helper_svc=None) -> None:
    """main.py에서 호출하여 서비스 인스턴스를 주입한다."""
    global auth_service, membership_service, db_helper
    auth_service = auth_svc
    membership_service = membership_svc
    db_helper = db_helper_svc


async def authorize_admin(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Supabase JWT의 app_metadata를 확인해 관리자 권한을 검증한다."""
    if auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="관리자 인증 서비스가 초기화되지 않았습니다.",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 토큰이 필요합니다.",
        )

    user = await auth_service.verify_auth(credentials)
    metadata = getattr(user, "app_metadata", {}) or {}

    roles = set()
    role_value: Optional[str] = metadata.get("role") if isinstance(metadata, dict) else None
    if isinstance(role_value, str):
        roles.add(role_value.lower())

    roles_field = metadata.get("roles") if isinstance(metadata, dict) else None
    if isinstance(roles_field, list):
        roles.update(str(value).lower() for value in roles_field if isinstance(value, str))
    elif isinstance(roles_field, str):
        roles.update(part.strip().lower() for part in roles_field.split(",") if part.strip())

    if not any(role in ADMIN_ROLES for role in roles):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="관리자 권한이 필요합니다.",
        )

    return user


async def require_services():
    if auth_service is None or membership_service is None or db_helper is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="관리자 서비스 의존성이 초기화되지 않았습니다.",
        )


async def get_current_admin(user=Depends(authorize_admin)):
    """엔드포인트에서 관리자 정보를 활용할 수 있도록 반환."""
    await require_services()
    return user


router = APIRouter(
    prefix="/api/v1/admin",
    tags=["admin"],
)


def _ensure_positive_page(page: int) -> int:
    return page if page > 0 else 1


def _ensure_page_size(limit: int) -> int:
    if limit <= 0:
        return 20
    return min(limit, 100)


async def _log_admin_action(
    admin_user,
    action: str,
    target_user: Optional[str],
    metadata: Optional[Dict[str, Any]] = None,
):
    if db_helper is None:
        return
    actor_id = getattr(admin_user, "id", None)
    await db_helper.log_admin_action(actor_id, action, target_user, metadata)


@router.get("/health")
async def admin_health_check(admin=Depends(get_current_admin)):
    """관리자 라우터용 헬스 체크 엔드포인트."""
    return success_response(data={"status": "ok"})


@router.get("/users")
async def list_users(
    q: Optional[str] = Query(None, description="이메일/ID 검색어"),
    status: str = Query("all", description="멤버십 상태 필터"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin=Depends(get_current_admin),
):
    await require_services()
    result = await db_helper.list_admin_users(
        query=q,
        status=status.lower(),
        page=_ensure_positive_page(page),
        page_size=_ensure_page_size(limit),
    )
    return success_response(data=result)


@router.get("/events")
async def list_events(
    type: str = Query("all", description="이벤트 유형 필터"),
    status: str = Query("all", description="처리 상태 필터"),
    start: Optional[str] = Query(None, description="조회 시작일 (YYYY-MM-DD)"),
    end: Optional[str] = Query(None, description="조회 종료일 (YYYY-MM-DD)"),
    q: Optional[str] = Query(None, description="검색어"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin=Depends(get_current_admin),
):
    await require_services()
    data = await db_helper.list_admin_events(
        event_type=type.lower() if type else "all",
        status=status.lower() if status else "all",
        start=start,
        end=end,
        query=q,
        page=page,
        page_size=limit,
    )
    return success_response(data=data)


@router.get("/events/{event_id}")
async def get_event_detail(
    event_id: str = Path(..., description="조회할 이벤트 ID"),
    admin=Depends(get_current_admin),
):
    await require_services()
    detail = await db_helper.get_admin_event_detail(event_id)
    if not detail:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="이벤트를 찾을 수 없습니다.")
    return success_response(data=detail)


@router.post("/events/{event_id}/replay")
async def replay_event(
    event_id: str,
    request: EventReplayRequest,
    admin=Depends(get_current_admin),
):
    await require_services()

    formatted = await db_helper.fetch_admin_event_record(event_id)
    if not formatted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="이벤트를 찾을 수 없습니다.")

    raw_payload = formatted.get('raw_payload')
    if not isinstance(raw_payload, dict):
        raw_payload = formatted.get('payload') if isinstance(formatted.get('payload'), dict) else None

    if not isinstance(raw_payload, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="원본 페이로드가 저장되지 않아 재처리할 수 없습니다.",
        )

    result = await process_paddle_payload(
        raw_payload,
        allow_duplicate=True,
        replay_reason=request.reason,
    )

    summary = formatted.get('summary') or {}
    target_user = summary.get('user_id')
    metadata = {
        "event_id": event_id,
        "replay_reason": request.reason,
        "status": result.get("status"),
        "log_recorded": result.get("log_recorded"),
    }
    processed = result.get("processed")
    if processed is not None:
        metadata["processed"] = processed

    await _log_admin_action(admin, "event_replay", target_user, metadata)
    return success_response(data=result, message="이벤트를 재처리했습니다.")


@router.get("/users/{user_id}")
async def get_user_detail(
    user_id: str = Path(..., description="조회할 사용자 ID"),
    admin=Depends(get_current_admin),
):
    await require_services()

    profile = await db_helper.get_user_profile(user_id)
    membership = await membership_service.get_user_membership(user_id)
    wallet = await db_helper.get_user_wallet(user_id)
    transactions = await db_helper.get_token_transactions(user_id, limit=10)

    return success_response(
        data={
            "profile": profile,
            "membership": membership,
            "wallet": wallet,
            "transactions": transactions,
        }
    )


@router.post("/users/{user_id}/membership/grant")
async def grant_membership(
    user_id: str,
    request: MembershipGrantRequest,
    admin=Depends(get_current_admin),
):
    await require_services()
    try:
        membership = await membership_service.upgrade_membership(
            user_id=user_id,
            target_level=request.target_level,
            duration_days=request.duration_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    if not membership:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="멤버십 부여에 실패했습니다.")

    await _log_admin_action(
        admin,
        "membership_grant",
        user_id,
        {"target_level": request.target_level, "duration_days": request.duration_days},
    )
    return success_response(data={"membership": membership}, message="멤버십을 부여했습니다.")


@router.post("/users/{user_id}/membership/extend")
async def extend_membership(
    user_id: str,
    request: MembershipExtendRequest,
    admin=Depends(get_current_admin),
):
    await require_services()
    try:
        membership = await membership_service.extend_membership(user_id, request.duration_days)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    if not membership:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="멤버십 연장에 실패했습니다.")

    await _log_admin_action(
        admin,
        "membership_extend",
        user_id,
        {"duration_days": request.duration_days},
    )
    return success_response(data={"membership": membership}, message="멤버십을 연장했습니다.")


@router.post("/users/{user_id}/membership/pause")
async def pause_membership(
    user_id: str,
    admin=Depends(get_current_admin),
):
    await require_services()
    try:
        membership = await membership_service.cancel_membership(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    await _log_admin_action(admin, "membership_cancel_scheduled", user_id, None)
    return success_response(data={"membership": membership}, message="만료 시점에 해지되도록 예약했습니다.")


@router.post("/users/{user_id}/membership/resume")
async def resume_membership(
    user_id: str,
    admin=Depends(get_current_admin),
):
    await require_services()
    try:
        membership = await membership_service.resume_membership(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    if not membership:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="멤버십 해지 예약 취소에 실패했습니다.")

    await _log_admin_action(admin, "membership_resume", user_id, None)
    return success_response(data={"membership": membership}, message="해지 예약을 취소했습니다.")


@router.post("/users/{user_id}/membership/cancel")
async def cancel_membership_immediately(
    user_id: str,
    admin=Depends(get_current_admin),
):
    await require_services()
    try:
        membership = await membership_service.force_downgrade_to_free(user_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))

    await _log_admin_action(admin, "membership_cancel_immediate", user_id, None)
    return success_response(data={"membership": membership}, message="멤버십을 즉시 해지했습니다.")


@router.post("/users/{user_id}/credits/grant")
async def grant_credits(
    user_id: str,
    request: CreditAdjustRequest,
    admin=Depends(get_current_admin),
):
    await require_services()
    metadata = {
        "reason": request.reason,
        "source": "admin_manual",
        "actor_id": getattr(admin, "id", None),
        "actor_email": getattr(admin, "email", None),
        "direction": "grant",
    }
    result = await db_helper.credit_wallet(user_id, request.amount, metadata=metadata)
    if result is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="크레딧 부여에 실패했습니다.")

    wallet = await db_helper.get_user_wallet(user_id)
    await _log_admin_action(admin, "credit_grant", user_id, {"amount": request.amount, "reason": request.reason})
    return success_response(data={"wallet": wallet}, message="크레딧을 부여했습니다.")


@router.post("/users/{user_id}/credits/deduct")
async def deduct_credits(
    user_id: str,
    request: CreditAdjustRequest,
    admin=Depends(get_current_admin),
):
    await require_services()
    metadata = {
        "reason": request.reason,
        "source": "admin_manual",
        "actor_id": getattr(admin, "id", None),
        "actor_email": getattr(admin, "email", None),
        "direction": "deduct",
    }
    result = await db_helper.debit_wallet(user_id, request.amount, metadata=metadata)
    if result is None:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="크레딧 차감에 실패했습니다.")

    wallet = await db_helper.get_user_wallet(user_id)
    await _log_admin_action(admin, "credit_deduct", user_id, {"amount": request.amount, "reason": request.reason})
    return success_response(data={"wallet": wallet}, message="크레딧을 차감했습니다.")


@router.post("/users/{user_id}/refunds")
async def request_refund(
    user_id: str,
    request: RefundRequest,
    admin=Depends(get_current_admin),
):
    await require_services()
    metadata = {"transaction_id": request.transaction_id, "reason": request.reason}

    try:
        recorded = await db_helper.record_admin_refund_request(
            actor_id=getattr(admin, "id", None),
            actor_email=getattr(admin, "email", None),
            user_id=user_id,
            transaction_id=request.transaction_id,
            reason=request.reason,
        )
    except ValueError as exc:
        await _log_admin_action(admin, "refund_failed", user_id, {**metadata, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        await _log_admin_action(admin, "refund_failed", user_id, {**metadata, "error": str(exc)})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="환불 요청 기록에 실패했습니다.")

    if not recorded:
        await _log_admin_action(admin, "refund_failed", user_id, {**metadata, "error": "log_failed"})
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="환불 요청을 기록하지 못했습니다.")

    await _log_admin_action(admin, "refund_requested", user_id, metadata)
    return success_response(
        data={"status": "queued", "transaction_id": request.transaction_id},
        message="환불 요청을 접수했습니다.",
    )


__all__ = ["router", "set_dependencies", "authorize_admin"]
