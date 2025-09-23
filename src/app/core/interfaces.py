"""
서비스 인터페이스 정의
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from datetime import datetime
from core.responses import APIResponse

class IAuthService(ABC):
    """인증 서비스 인터페이스"""
    
    @abstractmethod
    async def verify_auth(self, credentials) -> Any:
        """토큰 검증"""
        pass

class IScriptService(ABC):
    """스크립트 서비스 인터페이스"""
    
    @abstractmethod
    async def get_site_scripts(self, user_id: str, site_code: str) -> Dict[str, Any]:
        """사이트 스크립트 조회"""
        pass
    
    @abstractmethod
    async def deploy_site_scripts(self, user_id: str, site_code: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        """사이트 스크립트 배포"""
        pass

class IImwebService(ABC):
    """아임웹 서비스 인터페이스"""
    
    @abstractmethod
    async def fetch_site_info_from_imweb(self, access_token: str) -> Dict[str, Any]:
        """아임웹에서 사이트 정보 조회"""
        pass
    
    @abstractmethod
    async def get_oauth_token(self, auth_code: str) -> Dict[str, Any]:
        """OAuth 토큰 교환"""
        pass

class IAIService(ABC):
    """AI 서비스 인터페이스"""
    
    @abstractmethod
    async def generate_gemini_response(self, chat_history: List[Dict], user_id: str, metadata: Optional[str] = None, site_code: Optional[str] = None):
        """Gemini AI 응답 생성"""
        pass

class IThreadService(ABC):
    """스레드 서비스 인터페이스"""
    
    @abstractmethod
    async def create_thread(self, user_id: str, site_code: Optional[str] = None) -> Dict[str, Any]:
        """스레드 생성"""
        pass
    
    @abstractmethod
    async def get_user_threads(self, user_id: str) -> Dict[str, Any]:
        """사용자 스레드 목록 조회"""
        pass

class IDatabaseHelper(ABC):
    """데이터베이스 헬퍼 인터페이스"""
    
    @abstractmethod
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """사용자 프로필 조회"""
        pass
    
    @abstractmethod
    async def create_user_profile(self, user_id: str, display_name: str = None) -> Dict[str, Any]:
        """사용자 프로필 생성"""
        pass
    
    @abstractmethod
    async def log_system_event(self, event_type: str, event_data: Dict[str, Any], user_id: str = None):
        """시스템 이벤트 로깅"""
        pass

class IMembershipService(ABC):
    """멤버십 서비스 인터페이스"""
    
    @abstractmethod
    async def get_user_membership(self, user_id: str) -> Dict[str, Any]:
        """사용자 멤버십 정보 조회"""
        pass
    
    @abstractmethod
    async def upgrade_membership(
        self,
        user_id: str,
        target_level: int,
        duration_days: int = 30,
        next_billing_at: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """멤버십 업그레이드"""
        pass
    
    @abstractmethod
    async def extend_membership(self, user_id: str, days: int) -> Dict[str, Any]:
        """멤버십 기간 연장"""
        pass
    
    @abstractmethod
    async def check_permission(self, user_id: str, required_level: int) -> bool:
        """사용자 권한 확인"""
        pass
    
    @abstractmethod
    async def get_membership_status(self, user_id: str) -> Dict[str, Any]:
        """멤버십 상태 상세 조회"""
        pass
    
    @abstractmethod
    async def batch_cleanup_expired_memberships(self) -> Dict[str, Any]:
        """만료된 멤버십 일괄 정리"""
        pass
