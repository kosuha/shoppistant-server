from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from supabase import Client
from database_helper import DatabaseHelper
import logging

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self, supabase_client: Client, db_helper: DatabaseHelper):
        self.supabase = supabase_client
        self.db_helper = db_helper

    async def verify_auth(self, credentials: HTTPAuthorizationCredentials):
        """
        JWT 토큰을 검증하여 사용자 정보를 반환합니다.
        
        Args:
            credentials: HTTPAuthorizationCredentials 객체
            
        Returns:
            User: 검증된 사용자 객체
            
        Raises:
            HTTPException: 인증 실패 시
        """
        try:
            # JWT 토큰으로 사용자 정보 조회
            response = self.supabase.auth.get_user(credentials.credentials)
            if response.user is None:
                raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
            
            # 프로필 자동 생성/확인 (Service Role로 처리)
            try:
                profile = await self.db_helper.get_user_profile(response.user.id)
                if not profile:
                    await self.db_helper.create_user_profile(response.user.id, response.user.email)
            except Exception as profile_error:
                logger.warning(f"프로필 처리 실패: {profile_error}")
            
            return response.user
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"인증 실패: {e}")
            raise HTTPException(status_code=401, detail="인증에 실패했습니다.")