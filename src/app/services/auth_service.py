from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from supabase import Client
import logging

# Core imports
from core.interfaces import IAuthService, IDatabaseHelper
from core.base_service import BaseService
from core.responses import AuthenticationException

logger = logging.getLogger(__name__)


class AuthService(BaseService, IAuthService):
    """인증 서비스 - 리팩토링 버전"""
    
    def __init__(self, supabase_client: Client, db_helper: IDatabaseHelper, supabase_admin: Client = None):
        super().__init__(db_helper)
        self.supabase = supabase_client
        self.supabase_admin = supabase_admin

    async def verify_auth(self, credentials: HTTPAuthorizationCredentials):
        """JWT 토큰 검증 - 새로운 구조"""
        
        try:
            user = await self._verify_token_internal(credentials)
            return user
        except AuthenticationException:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        except Exception as e:
            self.logger.error(f"인증 실패: {e}")
            raise HTTPException(status_code=401, detail="인증에 실패했습니다.")
    
    async def _verify_token_internal(self, credentials: HTTPAuthorizationCredentials):
        """내부 토큰 검증 로직"""
        try:
            # JWT 토큰으로 사용자 정보 조회
            response = self.supabase.auth.get_user(credentials.credentials)
            
            if response.user is None:
                raise AuthenticationException("유효하지 않은 토큰입니다")
            
            
            # 프로필 자동 생성/확인
            try:
                profile = await self.db_helper.get_user_profile(response.user.id)
                if not profile:
                    await self.db_helper.create_user_profile(
                        response.user.id, 
                        response.user.email
                    )
            except Exception as profile_error:
                self.logger.warning(f"프로필 처리 실패: {profile_error}")
            
            return response.user
            
        except AuthenticationException:
            raise
        except Exception as e:
            self.logger.error(f"토큰 검증 중 오류: {e}")
            raise AuthenticationException("인증 처리 중 오류가 발생했습니다")
    
    async def delete_user_account(self, user_id: str):
        """사용자 계정 완전 삭제"""
        try:
            # 1. 사용자의 모든 데이터 삭제 (sites, scripts, threads, versions 등)
            await self.db_helper.delete_all_user_data(user_id)
            
            # 2. 사용자 프로필 삭제
            await self.db_helper.delete_user_profile(user_id)
            
            # 3. Supabase Auth에서 실제 사용자 계정 삭제
            if self.supabase_admin:
                try:
                    # Admin API를 사용하여 사용자 삭제
                    response = self.supabase_admin.auth.admin.delete_user(user_id)
                    self.logger.info(f"Supabase 계정 삭제 완료: {user_id}")
                except Exception as supabase_error:
                    # Supabase 계정 삭제가 실패해도 데이터는 이미 삭제되었으므로 경고만 로그
                    self.logger.warning(f"Supabase 계정 삭제 실패 (데이터는 삭제됨): {user_id}, 오류: {supabase_error}")
                    # 부분적 성공으로 처리 - 사용자에게는 성공으로 알림
            else:
                self.logger.warning(f"Supabase Admin 클라이언트가 설정되지 않음 - Auth 계정은 유지됨: {user_id}")
            
            self.logger.info(f"사용자 계정 삭제 처리 완료: {user_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"계정 삭제 실패 - 사용자 ID: {user_id}, 오류: {e}")
            raise HTTPException(status_code=500, detail="계정 삭제 중 오류가 발생했습니다")