"""
서비스 팩토리 - 의존성 주입 설정
"""
from supabase import create_client
from google import genai
from fastmcp import Client as MCPClient
import logging

from core.config import settings
from core.container import container
from core.interfaces import (
    IAuthService, IScriptService, IImwebService, 
    IAIService, IThreadService, IDatabaseHelper
)
from database_helper import DatabaseHelper
from services.auth_service import AuthService
from services.script_service import ScriptService
from services.imweb_service import WebsiteService
from services.ai_service import AIService
from services.thread_service import ThreadService

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
        from fastmcp import Client as MCPClient
        container.register_singleton(SyncClient, supabase_client)
        container.register_singleton(genai.Client, gemini_client)
        
        # MCP 클라이언트는 일단 None으로 등록 (나중에 초기화)
        container.register_singleton(MCPClient, None)
        
        # DatabaseHelper 싱글톤 등록
        db_helper = DatabaseHelper(supabase_client, supabase_admin)
        container.register_singleton(IDatabaseHelper, db_helper)
        container.register_singleton(DatabaseHelper, db_helper)  # 하위 호환성
        
        # 서비스 클래스 등록 (의존성 자동 해결)
        container.register_service(IAuthService, AuthService)
        container.register_service(IScriptService, ScriptService)
        
        # ImwebService는 설정값이 필요하므로 직접 생성
        imweb_service = WebsiteService(
            settings.IMWEB_CLIENT_ID,
            settings.IMWEB_CLIENT_SECRET, 
            settings.IMWEB_REDIRECT_URI,
            db_helper
        )
        container.register_singleton(IImwebService, imweb_service)
        container.register_singleton(WebsiteService, imweb_service)
        
        # AIService는 MCP 클라이언트 때문에 직접 생성
        ai_service = AIService(
            gemini_client=gemini_client,
            mcp_client=None,  # 나중에 주입
            db_helper=db_helper
        )
        container.register_singleton(IAIService, ai_service)
        container.register_singleton(AIService, ai_service)
        container.register_service(IThreadService, ThreadService)
        
        # 하위 호환성을 위한 구체 클래스도 등록
        container.register_service(AuthService, AuthService)
        container.register_service(ScriptService, ScriptService)
        container.register_service(WebsiteService, WebsiteService)
        # AIService는 이미 위에서 싱글톤으로 등록됨
        container.register_service(ThreadService, ThreadService)
        
        logger.info("의존성 주입 컨테이너 설정 완료")
    
    @staticmethod
    async def initialize_mcp_client() -> MCPClient:
        """MCP 클라이언트 초기화"""
        try:
            logger.info(f"MCP 클라이언트 초기화 시작: {settings.MCP_SERVER_URL}")
            mcp_client = MCPClient(settings.MCP_SERVER_URL)
            await mcp_client.__aenter__()
            logger.info("MCP 클라이언트 연결 성공")
            
            # 컨테이너에 실제 MCP 클라이언트 등록 (기존 None 대체)
            container.register_singleton(MCPClient, mcp_client)
            logger.info("컨테이너에 MCP 클라이언트 등록 완료")
            
            # 모든 AI 서비스 인스턴스에 MCP 클라이언트 주입
            try:
                ai_service = container.get(IAIService)
                logger.info(f"AI 서비스 조회 성공: {type(ai_service)}")
                ai_service.mcp_client = mcp_client
                logger.info("AI 서비스에 MCP 클라이언트 주입 완료")
            except Exception as inject_error:
                logger.error(f"AI 서비스에 MCP 클라이언트 주입 실패: {inject_error}")
            
            # 하위 호환성을 위해 AIService로도 조회해서 주입
            try:
                ai_service_concrete = container.get(AIService)
                logger.info(f"AIService 구체 클래스 조회 성공: {type(ai_service_concrete)}")
                ai_service_concrete.mcp_client = mcp_client
                logger.info("AIService 구체 클래스에도 MCP 클라이언트 주입 완료")
            except Exception as inject_error:
                logger.warning(f"AIService 구체 클래스에 MCP 클라이언트 주입 실패: {inject_error}")

            logger.info("MCP 클라이언트 초기화 완료")
            return mcp_client
        except Exception as e:
            logger.error(f"MCP 클라이언트 초기화 실패: {e}")
            import traceback
            logger.error(f"스택트레이스: {traceback.format_exc()}")
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
