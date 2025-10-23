"""
멤버십 관리 서비스
사용자 멤버십 등급, 만료일 관리 및 권한 검증
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

from core.interfaces import IDatabaseHelper, IMembershipService
from core.base_service import BaseService
from core.membership_config import MembershipLevel

logger = logging.getLogger(__name__)

class MembershipService(BaseService, IMembershipService):
    """멤버십 관리 서비스"""
    
    def __init__(self, db_helper: IDatabaseHelper):
        super().__init__(db_helper)
    
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
    
    async def upgrade_membership(
        self,
        user_id: str,
        target_level: int,
        duration_days: int = 30,
        next_billing_at: datetime | None = None,
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

            # 기존 멤버십 조회
            current_membership = await self.db_helper.get_user_membership(user_id)

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

            expires_at = base_time + timedelta(days=duration_days)

            if current_membership:
                # 업데이트
                success = await self.db_helper.update_user_membership(
                    user_id,
                    target_level,
                    expires_at,
                    next_billing_at,
                    cancel_at_period_end=False,
                    cancel_requested_at=None,
                )
            else:
                # 새로 생성
                membership = await self.db_helper.create_user_membership(
                    user_id, target_level, expires_at, next_billing_at
                )
                success = bool(membership)
            
            if success:
                # 업그레이드 로그 기록
                await self.db_helper.log_system_event(
                    user_id=user_id,
                    event_type='membership_upgrade',
                    event_data={
                        'from_level': current_membership.get('membership_level', 0) if current_membership else 0,
                        'to_level': target_level,
                        'duration_days': duration_days,
                        'expires_at': expires_at.isoformat(),
                        'next_billing_at': next_billing_at.isoformat() if next_billing_at else None,
                    }
                )
                
                # 업데이트된 멤버십 정보 반환
                return await self.get_user_membership(user_id)
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

    async def cancel_membership(self, user_id: str) -> Dict[str, Any]:
        """멤버십을 만료 시점에 해지하도록 예약"""
        try:
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
            self.logger.error(f"멤버십 해지 예약 실패: {e}")
            raise

    async def resume_membership(self, user_id: str) -> Dict[str, Any]:
        """예약된 멤버십 해지를 취소하고 유료 멤버십을 유지"""
        try:
            membership = await self.db_helper.get_user_membership(user_id)
            if not membership or int(membership.get('membership_level', 0)) <= 0:
                raise ValueError("해지 취소할 유료 멤버십이 존재하지 않습니다")

            expires_at = self.db_helper._parse_iso_datetime(membership.get('expires_at'))
            next_billing_at = self.db_helper._parse_iso_datetime(membership.get('next_billing_at'))

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
            self.logger.error(f"멤버십 해지 취소 실패: {e}")
            raise
