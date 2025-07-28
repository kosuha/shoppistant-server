"""
멤버십 관리 서비스
사용자 멤버십 등급, 만료일 관리 및 권한 검증
"""
import logging
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from enum import IntEnum

from core.interfaces import IDatabaseHelper, IMembershipService
from core.base_service import BaseService

logger = logging.getLogger(__name__)

class MembershipLevel(IntEnum):
    """멤버십 레벨 열거형"""
    BASIC = 0      # 기본 등급 (무료)
    PREMIUM = 1    # 프리미엄 등급
    PRO = 2        # 프로 등급

class MembershipService(BaseService, IMembershipService):
    """멤버십 관리 서비스"""
    
    def __init__(self, db_helper: IDatabaseHelper):
        super().__init__(db_helper)
    
    async def get_user_membership(self, user_id: str) -> Dict[str, Any]:
        """사용자 멤버십 정보 조회"""
        try:
            membership = await self.db_helper.get_user_membership(user_id)
            
            if not membership:
                # 멤버십이 없으면 기본 멤버십 생성 시도
                membership = await self.db_helper.create_user_membership(user_id, MembershipLevel.BASIC)
                if membership:
                    self.logger.info(f"기본 멤버십 자동 생성: user_id={user_id}")
                else:
                    # 멤버십 생성 실패 시 기본값 반환
                    self.logger.warning(f"멤버십 생성 실패, 기본값 반환: user_id={user_id}")
                    return {
                        'id': str(uuid.uuid4()),
                        'user_id': user_id,
                        'membership_level': MembershipLevel.BASIC,
                        'expires_at': None,
                        'created_at': None,
                        'updated_at': None,
                        'is_expired': False,
                        'days_remaining': None
                    }
            
            if not membership:
                return None
                
            # 응답 데이터 가공
            result = {
                **membership,
                'is_expired': self._is_membership_expired(membership),
                'days_remaining': self._get_days_remaining(membership)
            }
            
            return result
            
        except Exception as e:
            self.logger.error(f"멤버십 조회 실패: {e}")
            return None
    
    async def upgrade_membership(self, user_id: str, target_level: int, 
                               duration_days: int = 30) -> Dict[str, Any]:
        """멤버십 업그레이드"""
        try:
            # 유효한 레벨인지 확인
            if target_level not in [level.value for level in MembershipLevel]:
                raise ValueError(f"유효하지 않은 멤버십 레벨: {target_level}")
            
            # 기본 등급으로의 다운그레이드는 별도 처리
            if target_level == MembershipLevel.BASIC:
                return await self._downgrade_to_basic(user_id)
            
            # 만료일 계산
            expires_at = datetime.now() + timedelta(days=duration_days)
            
            # 기존 멤버십 조회
            current_membership = await self.db_helper.get_user_membership(user_id)
            
            if current_membership:
                # 업데이트
                success = await self.db_helper.update_user_membership(
                    user_id, target_level, expires_at
                )
            else:
                # 새로 생성
                membership = await self.db_helper.create_user_membership(
                    user_id, target_level, expires_at
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
                        'expires_at': expires_at.isoformat()
                    }
                )
                
                self.logger.info(f"멤버십 업그레이드 성공: user_id={user_id}, level={target_level}")
                
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
            
            # 기본 등급은 연장할 수 없음
            if current_level == MembershipLevel.BASIC:
                raise ValueError("기본 등급은 연장할 수 없습니다")
            
            # 현재 만료일 기준으로 연장
            current_expires = current_membership.get('expires_at')
            if current_expires:
                current_expires_dt = datetime.fromisoformat(current_expires.replace('Z', '+00:00'))
                # 이미 만료되었다면 현재 시간부터 계산
                base_time = max(current_expires_dt, datetime.now().replace(tzinfo=current_expires_dt.tzinfo))
            else:
                base_time = datetime.now()
            
            new_expires_at = base_time + timedelta(days=days)
            
            success = await self.db_helper.update_user_membership(
                user_id, current_level, new_expires_at
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
                
                self.logger.info(f"멤버십 연장 성공: user_id={user_id}, days={days}")
                return await self.get_user_membership(user_id)
            else:
                raise Exception("멤버십 연장 실패")
                
        except Exception as e:
            self.logger.error(f"멤버십 연장 실패: {e}")
            return {}
    
    async def check_permission(self, user_id: str, required_level: int) -> bool:
        """사용자 권한 확인"""
        return await self.db_helper.check_membership_level(user_id, required_level)
    
    async def get_membership_status(self, user_id: str) -> Dict[str, Any]:
        """멤버십 상태 상세 조회"""
        try:
            membership = await self.get_user_membership(user_id)
            
            if not membership:
                return {'status': 'no_membership'}
            
            level = membership.get('membership_level', 0)
            expires_at = membership.get('expires_at')
            
            status = {
                'level': level,
                'expires_at': expires_at,
                'is_expired': self._is_membership_expired(membership),
                'days_remaining': self._get_days_remaining(membership)
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
            
            self.logger.info(f"만료된 멤버십 배치 정리 완료: {downgraded_count}건")
            return result
            
        except Exception as e:
            self.logger.error(f"배치 정리 실패: {e}")
            return {'success': False, 'error': str(e)}
    
    def _is_membership_expired(self, membership: Dict[str, Any]) -> bool:
        """멤버십 만료 여부 확인"""
        expires_at = membership.get('expires_at')
        if not expires_at:
            return False  # 만료일이 없는 기본 등급
        
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            return expires_dt < datetime.now().replace(tzinfo=expires_dt.tzinfo)
        except:
            return False
    
    def _get_days_remaining(self, membership: Dict[str, Any]) -> Optional[int]:
        """남은 일수 계산"""
        expires_at = membership.get('expires_at')
        if not expires_at:
            return None  # 무제한 (기본 등급)
        
        try:
            expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
            remaining = expires_dt - datetime.now().replace(tzinfo=expires_dt.tzinfo)
            return max(0, remaining.days)
        except:
            return None
    
    
    async def _downgrade_to_basic(self, user_id: str) -> Dict[str, Any]:
        """기본 등급으로 다운그레이드"""
        try:
            success = await self.db_helper.update_user_membership(
                user_id, MembershipLevel.BASIC, None
            )
            
            if success:
                await self.db_helper.log_system_event(
                    user_id=user_id,
                    event_type='membership_downgrade',
                    event_data={'reason': 'manual', 'new_level': MembershipLevel.BASIC}
                )
                
                return await self.get_user_membership(user_id)
            else:
                raise Exception("다운그레이드 실패")
                
        except Exception as e:
            self.logger.error(f"기본 등급 다운그레이드 실패: {e}")
            return {}