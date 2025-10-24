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
from services.paddle_billing_client import PaddleBillingClient
from services.llm_providers.langchain_manager import LangChainLLMManager

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
        lc_manager = LangChainLLMManager()

        # 외부 클라이언트들을 컨테이너에 등록
        from supabase import Client as SyncClient
        container.register_singleton(SyncClient, supabase_client)
        container.register_singleton(genai.Client, gemini_client)
        container.register_singleton(LangChainLLMManager, lc_manager)

        # Paddle Billing API 클라이언트 설정
        paddle_api_key = getattr(settings, "PADDLE_API_KEY", None)
        paddle_base_url = getattr(settings, "PADDLE_API_BASE_URL", "https://api.paddle.com")
        if paddle_api_key:
            paddle_client = PaddleBillingClient(api_key=paddle_api_key, base_url=paddle_base_url)
            container.register_singleton(PaddleBillingClient, paddle_client)
        else:
            logger.warning("[PADDLE] PADDLE_API_KEY가 설정되지 않아 PaddleBillingClient를 초기화하지 않습니다.")

        # DatabaseHelper 싱글톤 등록
        db_helper = DatabaseHelper(supabase_client, supabase_admin)
        container.register_singleton(IDatabaseHelper, db_helper)
        container.register_singleton(DatabaseHelper, db_helper)  # 하위 호환성

        # AuthService는 admin 클라이언트가 필요하므로 직접 생성
        auth_service = AuthService(supabase_client, db_helper, supabase_admin)
        container.register_singleton(IAuthService, auth_service)
        container.register_singleton(AuthService, auth_service)
        container.register_service(IScriptService, ScriptService)

        # ImwebService는 설정값이 필요하므로 직접 생성
        imweb_service = WebsiteService(db_helper)
        container.register_singleton(IImwebService, imweb_service)
        container.register_singleton(WebsiteService, imweb_service)

        # AIService 직접 생성
        ai_service = AIService(
            gemini_client=gemini_client,
            db_helper=db_helper,
            lc_manager=lc_manager,
        )
        container.register_singleton(IAIService, ai_service)
        container.register_singleton(AIService, ai_service)
        container.register_service(IThreadService, ThreadService)
        container.register_service(IMembershipService, MembershipService)

        # 레거시 서비스 등록
        container.register_service(ScriptService, ScriptService)
        container.register_service(ThreadService, ThreadService)
        container.register_service(MembershipService, MembershipService)
        
    
    @staticmethod
    async def initialize_mcp_client():
        """MCP 클라이언트 초기화 (비활성화됨)"""
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

    @staticmethod
    def get_paddle_billing_client() -> PaddleBillingClient | None:
        """Paddle Billing 클라이언트 조회"""
        try:
            return container.get(PaddleBillingClient)
        except ValueError:
            return None
