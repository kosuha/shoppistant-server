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

# Services Import
from services.auth_service import AuthService
from services.ai_service import AIService
from services.imweb_service import ImwebService
from services.script_service import ScriptService
from services.thread_service import ThreadService
from database_helper import DatabaseHelper

# Routers Import
from routers import auth_router, site_router, script_router, thread_router

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# 환경 변수 로드  
PLAYWRIGHT_MCP_SERVER_URL = os.getenv("PLAYWRIGHT_MCP_SERVER_URL", "http://localhost:8002")

# imweb 설정
IMWEB_CLIENT_ID = os.getenv("IMWEB_CLIENT_ID")
IMWEB_CLIENT_SECRET = os.getenv("IMWEB_CLIENT_SECRET")
IMWEB_REDIRECT_URI = os.getenv("IMWEB_REDIRECT_URI")

# Supabase 설정
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("SUPABASE_URL과 SUPABASE_ANON_KEY 환경변수가 필요합니다.")

# Gemini API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경변수가 필요합니다.")

# 전역 변수들
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin = None
if SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    logger.info("Supabase 관리자 클라이언트 생성됨")
else:
    logger.warning("SUPABASE_SERVICE_ROLE_KEY가 설정되지 않음")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
playwright_mcp_client = None
db_connected = False

# 서비스 인스턴스들
db_helper = DatabaseHelper(supabase, supabase_admin)
auth_service = AuthService(supabase, db_helper)
# AI 서비스는 일단 None으로 시작 (playwright_mcp_client가 필요)
ai_service = AIService(gemini_client, None, db_helper)  # playwright_mcp_client는 나중에 업데이트
imweb_service = ImwebService(IMWEB_CLIENT_ID, IMWEB_CLIENT_SECRET, IMWEB_REDIRECT_URI, db_helper)
script_service = ScriptService(db_helper)
thread_service = ThreadService(db_helper, ai_service)

security = HTTPBearer()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 시작 시 Playwright MCP 클라이언트 및 데이터베이스 초기화
    global playwright_mcp_client, db_connected
    
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
    
    # Playwright MCP 클라이언트 초기화
    try:
        playwright_mcp_client = MCPClient(PLAYWRIGHT_MCP_SERVER_URL)
        await playwright_mcp_client.__aenter__()
        logger.info("Playwright MCP 클라이언트 연결 성공")
        
        # AI 서비스의 playwright_mcp_client 업데이트
        ai_service.playwright_mcp_client = playwright_mcp_client
        logger.info("AI 서비스에 Playwright MCP 클라이언트 연결됨")
    except Exception as e:
        logger.warning(f"Playwright MCP 클라이언트 연결 실패 (일반 모드로 계속): {e}")
        playwright_mcp_client = None
    
    logger.info("모든 서비스 인스턴스 초기화 완료")
    
    yield
    
    # 종료 시 정리
    if playwright_mcp_client:
        try:
            await playwright_mcp_client.__aexit__(None, None, None)
            logger.info("Playwright MCP 클라이언트 연결 종료")
        except Exception as e:
            logger.error(f"Playwright MCP 클라이언트 종료 실패: {e}")
    
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
    lifespan=lifespan
)

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
    return {"status": "success", "message": "Hello, Imweb AI Agent Server!"}

@app.get("/health")
async def health_check():
    try:
        # 데이터베이스 상태 확인
        db_health = await db_helper.health_check()
        
        return {
            "status": "success",
            "data": {
                "database": db_health,
                "playwright_mcp_client": "connected" if playwright_mcp_client else "disconnected",
                "timestamp": datetime.now().isoformat()
            },
            "message": "헬스 체크 성공"
        }
    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        return {
            "status": "unhealthy",
            "message": "헬스 체크 실패",
            "data": {
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
        }

@app.get("/api/v1/status")
async def api_status():
    return {
        "status": "success",
        "message": "Imweb AI Agent Server is running",
        "data": {
            "api_version": "v1", 
            "service": "imweb-ai-agent-server"
        }
    }

# 라우터 등록
app.include_router(auth_router.router)
app.include_router(site_router.router)
app.include_router(script_router.router)
app.include_router(script_router.module_router)  # 스크립트 모듈 제공용 라우터 (인증 불필요)
app.include_router(thread_router.router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)