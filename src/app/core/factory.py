"""
서비스 팩토리 - 의존성 주입 설정
"""
from supabase import create_client
from google import genai
import logging

from core.config import settings
from core.container import container
from core.interfaces import (
    IAuthService, IScriptService, IImwebService, 
    IAIService, IThreadService, IDatabaseHelper, IMembershipService
)
from database_helper import DatabaseHelper
from services.auth_service import AuthService
from services.script_service import ScriptService
from services.website_service import WebsiteService
from services.ai_service import AIService
from services.thread_service import ThreadService
from services.membership_service import MembershipService

logger = logging.getLogger(__name__)

class ServiceFactory:
    """서비스 의존성 등록 및 초기화"""
    
    @staticmethod
    def configure_dependencies():
        """의존성 주입 컨테이너 설정"""
        
        # 외부 클라이언트 생성
        supabase_client = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
        supabase_admin = None
        if settings.SUPABASE_SERVICE_ROLE_KEY:
            supabase_admin = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
        
        gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        # 외부 클라이언트들을 컨테이너에 등록
        from supabase import Client as SyncClient
        container.register_singleton(SyncClient, supabase_client)
        container.register_singleton(genai.Client, gemini_client)
        
        # DatabaseHelper 싱글톤 등록
        db_helper = DatabaseHelper(supabase_client, supabase_admin)
        container.register_singleton(IDatabaseHelper, db_helper)
        container.register_singleton(DatabaseHelper, db_helper)  # 하위 호환성
        
        # 서비스 클래스 등록 (의존성 자동 해결)
        container.register_service(IAuthService, AuthService)
        container.register_service(IScriptService, ScriptService)
        
        # ImwebService는 설정값이 필요하므로 직접 생성
        imweb_service = WebsiteService(
            db_helper
        )
        container.register_singleton(IImwebService, imweb_service)
        container.register_singleton(WebsiteService, imweb_service)
        
        # AIService 직접 생성
        ai_service = AIService(
            gemini_client=gemini_client,
            db_helper=db_helper
        )
        container.register_singleton(IAIService, ai_service)
        container.register_singleton(AIService, ai_service)
        container.register_service(IThreadService, ThreadService)
        container.register_service(IMembershipService, MembershipService)
        
        # 하위 호환성을 위한 구체 클래스도 등록
        container.register_service(AuthService, AuthService)
        container.register_service(ScriptService, ScriptService)
        # AIService는 이미 위에서 싱글톤으로 등록됨
        container.register_service(ThreadService, ThreadService)
        container.register_service(MembershipService, MembershipService)
        
        logger.info("의존성 주입 컨테이너 설정 완료")
    
    @staticmethod
    async def initialize_mcp_client():
        """MCP 클라이언트 초기화 (비활성화됨)"""
        logger.info("MCP 클라이언트 연결이 비활성화되어 있습니다.")
        return None
    
    @staticmethod
    def get_auth_service() -> IAuthService:
        """인증 서비스 조회"""
        return container.get(IAuthService)
    
    @staticmethod
    def get_script_service() -> IScriptService:
        """스크립트 서비스 조회"""
        return container.get(IScriptService)
    
    @staticmethod
    def get_imweb_service() -> IImwebService:
        """아임웹 서비스 조회"""
        return container.get(IImwebService)
    
    @staticmethod
    def get_ai_service() -> IAIService:
        """AI 서비스 조회"""
        return container.get(IAIService)
    
    @staticmethod
    def get_thread_service() -> IThreadService:
        """스레드 서비스 조회"""
        return container.get(IThreadService)
    
    @staticmethod
    def get_db_helper() -> IDatabaseHelper:
        """DB 헬퍼 조회"""
        return container.get(IDatabaseHelper)
    
    @staticmethod
    def get_website_service() -> WebsiteService:
        """웹사이트 서비스 조회"""
        return container.get(WebsiteService)
    
    @staticmethod
    def get_membership_service() -> IMembershipService:
        """멤버십 서비스 조회"""
        return container.get(IMembershipService)
