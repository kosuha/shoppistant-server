"""
테스트를 위한 Mock 서비스들
"""
from typing import Dict, Any, Optional, List
from core.interfaces import (
    IAuthService, IScriptService, IImwebService, 
    IAIService, IThreadService, IDatabaseHelper
)

class MockAuthService(IAuthService):
    """테스트용 Mock 인증 서비스"""
    
    async def verify_auth(self, credentials) -> Any:
        # Mock 사용자 객체 반환
        class MockUser:
            def __init__(self):
                self.id = "test-user-id"
                self.email = "test@example.com"
        
        return MockUser()

class MockDatabaseHelper(IDatabaseHelper):
    """테스트용 Mock 데이터베이스 헬퍼"""
    
    def __init__(self):
        self.data = {}
    
    async def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        return self.data.get(f"profile_{user_id}")
    
    async def create_user_profile(self, user_id: str, display_name: str = None) -> Dict[str, Any]:
        profile = {
            "id": user_id,
            "display_name": display_name,
            "created_at": "2023-01-01T00:00:00Z"
        }
        self.data[f"profile_{user_id}"] = profile
        return profile
    
    async def log_system_event(self, event_type: str, event_data: Dict[str, Any], user_id: str = None):
        # Mock 로깅 - 실제로는 아무것도 하지 않음
        pass

class MockScriptService(IScriptService):
    """테스트용 Mock 스크립트 서비스"""
    
    async def get_site_scripts(self, user_id: str, site_code: str) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "script": "console.log('test script');"
            }
        }
    
    async def deploy_site_scripts(self, user_id: str, site_code: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        return {
            "success": True,
            "data": {
                "deployed_at": "2023-01-01T00:00:00Z",
                "site_code": site_code
            }
        }

# 테스트 컨테이너 설정 함수
def configure_test_dependencies():
    """테스트용 의존성 설정"""
    from core.container import container
    
    # Mock 서비스들 등록
    container.register_singleton(IAuthService, MockAuthService())
    container.register_singleton(IDatabaseHelper, MockDatabaseHelper())
    container.register_singleton(IScriptService, MockScriptService())
    
    return container
