"""
멤버십 관리 서비스
사용자 멤버십 등급, 만료일 관리 및 권한 검증
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List, Tuple
from uuid import uuid4

from core.interfaces import IDatabaseHelper, IMembershipService
from core.base_service import BaseService
from core.membership_config import MembershipLevel
from services.paddle_billing_client import PaddleBillingClient, PaddleAPIError

logger = logging.getLogger(__name__)

class MembershipService(BaseService, IMembershipService):
    """멤버십 관리 서비스"""
    
    def __init__(self, db_helper: IDatabaseHelper, paddle_client: PaddleBillingClient | None = None):
        super().__init__(db_helper)
        self.paddle_client = paddle_client

    async def _record_membership_error(
        self,
        *,
        user_id: str,
        action: str,
        error: Exception,
        subscription_id: Optional[str] = None,
        trigger_source: Optional[str] = None,
    ) -> str:
        """Paddle 연동 관련 실패 정보를 로그 및 시스템 로그에 기록"""

        correlation_id = uuid4().hex
        error_type = "paddle_api" if isinstance(error, PaddleAPIError) else "unexpected"
        event_payload: Dict[str, Any] = {
            "correlation_id": correlation_id,
            "action": action,
            "error_type": error_type,
            "message": str(error),
        }

        if isinstance(error, PaddleAPIError):
            event_payload.update(
                {
                    "status_code": error.status_code,
                    "paddle_code": error.code,
                    "payload": error.payload,
                }
            )

        if subscription_id:
            event_payload["subscription_id"] = subscription_id
        if trigger_source:
            event_payload["trigger_source"] = trigger_source

        self.logger.error(
            "멤버십 작업 실패: action=%s user_id=%s correlation_id=%s error=%s",
            action,
            user_id,
            correlation_id,
            error,
        )

        try:
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type=f"{action}_failed",
                event_data=event_payload,
            )
        except Exception as log_error:  # pragma: no cover - 로깅 실패는 치명적이지 않음
            self.logger.warning(
                "시스템 로그 기록 실패: action=%s correlation_id=%s error=%s",
                action,
                correlation_id,
                log_error,
            )

        return correlation_id

    def _build_support_detail(self, correlation_id: str, error: Exception) -> str:
        """사용자 안내 메시지에 포함할 지원 코드와 세부 정보를 생성"""

        parts: List[str] = [f"지원 코드: {correlation_id}"]
        if isinstance(error, PaddleAPIError):
            if getattr(error, "status_code", None):
                parts.append(f"status={error.status_code}")
            if getattr(error, "code", None):
                parts.append(f"code={error.code}")
            message = str(error)
            if message:
                parts.append(message)
        else:
            message = str(error)
            if message:
                parts.append(message)

        return " | ".join(parts)
    
    async def _fetch_subscription_status(
        self,
        user_id: str,
        subscription_id: str,
        *,
        trigger_source: str,
    ) -> Tuple[Optional[str], Optional[str]]:
        """이전 Paddle 구독 상태를 조회해 중복 청구 여부를 점검"""

        if not self.paddle_client:
            return None, None

        try:
            payload = await self.paddle_client.get_subscription(subscription_id)
        except PaddleAPIError as api_error:
            correlation_id = await self._record_membership_error(
                user_id=user_id,
                action="subscription_status_check",
                error=api_error,
                subscription_id=subscription_id,
                trigger_source=trigger_source,
            )
            return None, correlation_id
        except Exception as exc:  # pragma: no cover - 방어적 경로
            correlation_id = await self._record_membership_error(
                user_id=user_id,
                action="subscription_status_check",
                error=exc,
                subscription_id=subscription_id,
                trigger_source=trigger_source,
            )
            return None, correlation_id

        status_raw = payload.get("status") if isinstance(payload, dict) else None
        if isinstance(status_raw, str):
            return status_raw.lower(), None
        if status_raw is None:
            return None, None
        return str(status_raw).lower(), None
    
    async def get_user_membership(self, user_id: str) -> Dict[str, Any]:
        """사용자 멤버십 정보 조회"""
        try:
            membership = await self.db_helper.get_user_membership(user_id)
            
            if not membership:
                return None
                
            # 응답 데이터 가공
            result = {
                **membership,
                'is_expired': self._is_membership_expired(membership),
                'days_remaining': self._get_days_remaining(membership),
                'next_billing_at': membership.get('next_billing_at'),
            }

            # 신규 필드 기본값 보정
            if 'cancel_at_period_end' not in result:
                result['cancel_at_period_end'] = False
            if 'cancel_requested_at' not in result:
                result['cancel_requested_at'] = None

            return result
            
        except Exception as e:
            self.logger.error(f"멤버십 조회 실패: {e}")
            return None

    async def sync_paddle_subscription(
        self,
        user_id: str,
        subscription_id: str,
        metadata: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Paddle 구독 ID를 사용자 멤버십과 동기화"""

        if not subscription_id or not subscription_id.strip():
            raise ValueError("유효한 Paddle 구독 ID가 필요합니다")

        subscription_id = subscription_id.strip()
        meta_payload = metadata or {}
        result: Dict[str, Any] = {
            "subscription_id": subscription_id,
            "updated": False,
            "created": False,
            "status": "noop",
        }

        try:
            membership = await self.db_helper.get_user_membership(user_id)
            if membership:
                result["membership"] = membership
                current_id = membership.get("paddle_subscription_id")
                if current_id == subscription_id:
                    result["status"] = "unchanged"
                else:
                    updated = await self.db_helper.update_membership_subscription_id(user_id, subscription_id)
                    result["updated"] = bool(updated)
                    result["status"] = "updated" if updated else "update_failed"
            else:
                created = await self.db_helper.create_user_membership(
                    user_id,
                    membership_level=0,
                    expires_at=None,
                    next_billing_at=None,
                    cancel_at_period_end=False,
                    cancel_requested_at=None,
                    paddle_subscription_id=subscription_id,
                )
                result["created"] = bool(created)
                result["updated"] = bool(created)
                result["status"] = "created" if created else "create_failed"
                if created:
                    result["membership"] = created

            if result.get("updated"):
                refreshed = await self.db_helper.get_user_membership(user_id)
                if refreshed:
                    result["membership"] = refreshed

            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type="membership_subscription_sync",
                event_data={
                    "subscription_id": subscription_id,
                    "metadata": meta_payload,
                    "status": result["status"],
                    "updated": result["updated"],
                    "created": result["created"],
                },
            )

            return result
        except Exception as e:
            self.logger.error(f"Paddle 구독 동기화 실패: {e}")
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type="membership_subscription_sync_error",
                event_data={
                    "subscription_id": subscription_id,
                    "metadata": meta_payload,
                    "error": str(e),
                },
            )
            return {
                "status": "error",
                "subscription_id": subscription_id,
                "error": str(e),
            }
    
    async def upgrade_membership(
        self,
        user_id: str,
        target_level: int,
        duration_days: int = 30,
        next_billing_at: datetime | None = None,
        paddle_subscription_id: str | None = None,
    ) -> Dict[str, Any]:
        """멤버십 업그레이드"""
        try:
            # 유효한 레벨인지 확인
            if target_level not in [level.value for level in MembershipLevel]:
                raise ValueError(f"유효하지 않은 멤버십 레벨: {target_level}")
            
            # 무료 등급 요청은 만료 시점 해지 예약으로 처리
            if target_level == MembershipLevel.FREE:
                return await self.cancel_membership(user_id)
            
            now = datetime.now(timezone.utc)
            base_time = now

            normalized_subscription_id: Optional[str]
            if isinstance(paddle_subscription_id, str):
                normalized_subscription_id = paddle_subscription_id.strip() or None
            else:
                normalized_subscription_id = paddle_subscription_id

            resubscribe_detected = False
            previous_subscription_status: Optional[str] = None
            status_check_correlation_id: Optional[str] = None
            cancel_flags_were_set = False

            # 기존 멤버십 조회
            current_membership = await self.db_helper.get_user_membership(user_id)

            current_subscription_id = None
            if current_membership:
                current_expires = current_membership.get('expires_at')
                if current_expires:
                    try:
                        parsed_expires = datetime.fromisoformat(current_expires.replace('Z', '+00:00'))
                        if parsed_expires.tzinfo is None:
                            parsed_expires = parsed_expires.replace(tzinfo=timezone.utc)
                        if parsed_expires > base_time:
                            base_time = parsed_expires
                    except Exception as parse_err:
                        self.logger.warning(f"기존 만료일 파싱 실패: {parse_err}")

                raw_subscription = current_membership.get('paddle_subscription_id')
                if isinstance(raw_subscription, str):
                    raw_subscription = raw_subscription.strip() or None
                current_subscription_id = raw_subscription

                cancel_flags_were_set = bool(
                    current_membership.get('cancel_at_period_end')
                    or current_membership.get('cancel_requested_at')
                )

                if (
                    normalized_subscription_id
                    and current_subscription_id
                    and normalized_subscription_id != current_subscription_id
                ):
                    resubscribe_detected = True
                    self.logger.info(
                        "Paddle 구독 ID 갱신 감지: user_id=%s previous=%s → new=%s",
                        user_id,
                        current_subscription_id,
                        normalized_subscription_id,
                    )
                    previous_subscription_status, status_check_correlation_id = await self._fetch_subscription_status(
                        user_id,
                        current_subscription_id,
                        trigger_source="upgrade_membership",
                    )
                    if previous_subscription_status and previous_subscription_status not in {
                        "canceled",
                        "cancelled",
                        "ended",
                        "inactive",
                    }:
                        self.logger.warning(
                            "이전 Paddle 구독이 활성 상태로 남아 있을 수 있습니다: user_id=%s subscription_id=%s status=%s",
                            user_id,
                            current_subscription_id,
                            previous_subscription_status,
                        )
                    event_payload = {
                        "previous_subscription_id": current_subscription_id,
                        "new_subscription_id": normalized_subscription_id,
                        "previous_subscription_status": previous_subscription_status,
                        "cancel_flags_were_set": cancel_flags_were_set,
                    }
                    if status_check_correlation_id:
                        event_payload["status_check_correlation_id"] = status_check_correlation_id
                    try:
                        await self.db_helper.log_system_event(
                            user_id=user_id,
                            event_type="membership_subscription_resubscribe_detected",
                            event_data=event_payload,
                        )
                    except Exception as log_error:  # pragma: no cover - 로깅 실패 무시
                        self.logger.warning(f"재구독 로그 기록 실패: {log_error}")

            expires_at = base_time + timedelta(days=duration_days)
            target_subscription_id = normalized_subscription_id or current_subscription_id

            if current_membership:
                # 업데이트
                success = await self.db_helper.update_user_membership(
                    user_id,
                    target_level,
                    expires_at,
                    next_billing_at,
                    cancel_at_period_end=False,
                    cancel_requested_at=None,
                    paddle_subscription_id=target_subscription_id,
                )
            else:
                # 새로 생성
                membership = await self.db_helper.create_user_membership(
                    user_id,
                    target_level,
                    expires_at,
                    next_billing_at,
                    cancel_at_period_end=False,
                    cancel_requested_at=None,
                    paddle_subscription_id=target_subscription_id,
                )
                success = bool(membership)
            
            if success:
                # 업그레이드 로그 기록
                event_data = {
                    'from_level': current_membership.get('membership_level', 0) if current_membership else 0,
                    'to_level': target_level,
                    'duration_days': duration_days,
                    'expires_at': expires_at.isoformat(),
                    'next_billing_at': next_billing_at.isoformat() if next_billing_at else None,
                    'paddle_subscription_id': target_subscription_id,
                }
                if resubscribe_detected:
                    event_data.update({
                        'resubscribe_detected': True,
                        'previous_subscription_id': current_subscription_id,
                        'previous_subscription_status': previous_subscription_status,
                        'cancel_flags_reset': cancel_flags_were_set,
                    })
                    if status_check_correlation_id:
                        event_data['status_check_correlation_id'] = status_check_correlation_id

                await self.db_helper.log_system_event(
                    user_id=user_id,
                    event_type='membership_upgrade',
                    event_data=event_data
                )
                
                # 업데이트된 멤버십 정보 반환
                membership_data = await self.get_user_membership(user_id)
                if isinstance(membership_data, dict) and resubscribe_detected:
                    membership_data['resubscribe_detected'] = True
                    membership_data['previous_subscription_id'] = current_subscription_id
                    membership_data['previous_subscription_status'] = previous_subscription_status
                    membership_data['cancel_flags_cleared'] = cancel_flags_were_set
                    if status_check_correlation_id:
                        membership_data['status_check_correlation_id'] = status_check_correlation_id
                return membership_data
            else:
                raise Exception("멤버십 업데이트 실패")
                
        except Exception as e:
            self.logger.error(f"멤버십 업그레이드 실패: {e}")
            return {}
    
    async def extend_membership(self, user_id: str, days: int) -> Dict[str, Any]:
        """멤버십 기간 연장"""
        try:
            current_membership = await self.db_helper.get_user_membership(user_id)
            
            if not current_membership:
                raise ValueError("멤버십이 존재하지 않습니다")
            
            current_level = current_membership.get('membership_level', 0)
            
            # 무료 등급은 연장할 수 없음
            if current_level == MembershipLevel.FREE:
                raise ValueError("무료 등급은 연장할 수 없습니다")
            
            # 현재 만료일 기준으로 연장
            current_expires = current_membership.get('expires_at')
            if current_expires:
                current_expires_dt = datetime.fromisoformat(current_expires.replace('Z', '+00:00'))
                # 이미 만료되었다면 현재 시간부터 계산
                base_time = max(current_expires_dt, datetime.now().replace(tzinfo=current_expires_dt.tzinfo))
            else:
                base_time = datetime.now()
            
            new_expires_at = base_time + timedelta(days=days)
            next_billing_at = current_membership.get('next_billing_at')
            if isinstance(next_billing_at, str):
                try:
                    next_billing_at = datetime.fromisoformat(next_billing_at.replace('Z', '+00:00'))
                except Exception:
                    next_billing_at = None
            
            success = await self.db_helper.update_user_membership(
                user_id,
                current_level,
                new_expires_at,
                next_billing_at,
                cancel_at_period_end=False,
                cancel_requested_at=None,
            )
            
            if success:
                await self.db_helper.log_system_event(
                    user_id=user_id,
                    event_type='membership_extend',
                    event_data={
                        'level': current_level,
                        'extended_days': days,
                        'new_expires_at': new_expires_at.isoformat()
                    }
                )
                return await self.get_user_membership(user_id)
            else:
                raise Exception("멤버십 연장 실패")
                
        except Exception as e:
            self.logger.error(f"멤버십 연장 실패: {e}")
            return {}
    
    async def check_permission(self, user_id: str, required_level: int) -> bool:
        """사용자 권한 확인"""
        return await self.db_helper.check_membership_level(user_id, required_level)

    async def force_downgrade_to_free(self, user_id: str) -> Dict[str, Any]:
        """환불 등으로 즉시 무료 등급으로 전환"""
        return await self._downgrade_to_free(user_id)

    async def get_membership_status(self, user_id: str) -> Dict[str, Any]:
        """멤버십 상태 상세 조회"""
        try:
            membership = await self.get_user_membership(user_id)
            
            if not membership:
                return {'status': 'no_membership'}
            
            level = membership.get('membership_level', 0)
            expires_at = membership.get('expires_at')
            next_billing_at = membership.get('next_billing_at')
            
            status = {
                'level': level,
                'expires_at': expires_at,
                'next_billing_at': next_billing_at,
                'is_expired': self._is_membership_expired(membership),
                'days_remaining': self._get_days_remaining(membership),
                'cancel_at_period_end': membership.get('cancel_at_period_end', False),
                'cancel_requested_at': membership.get('cancel_requested_at'),
            }
            
            if expires_at:
                expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                status['expires_in_days'] = (expires_dt - datetime.now().replace(tzinfo=expires_dt.tzinfo)).days
            
            return status
            
        except Exception as e:
            self.logger.error(f"멤버십 상태 조회 실패: {e}")
            return {'status': 'error', 'error': str(e)}
    
    async def batch_cleanup_expired_memberships(self) -> Dict[str, Any]:
        """만료된 멤버십 일괄 정리 (배치 작업용)"""
        try:
            downgraded_count = await self.db_helper.batch_downgrade_expired_memberships()
            
            result = {
                'success': True,
                'downgraded_count': downgraded_count,
                'processed_at': datetime.now().isoformat()
            }
            return result
            
        except Exception as e:
            self.logger.error(f"배치 정리 실패: {e}")
            return {'success': False, 'error': str(e)}
    
    def _is_membership_expired(self, membership: Dict[str, Any]) -> bool:
        """멤버십 만료 여부 확인"""
        expires_at = membership.get('expires_at')
        if not expires_at:
            return False  # 만료일이 없는 무료 등급
        
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            return expires_dt < datetime.now().replace(tzinfo=expires_dt.tzinfo)
        except:
            return False
    
    def _get_days_remaining(self, membership: Dict[str, Any]) -> Optional[int]:
        """남은 일수 계산"""
        expires_at = membership.get('expires_at')
        if not expires_at:
            return None  # 무제한 (무료 등급)
        
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            remaining = expires_dt - datetime.now().replace(tzinfo=expires_dt.tzinfo)
            return max(0, remaining.days)
        except:
            return None
    
    
    async def _downgrade_to_free(self, user_id: str) -> Dict[str, Any]:
        """무료 등급으로 다운그레이드"""
        try:
            success = await self.db_helper.update_user_membership(
                user_id,
                MembershipLevel.FREE,
                None,
                cancel_at_period_end=False,
                cancel_requested_at=None,
                paddle_subscription_id=None,
            )

            if success:
                await self.db_helper.log_system_event(
                    user_id=user_id,
                    event_type='membership_downgrade',
                    event_data={'reason': 'manual', 'new_level': int(MembershipLevel.FREE)}
                )

                return await self.get_user_membership(user_id)
            else:
                raise Exception("다운그레이드 실패")
                
        except Exception as e:
            self.logger.error(f"무료 등급 다운그레이드 실패: {e}")
            return {}

    async def cancel_membership(self, user_id: str, trigger_source: str = "user") -> Dict[str, Any]:
        """멤버십을 만료 시점에 해지하도록 예약"""
        subscription_id: Optional[str] = None

        try:
            membership = await self.db_helper.get_user_membership(user_id)
            if not membership or int(membership.get('membership_level', 0)) <= 0:
                raise ValueError("해지할 유료 멤버십이 존재하지 않습니다")

            subscription_id = membership.get('paddle_subscription_id')

            if trigger_source != "webhook" and not self.paddle_client:
                self.logger.error("Paddle API 클라이언트가 구성되지 않아 해지를 진행할 수 없습니다 (user_id=%s)", user_id)
                raise RuntimeError("결제 연동 설정이 누락되어 해지를 완료할 수 없습니다. 관리자에게 문의해주세요.")

            if trigger_source != "webhook" and self.paddle_client:
                if subscription_id:
                    try:
                        await self.paddle_client.cancel_subscription(subscription_id, effective_from="next_billing_period")
                    except PaddleAPIError as e:
                        correlation_id = await self._record_membership_error(
                            user_id=user_id,
                            action="membership_cancel",
                            error=e,
                            subscription_id=subscription_id,
                            trigger_source=trigger_source,
                        )
                        raise RuntimeError(self._build_support_detail(correlation_id, e)) from e
                    except Exception as e:  # pragma: no cover - 예외 처리 보강
                        correlation_id = await self._record_membership_error(
                            user_id=user_id,
                            action="membership_cancel",
                            error=e,
                            subscription_id=subscription_id,
                            trigger_source=trigger_source,
                        )
                        raise RuntimeError(self._build_support_detail(correlation_id, e)) from e
                else:
                    self.logger.warning("Paddle 구독 ID가 없어 API 해지를 건너뜁니다 (user_id=%s)", user_id)

            scheduled = await self.db_helper.schedule_membership_cancellation(user_id)
            if not scheduled:
                raise ValueError("해지할 유료 멤버십이 존재하지 않습니다")

            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='membership_cancel_scheduled',
                event_data={'cancel_at_period_end': True}
            )

            membership = await self.get_user_membership(user_id)
            if not membership:
                raise RuntimeError("멤버십 정보를 조회할 수 없습니다")
            return membership
        except ValueError:
            raise
        except Exception as e:
            correlation_id = await self._record_membership_error(
                user_id=user_id,
                action="membership_cancel",
                error=e,
                subscription_id=subscription_id,
                trigger_source=trigger_source,
            )
            raise RuntimeError(self._build_support_detail(correlation_id, e)) from e

    async def resume_membership(self, user_id: str) -> Dict[str, Any]:
        """예약된 멤버십 해지를 취소하고 유료 멤버십을 유지"""
        subscription_id: Optional[str] = None

        try:
            membership = await self.db_helper.get_user_membership(user_id)
            if not membership or int(membership.get('membership_level', 0)) <= 0:
                raise ValueError("해지 취소할 유료 멤버십이 존재하지 않습니다")

            expires_at = self.db_helper._parse_iso_datetime(membership.get('expires_at'))
            next_billing_at = self.db_helper._parse_iso_datetime(membership.get('next_billing_at'))

            subscription_id = membership.get('paddle_subscription_id')

            if membership.get('cancel_at_period_end') and not self.paddle_client:
                self.logger.error("Paddle API 클라이언트가 구성되지 않아 해지 예약을 취소할 수 없습니다 (user_id=%s)", user_id)
                raise RuntimeError("결제 연동 설정이 누락되어 해지 예약을 취소하지 못했습니다. 관리자에게 문의해주세요.")

            if self.paddle_client and subscription_id and membership.get('cancel_at_period_end'):
                try:
                    await self.paddle_client.resume_subscription(subscription_id)
                except PaddleAPIError as e:
                    correlation_id = await self._record_membership_error(
                        user_id=user_id,
                        action="membership_resume",
                        error=e,
                        subscription_id=subscription_id,
                    )
                    raise RuntimeError(self._build_support_detail(correlation_id, e)) from e
                except Exception as e:  # pragma: no cover
                    correlation_id = await self._record_membership_error(
                        user_id=user_id,
                        action="membership_resume",
                        error=e,
                        subscription_id=subscription_id,
                    )
                    raise RuntimeError(self._build_support_detail(correlation_id, e)) from e

            success = await self.db_helper.update_user_membership(
                user_id,
                membership_level=membership.get('membership_level', 0),
                expires_at=expires_at,
                next_billing_at=next_billing_at,
                cancel_at_period_end=False,
                cancel_requested_at=None,
            )

            if not success:
                raise RuntimeError("멤버십 해지 취소에 실패했습니다")

            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='membership_cancel_resumed',
                event_data={'cancel_at_period_end': False}
            )

            return await self.get_user_membership(user_id)
        except ValueError:
            raise
        except Exception as e:
            correlation_id = await self._record_membership_error(
                user_id=user_id,
                action="membership_resume",
                error=e,
                subscription_id=subscription_id,
            )
            raise RuntimeError(self._build_support_detail(correlation_id, e)) from e
