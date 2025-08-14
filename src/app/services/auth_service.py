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
    
    def __init__(self, supabase_client: Client, db_helper: IDatabaseHelper):
        super().__init__(db_helper)
        self.supabase = supabase_client

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