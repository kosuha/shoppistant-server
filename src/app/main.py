from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from contextlib import asynccontextmanager
import logging
from datetime import datetime
from fastmcp import Client as MCPClient

# Core imports - 새로운 구조
from core.config import settings
from core.factory import ServiceFactory
from core.middleware import setup_exception_handlers
from core.responses import success_response, error_response

# Legacy Services Import (기존 호환성)
from services.auth_service import AuthService
from services.ai_service import AIService
from services.website_service import WebsiteService
from services.script_service import ScriptService
from services.thread_service import ThreadService
from database_helper import DatabaseHelper

# Routers Import
from routers import auth_router, site_router, script_router, thread_router

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# 환경 변수 로드 (settings에서 관리되지만 기존 코드 호환성을 위해 유지)
MCP_SERVER_URL = settings.MCP_SERVER_URL
IMWEB_CLIENT_ID = settings.IMWEB_CLIENT_ID
IMWEB_CLIENT_SECRET = settings.IMWEB_CLIENT_SECRET
IMWEB_REDIRECT_URI = settings.IMWEB_REDIRECT_URI
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_ANON_KEY = settings.SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY = settings.SUPABASE_SERVICE_ROLE_KEY
GEMINI_API_KEY = settings.GEMINI_API_KEY

# 레거시 클라이언트들 (기존 코드 호환성)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin = None
if SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    logger.info("Supabase 관리자 클라이언트 생성됨")
else:
    logger.warning("SUPABASE_SERVICE_ROLE_KEY가 설정되지 않음")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
mcp_client = None
db_connected = False

# 새로운 Factory 패턴으로 서비스 초기화
ServiceFactory.configure_dependencies()

# 레거시 서비스 인스턴스들 (기존 라우터 호환성)
db_helper = ServiceFactory.get_db_helper()
auth_service = ServiceFactory.get_auth_service()
ai_service = ServiceFactory.get_ai_service()
imweb_service = ServiceFactory.get_imweb_service()
website_service = ServiceFactory.get_website_service()
script_service = ServiceFactory.get_script_service()
thread_service = ServiceFactory.get_thread_service()

security = HTTPBearer()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 시작 시 Playwright MCP 클라이언트 및 데이터베이스 초기화
    global mcp_client, db_connected
    
    logger.info("애플리케이션 초기화 시작")
    
    # 데이터베이스 연결 상태 확인
    try:
        health_status = await db_helper.health_check()
        db_connected = health_status.get('connected', False)
        if db_connected:
            logger.info("데이터베이스 연결 성공")
            # 시스템 시작 로그 기록
            await db_helper.log_system_event(
                event_type='server_start',
                event_data={'status': 'success', 'timestamp': datetime.now().isoformat()}
            )
        else:
            logger.error("데이터베이스 연결 실패")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 실패: {e}")
        db_connected = False
    
    # MCP 클라이언트 초기화 (Factory 패턴 사용)
    mcp_client = await ServiceFactory.initialize_mcp_client()
    if mcp_client:
        logger.info("MCP 클라이언트 연결 성공")
        # 레거시 인스턴스도 업데이트
        ai_service.mcp_client = mcp_client
        logger.info("레거시 AI 서비스 인스턴스에도 MCP 클라이언트 주입 완료")
        logger.info(f"AI 서비스 MCP 클라이언트 상태: {ai_service.mcp_client is not None}")
    else:
        logger.warning("MCP 클라이언트 연결 실패 (일반 모드로 계속)")
    
    logger.info("모든 서비스 인스턴스 초기화 완료")
    
    yield
    
    # 종료 시 정리
    if mcp_client:
        try:
            await mcp_client.__aexit__(None, None, None)
            logger.info("MCP 클라이언트 연결 종료")
        except Exception as e:
            logger.error(f"MCP 클라이언트 종료 실패: {e}")
    
    # 시스템 종료 로그 기록
    if db_connected:
        try:
            await db_helper.log_system_event(
                event_type='server_stop',
                event_data={'status': 'success', 'timestamp': datetime.now().isoformat()}
            )
        except Exception as e:
            logger.error(f"종료 로그 기록 실패: {e}")

app = FastAPI(
    title="Imweb AI Agent Server", 
    description="A server for managing AI agents in Imweb", 
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.DEBUG
)

# 예외 처리 미들웨어 설정
setup_exception_handlers(app)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 의존성 주입 함수들
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    return await auth_service.verify_auth(credentials)

# 라우터에서 사용할 의존성 함수들 설정
auth_router.get_current_user = get_current_user
site_router.get_current_user = get_current_user
script_router.get_current_user = get_current_user
thread_router.get_current_user = get_current_user

# 기본 엔드포인트
@app.get("/")
async def root():
    return success_response(
        data={"message": "Hello, Imweb AI Agent Server!"},
        message="서버가 정상적으로 실행 중입니다"
    )

@app.get("/health")
async def health_check():
    try:
        # 데이터베이스 상태 확인
        db_health = await db_helper.health_check()
        
        return success_response(
            data={
                "database": db_health,
                "playwright_mcp_client": "connected" if mcp_client else "disconnected",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0",
                "environment": "development" if settings.DEBUG else "production"
            },
            message="헬스 체크 성공"
        )
    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        return error_response(
            message="헬스 체크 실패",
            error_code="HEALTH_CHECK_FAILED",
            data={
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        )

@app.get("/api/v1/status")
async def api_status():
    return success_response(
        data={
            "api_version": "v1", 
            "service": "imweb-ai-agent-server",
            "environment": "development" if settings.DEBUG else "production",
            "features": {
                "dependency_injection": True,
                "exception_handling": True,
                "structured_logging": True
            }
        },
        message="API 상태 정상"
    )

# 라우터 등록
app.include_router(auth_router.router)
app.include_router(site_router.router)
app.include_router(site_router.websites_router)  # 웹사이트 추가용 라우터
app.include_router(script_router.router)
app.include_router(script_router.module_router)  # 스크립트 모듈 제공용 라우터 (인증 불필요)
app.include_router(thread_router.router)

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host=settings.HOST, 
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.DEBUG
    )