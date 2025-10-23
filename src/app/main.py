from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import signal
import asyncio
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from contextlib import asynccontextmanager
import logging
from datetime import datetime

# Core imports - 새로운 구조
from core.config import settings
from core.factory import ServiceFactory
from core.middleware import setup_exception_handlers
# from core.rate_limit_middleware import RateLimitMiddleware  # 미들웨어 제거
from core.scheduler import initialize_scheduler, cleanup_scheduler
from core.responses import success_response, error_response

# Legacy Services Import (기존 호환성)
from services.auth_service import AuthService
from services.ai_service import AIService
from services.website_service import WebsiteService
from services.script_service import ScriptService
from services.thread_service import ThreadService
from database_helper import DatabaseHelper

# Routers Import
from routers import auth_router, site_router, script_router, thread_router, sse_router, membership_router
from routers import paddle_router, public_router
from routers import version_router

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

# 환경 변수 로드 (settings에서 관리되지만 기존 코드 호환성을 위해 유지)
SUPABASE_URL = settings.SUPABASE_URL
SUPABASE_ANON_KEY = settings.SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY = settings.SUPABASE_SERVICE_ROLE_KEY
GEMINI_API_KEY = settings.GEMINI_API_KEY

# 레거시 클라이언트들 (기존 코드 호환성)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
supabase_admin = None
if SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
else:
    logger.warning("SUPABASE_SERVICE_ROLE_KEY가 설정되지 않음")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)
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
membership_service = ServiceFactory.get_membership_service()

security = HTTPBearer()

# Graceful shutdown을 위한 글로벌 변수
shutdown_event = asyncio.Event()


def signal_handler(signum, frame):
    """SIGINT (Ctrl+C) 및 SIGTERM 처리"""
    shutdown_event.set()
    # 강제 종료를 위한 시스템 종료
    import sys
    sys.exit(0)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # 시작 시 데이터베이스 초기화 (DB 헬스체크 생략)
    global db_connected

    # DB 헬스체크 없이 낙관적으로 시작하고, 로그 기록 실패 시만 플래그 내림
    db_connected = True
    try:
        await db_helper.log_system_event(
            event_type='server_start',
            event_data={'status': 'success', 'timestamp': datetime.now().isoformat()}
        )
    except Exception as e:
        logger.error(f"시작 로그 기록 실패(헬스체크 미수행): {e}")
        db_connected = False

    # 백그라운드 스케줄러 초기화 (헬스체크 없이 시도)
    try:
        await initialize_scheduler(db_helper)
    except Exception as e:
        logger.error(f"백그라운드 스케줄러 초기화 실패: {e}")

    
    yield
    
    # 종료 시 정리
    
    # SSE 연결 정리
    try:
        from routers.sse_router import cleanup_all_sse_connections
        await cleanup_all_sse_connections()
    except Exception as e:
        logger.error(f"SSE 연결 정리 실패: {e}")
    
    # 실행 중인 asyncio task 정리
    try:
        tasks = [task for task in asyncio.all_tasks() if not task.done()]
        if tasks:
            for task in tasks:
                task.cancel()
            
            # task들이 정리될 때까지 잠시 대기
            await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error(f"Task cleanup 실패: {e}")
    
    # 백그라운드 스케줄러 종료
    try:
        await cleanup_scheduler()
    except Exception as e:
        logger.error(f"백그라운드 스케줄러 종료 실패: {e}")
    
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

# 요청 제한 미들웨어 제거 - ThreadService에서 직접 처리

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

# 멤버십 라우터 의존성 설정 (멤버십 서비스만 설정, get_current_user는 직접 정의됨)
membership_router.set_dependencies(None, membership_service)

# 기본 엔드포인트
@app.get("/")
async def root():
    return success_response(
        data={"message": "Hello, Imweb AI Agent Server!"},
        message="서버가 정상적으로 실행 중입니다"
    )

@app.get("/health")
async def health_check():
    # DB 헬스체크를 수행하지 않고 정적 상태만 반환
    return success_response(
        data={
            "database": {"checked": False},
            "timestamp": datetime.now().isoformat(),
            "version": "1.0.0",
            "environment": "development" if settings.DEBUG else "production"
        },
        message="헬스 체크(DB 미검사)"
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
app.include_router(sse_router.router)  # 실시간 메시지 상태 스트리밍
app.include_router(membership_router.router)  # 멤버십 관리 라우터
app.include_router(version_router.router)  # 버전 관리 라우터
app.include_router(paddle_router.router)  # Paddle 웹훅 라우터
app.include_router(public_router.router)  # 공개 API 라우터

if __name__ == "__main__":
    # 메인 스레드에서만 신호 핸들러 등록
    try:
        import threading
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        else:
            logger.warning("메인 스레드가 아니므로 signal 핸들러 등록을 건너뜁니다")
    except Exception as e:
        logger.warning(f"signal 핸들러 등록 실패, uvicorn 기본 처리에 위임: {e}")

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower(),
        reload=settings.DEBUG
    )
