"""
리팩토링된 메인 애플리케이션
"""
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from contextlib import asynccontextmanager
import uvicorn
import logging
from datetime import datetime

# Core imports
from core.config import settings
from core.factory import ServiceFactory
from core.interfaces import IAuthService, IDatabaseHelper
from core.responses import success_response, error_response

# Router imports
from routers import auth_router, site_router, script_router, thread_router

# 로깅 설정
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 전역 변수
mcp_client = None
db_connected = False
security = HTTPBearer()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """애플리케이션 라이프사이클 관리"""
    global mcp_client, db_connected
    
    # 의존성 주입 설정
    ServiceFactory.configure_dependencies()
    logger.info("의존성 주입 컨테이너 설정 완료")
    
    # 데이터베이스 연결 확인
    try:
        db_helper = ServiceFactory.get_db_helper()
        health_status = await db_helper.health_check()
        db_connected = health_status.get('connected', False)
        
        if db_connected:
            logger.info("데이터베이스 연결 성공")
            await db_helper.log_system_event(
                event_type='server_start',
                event_data={'status': 'success', 'timestamp': datetime.now().isoformat()}
            )
        else:
            logger.error("데이터베이스 연결 실패")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 실패: {e}")
        db_connected = False
    
    # MCP 클라이언트 초기화
    mcp_client = await ServiceFactory.initialize_mcp_client()
    
    logger.info("애플리케이션 초기화 완료")
    
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
            db_helper = ServiceFactory.get_db_helper()
            await db_helper.log_system_event(
                event_type='server_stop',
                event_data={'status': 'success', 'timestamp': datetime.now().isoformat()}
            )
        except Exception as e:
            logger.error(f"종료 로그 기록 실패: {e}")

# FastAPI 애플리케이션 생성
app = FastAPI(
    title="Imweb AI Agent Server",
    description="A server for managing AI agents in Imweb",
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.DEBUG
)

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 프로덕션에서는 특정 도메인만 허용
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 의존성 주입 함수
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 사용자 정보를 가져오는 의존성"""
    auth_service = ServiceFactory.get_auth_service()
    return await auth_service.verify_auth(credentials)

# 서비스 의존성 함수들
def get_auth_service() -> IAuthService:
    return ServiceFactory.get_auth_service()

def get_script_service():
    return ServiceFactory.get_script_service()

def get_imweb_service():
    return ServiceFactory.get_imweb_service()

def get_thread_service():
    return ServiceFactory.get_thread_service()

def get_db_helper():
    return ServiceFactory.get_db_helper()

# 라우터에 의존성 주입 설정
auth_router.get_current_user = get_current_user
site_router.get_current_user = get_current_user
script_router.get_current_user = get_current_user
thread_router.get_current_user = get_current_user

# 라우터에 서비스 의존성 설정
auth_router.get_auth_service = get_auth_service
auth_router.get_imweb_service = get_imweb_service
auth_router.get_db_helper = get_db_helper

script_router.get_script_service = get_script_service
thread_router.get_thread_service = get_thread_service

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
        db_helper = ServiceFactory.get_db_helper()
        db_health = await db_helper.health_check()
        
        return success_response(
            data={
                "database": db_health,
                "playwright_mcp_client": "connected" if mcp_client else "disconnected",
                "timestamp": datetime.now().isoformat(),
                "version": "1.0.0"
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
            "environment": "development" if settings.DEBUG else "production"
        },
        message="API 상태 정상"
    )

# 라우터 등록
app.include_router(auth_router.router)
app.include_router(site_router.router)
app.include_router(script_router.router)
app.include_router(script_router.module_router)
app.include_router(thread_router.router)

if __name__ == "__main__":
    uvicorn.run(
        app, 
        host=settings.HOST, 
        port=settings.PORT,
        log_level=settings.LOG_LEVEL.lower()
    )
