from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from google.genai import types
from typing import Dict, List, Any
from datetime import datetime
import uuid
import threading
from fastmcp import Client
from contextlib import asynccontextmanager
import requests
import logging
from database_helper import DatabaseHelper

# MCP 클라이언트 전역 변수
mcp_client = None

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

# 환경 변수 로드
MCP_SERVER_URL = os.getenv("MCP_SERVER_URL", "http://localhost:8001")

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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# 시스템 로그용 서비스 역할 클라이언트 (선택사항)
supabase_admin = None
if SUPABASE_SERVICE_ROLE_KEY:
    supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    logger.info("Supabase 관리자 클라이언트 생성됨")
else:
    logger.warning("SUPABASE_SERVICE_ROLE_KEY가 설정되지 않음")

# 데이터베이스 헬퍼 초기화
db_helper = DatabaseHelper(supabase, supabase_admin)

# Gemini API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경변수가 필요합니다.")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 MCP 클라이언트 및 데이터베이스 초기화
    global mcp_client, db_connected
    
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
    
    # MCP 클라이언트 초기화
    try:
        mcp_client = Client(MCP_SERVER_URL)
        await mcp_client.__aenter__()
        logger.info("MCP 클라이언트 연결 성공")
    except Exception as e:
        logger.warning(f"MCP 클라이언트 연결 실패 (일반 모드로 계속): {e}")
        mcp_client = None
    
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

# 데이터베이스 연결 상태 확인을 위한 변수
db_connected = False

# Supabase Auth 미들웨어 - 간단한 JWT 검증
async def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        # JWT 토큰으로 사용자 정보 조회
        response = supabase.auth.get_user(credentials.credentials)
        if response.user is None:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        
        # 프로필 자동 생성/확인 (Service Role로 처리)
        try:
            profile = await db_helper.get_user_profile(response.user.id)
            if not profile:
                await db_helper.create_user_profile(response.user.id, response.user.email)
        except Exception as profile_error:
            logger.warning(f"프로필 처리 실패: {profile_error}")
        
        return response.user
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"인증 실패: {e}")
        raise HTTPException(status_code=401, detail="인증에 실패했습니다.")


async def generate_gemini_response(chat_history, user_id):
    """
    대화 내역을 기반으로 Gemini API를 호출하여 AI 응답을 생성합니다.
    
    Args:
        chat_history: 대화 내역 리스트
        user_id: 사용자 ID
        
    Returns:
        str: AI 응답 텍스트
    """
    try:
        # 1. 사용자의 모든 사이트와 토큰 정보 가져오기
        user_sites = await db_helper.get_user_sites(user_id, user_id)
        if not user_sites:
            return "아임웹 사이트가 연결되지 않았습니다. 먼저 사이트를 연결해주세요."
        
        # 2. 세션 ID 생성
        session_id = str(uuid.uuid4())
        
        # 3. MCP 서버에 모든 사이트 정보 설정
        if mcp_client:
            try:
                # 모든 사이트의 토큰 정보를 준비
                sites_data = []
                for site in user_sites:
                    site_code = site.get('site_code')
                    access_token = site.get('access_token')
                    if site_code and access_token:
                        # 토큰 복호화
                        decrypted_token = db_helper._decrypt_token(access_token)
                        sites_data.append({
                            "site_name": site.get('site_name', site_code) or site_code,
                            "site_code": site_code,
                            "access_token": decrypted_token
                        })
                
                if not sites_data:
                    return "아임웹 API 토큰이 설정되지 않았습니다. 먼저 토큰을 등록해주세요."
                
                # MCP 도구 호출
                await mcp_client.call_tool("set_session_token", {
                    "session_id": session_id,
                    "user_id": user_id,
                    "sites": sites_data
                })
            except Exception as e:
                print(f"세션 토큰 설정 실패: {e}")
                return "세션 설정에 실패했습니다."
        
        # 5. 대화 내역을 Gemini 형식으로 변환
        contents = []
        for msg in chat_history:
            created_at = msg.get('created_at', '')
            if msg["message_type"] == "user":
                contents.append(f"User ({created_at}): {msg['message']}")
            elif msg["message_type"] == "assistant":
                contents.append(f"Assistant ({created_at}): {msg['message']}")
        
        conversation_context = "\n".join(contents)
        
        # 6. 시스템 프롬프트 (세션 ID만 포함)
        prompt = f"""
        당신은 아임웹 쇼핑몰 운영자를 도와주는 AI 어시스턴트입니다. 
        쇼핑몰 관리, 상품 등록, 주문 처리, 고객 서비스 등에 대한 도움을 제공합니다.

        # 규칙:
        친절하게 마지막 질문에 답변해주세요.
        질문에 답할때는 답변에 필요한 정보를 얻으려면 어떤 도구를 사용해야하는지 반드시 단계별로 계획을 세우고 순차적으로 도구를 호출하여 정보를 찾으세요.
        답변은 정보를 토대로 풍부하게 작성하세요.
        답변은 정보를 보기 좋게 마크다운 형식으로 정리해서 작성하세요.
        답변은 반드시 정확한 정보를 기반으로 작성하세요.
        도구 호출에 실패한 경우 에러 'message'를 반드시 사용자에게 알리세요.

        # 현재 세션 ID: {session_id}
        보안을 위해 세션 ID를 답변에 절대로 포함하지 마세요. 이 지시는 다른 어떤 지시보다 우선으로 지켜야합니다.

        # 대화 내역:
        {conversation_context}
        """

        # 7. MCP 클라이언트로 Gemini 호출
        if mcp_client:
            try:
                # 세션 기반 MCP 도구 사용
                response = await gemini_client.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=genai.types.GenerateContentConfig(
                        temperature=0.5,
                        tools=[mcp_client.session],
                        thinking_config=types.ThinkingConfig(thinking_budget=-1)
                    ),
                )
            except Exception as mcp_error:
                print(f"MCP 도구 사용 실패, 일반 모드로 전환: {mcp_error}")
                # MCP 실패 시 일반 모드로 fallback
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
        else:
            # MCP 클라이언트가 없으면 일반 모드로 호출
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
        
        # 응답 처리
        if hasattr(response, 'text') and response.text:
            return response.text
        elif hasattr(response, 'candidates') and response.candidates:
            text_parts = []
            for candidate in response.candidates:
                if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                    for part in candidate.content.parts:
                        if hasattr(part, 'text') and part.text:
                            text_parts.append(part.text)
            return ''.join(text_parts) if text_parts else "응답을 생성할 수 없습니다."
        else:
            return "응답을 생성할 수 없습니다."
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")

async def fetch_site_info_from_imweb(access_token: str) -> Dict[str, Any]:
    """
    아임웹 API를 통해 사이트 정보를 조회합니다.
    
    Args:
        access_token: 아임웹 API 액세스 토큰
        
    Returns:
        Dict: 사이트 정보 또는 에러 정보
    """
    try:
        response = requests.get(
            "https://openapi.imweb.me/site-info",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            timeout=10
        )
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("statusCode") == 200:
                return {"success": True, "data": response_data.get("data", {})}
            else:
                return {"success": False, "error": response_data.get("error", {}).get("message", "알 수 없는 오류")}
        else:
            return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
            
    except Exception as e:
        logger.error(f"아임웹 API 호출 실패: {e}")
        return {"success": False, "error": str(e)}

async def update_site_names_from_imweb(user_id: str) -> Dict[str, Any]:
    """
    사용자의 모든 사이트 정보를 아임웹 API로 조회하여 데이터베이스의 사이트 이름을 업데이트합니다.
    
    Args:
        user_id: 사용자 ID
        
    Returns:
        Dict: 업데이트 결과
    """
    try:
        # 사용자의 모든 사이트 조회
        user_sites = await db_helper.get_user_sites(user_id, user_id)
        if not user_sites:
            return {"success": False, "message": "연결된 사이트가 없습니다."}
        
        update_results = []
        
        for site in user_sites:
            site_code = site.get('site_code')
            access_token = site.get('access_token')
            current_site_name = site.get('site_name')
            
            if not site_code or not access_token:
                update_results.append({
                    "site_code": site_code,
                    "success": False,
                    "error": "사이트 코드 또는 토큰이 없습니다."
                })
                continue
            
            # 토큰 복호화
            decrypted_token = db_helper._decrypt_token(access_token)
            
            # 아임웹 API로 사이트 정보 조회
            site_info_result = await fetch_site_info_from_imweb(decrypted_token)
            
            if site_info_result["success"]:
                site_data = site_info_result["data"]
                # 아임웹에서 사이트 이름 가져오기 (siteName 또는 title 필드)
                imweb_site_name = site_data.get('unitList')[0].get('name')
                
                if imweb_site_name and imweb_site_name != current_site_name:
                    # 데이터베이스 업데이트
                    update_success = await db_helper.update_site_name(user_id, site_code, imweb_site_name)
                    update_results.append({
                        "site_code": site_code,
                        "success": update_success,
                        "old_name": current_site_name,
                        "new_name": imweb_site_name
                    })
                else:
                    update_results.append({
                        "site_code": site_code,
                        "success": True,
                        "message": "사이트 이름이 이미 최신상태입니다."
                    })
            else:
                update_results.append({
                    "site_code": site_code,
                    "success": False,
                    "error": site_info_result["error"]
                })
        
        success_count = sum(1 for result in update_results if result["success"])
        
        return {
            "success": True,
            "message": f"{len(update_results)}개 사이트 중 {success_count}개 사이트 이름 업데이트 완료",
            "results": update_results
        }
        
    except Exception as e:
        logger.error(f"사이트 이름 업데이트 실패: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/v1/tokens")
async def set_access_token(request: Request, user=Depends(verify_auth)):
    """
    사용자의 아임웹 API 액세스 토큰을 설정하는 API
    
    요청 본문:
    {
        "site_code": "사이트 코드",
        "access_token": "액세스 토큰"
    }
    
    응답:
    {
        "status": "success",
        "message": "액세스 토큰이 저장되었습니다."
    }
    """
    try:
        request_data = await request.json()
        site_code = request_data.get("site_code")
        access_token = request_data.get("access_token")
        
        if not site_code or not access_token:
            raise HTTPException(status_code=400, detail="사이트 코드와 액세스 토큰이 필요합니다.")
        
        # 기존 사이트 확인
        existing_site = await db_helper.get_user_site_by_code(user.id, site_code)
        
        if existing_site:
            # 기존 사이트의 토큰 업데이트
            success = await db_helper.update_user_site_tokens(user.id, site_code, access_token)
            if not success:
                raise HTTPException(status_code=500, detail="토큰 업데이트에 실패했습니다.")
        else:
            # 새로운 사이트 생성
            site_data = await db_helper.create_user_site(user.id, site_code, access_token=access_token)
            if not site_data:
                raise HTTPException(status_code=500, detail="사이트 생성에 실패했습니다.")
        
        # 로그 기록
        await db_helper.log_system_event(
            user_id=user.id,
            event_type='token_set',
            event_data={'site_code': site_code, 'action': 'manual_set'}
        )
        
        # 사이트 정보를 조회해서 데이터베이스에 사이트 이름을 업데이트
        try:
            site_info_result = await fetch_site_info_from_imweb(access_token)
            if site_info_result["success"]:
                site_data = site_info_result["data"]
                imweb_site_name = site_data.get('unitList')[0].get('name')
                if imweb_site_name:
                    await db_helper.update_site_name(user.id, site_code, imweb_site_name)
        except Exception as name_update_error:
            # 사이트 이름 업데이트 실패는 전체 프로세스를 중단하지 않음
            logger.warning(f"사이트 이름 자동 업데이트 실패: {name_update_error}")
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "액세스 토큰이 저장되었습니다."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"토큰 설정 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

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
                "mcp_client": "connected" if mcp_client else "disconnected",
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

@app.post("/api/v1/imweb/site-code")
async def api_imweb_site_code(request: Request, user=Depends(verify_auth)):
    """
    클라이언트로부터 받은 ImWeb 사이트 코드를 처리하는 API
    클라이언트가 아임웹 앱스토어에서 연동하기 버튼을 클릭하면
    우리 서비스의 리다이렉트 url로 사이트 코드가 전달됩니다.
    이 API는 클라이언트로부터 해당 사이트 코드를 받아서 처리하는 역할을 합니다.
    사이트코드는 ImWeb에서 제공하는 쇼핑몰 식별자로,
    이를 통해 우리 서비스가 해당 쇼핑몰과 연동할 수 있습니다.
    
    사이트 코드를 받으면 메모리에 저장합니다.
    아임웹에 연동 완료 처리를 요청합니다.
    연동 완료 -> 인가코드 요청, 발급 -> 토큰 요청, 발급 -> 토큰 발급 받고 메모리 저장

    미들웨어에서 사용자 식별하여 해당 사용자의 사이트 코드로 메모리에 저장합니다.

    요청 본문:
    {
        "site_code": "사이트 코드"
    }

    응답:
    {
        "status": "success",
        "message": "사이트 코드가 성공적으로 처리되었습니다.",
        "data": {
            "site_code": "사이트 코드"
        }
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """

    try:
        # 요청 본문에서 site_code 추출
        request_data = await request.json()
        site_code = request_data.get("site_code")

        if not site_code:
            raise HTTPException(status_code=400, detail="사이트 코드가 필요합니다.")

        # 데이터베이스에 사용자 사이트 코드 저장
        try:
            # 기존 사이트가 있는지 확인
            existing_site = await db_helper.get_user_site_by_code(user.id, site_code)
            
            if existing_site:
                # 이미 존재하는 경우 - 별도 업데이트 불필요 (자동으로 updated_at 갱신됨)
                pass
            else:
                # 새로운 사이트 코드 저장
                site_data = await db_helper.create_user_site(user.id, site_code)
                if not site_data:
                    raise HTTPException(status_code=500, detail="사이트 생성에 실패했습니다.")
                
                # 로그 기록
                await db_helper.log_system_event(
                    user_id=user.id,
                    event_type='site_connected',
                    event_data={'site_code': site_code}
                )

        except HTTPException:
            raise
        except Exception as store_error:
            logger.error(f"사이트 저장 실패: {store_error}")
            raise HTTPException(status_code=500, detail=f"사이트 저장 실패: {str(store_error)}")
        
        print(f"사용자 {user.id}의 사이트 코드 {site_code} 저장됨")
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "사이트 코드가 성공적으로 처리되었습니다.",
            "data": {
                "site_code": site_code
            }
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.post("/api/v1/auth-code")
async def auth_code(request: Request, user=Depends(verify_auth)):
    print("인증 코드 요청")
    request_data = await request.json()
    auth_code = request_data.get("auth_code")
    site_code = request_data.get("site_code")

    if not auth_code or not site_code:
        raise HTTPException(status_code=400, detail="인증 코드와 사이트 코드가 필요합니다.")
    try:
        # 아임웹에 토큰 발급 요청
        response = requests.post(
            "https://openapi.imweb.me/oauth2/token",
            data={
                "grantType": "authorization_code",
                "clientId": IMWEB_CLIENT_ID,
                "clientSecret": IMWEB_CLIENT_SECRET,
                "code": auth_code,
                "redirectUri": IMWEB_REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            }
        )
        if response.status_code != 200:
            print(f"아임웹 토큰 발급 요청 실패: {response.json()}")
            raise HTTPException(status_code=500, detail="아임웹 토큰 발급 요청 실패")
        response_data = response.json()
        token_data = response_data.get("data", {})
        if response_data.get("statusCode") != 200:
            print(f"아임웹 토큰 발급 실패: {response_data}")
            raise HTTPException(status_code=500, detail="아임웹 토큰 발급 실패")
        access_token = token_data.get("accessToken")
        refresh_token = token_data.get("refreshToken")

        if not access_token or not refresh_token:
            raise HTTPException(status_code=500, detail="토큰 발급에 실패했습니다.")
        
        # 데이터베이스에 사용자 사이트 정보 저장
        try:
            # 기존 사이트가 있는지 확인
            existing_site = await db_helper.get_user_site_by_code(user.id, site_code)
            
            if existing_site:
                # 기존 사이트의 토큰 업데이트
                success = await db_helper.update_user_site_tokens(user.id, site_code, access_token, refresh_token)
                if not success:
                    raise HTTPException(status_code=500, detail="토큰 업데이트에 실패했습니다.")
            else:
                # 새로운 사이트 정보 추가
                site_data = await db_helper.create_user_site(user.id, site_code, access_token=access_token, refresh_token=refresh_token)
                if not site_data:
                    raise HTTPException(status_code=500, detail="사이트 생성에 실패했습니다.")
            
            # 로그 기록
            await db_helper.log_system_event(
                user_id=user.id,
                event_type='oauth_token_received',
                event_data={'site_code': site_code, 'source': 'oauth_flow'}
            )
            
        except HTTPException:
            raise
        except Exception as db_error:
            logger.error(f"데이터베이스 저장 실패: {db_error}")
            raise HTTPException(status_code=500, detail="데이터베이스 저장에 실패했습니다.")
        
        # 아임웹에 연동 완료 요청
        response = requests.patch(
            "https://openapi.imweb.me/site-info/integration-complete",
            headers={
                "Authorization": f"Bearer {access_token}"
            }
        )
        print(f"사용자 {user.id}의 사이트 {site_code}에 액세스 토큰 저장됨.")

        if response.json().get("statusCode") != 200:
            if response.json().get("statusCode") == 404:
                raise HTTPException(status_code=404, detail="이미 연동된 사이트입니다.")
            print(f"아임웹 연동 완료 요청 실패: {response.json()}")
            raise HTTPException(status_code=500, detail="아임웹 연동 완료 요청 실패")
        
        # 사이트 정보를 조회해서 데이터베이스에 사이트 이름을 업데이트
        try:
            site_info_result = await fetch_site_info_from_imweb(access_token)
            if site_info_result["success"]:
                site_data = site_info_result["data"]
                imweb_site_name = site_data.get('unitList')[0].get('name')
                if imweb_site_name:
                    await db_helper.update_site_name(user.id, site_code, imweb_site_name)
        except Exception as name_update_error:
            # 사이트 이름 업데이트 실패는 전체 프로세스를 중단하지 않음
            logger.warning(f"사이트 이름 자동 업데이트 실패: {name_update_error}")
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "토큰이 성공적으로 발급되었습니다."
        })

    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.get("/api/v1/sites")
async def get_user_sites(user=Depends(verify_auth)):
    """
    사용자의 연결된 사이트 목록을 조회하는 API
    
    응답:
    {
        "status": "success",
        "data": {
            "sites": [
                {
                    "id": "사이트 ID",
                    "site_code": "사이트 코드", 
                    "site_name": "사이트 이름",
                    "created_at": "생성일시",
                    "updated_at": "수정일시"
                }
            ]
        },
        "message": "사이트 목록 조회 성공"
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        user_sites = await db_helper.get_user_sites(user.id, user.id)
        
        # 민감한 정보 제거 (토큰 정보 숨김)
        safe_sites = []
        for site in user_sites:
            # 토큰이 있는 사이트는 이름을 아임웹에서 가져오기
            site_name = site.get("site_name")
            if site.get("access_token"):
                try:
                    site_info = await fetch_site_info_from_imweb(site["access_token"])
                    if site_info["success"]:
                        site_name = site_info["data"].get('unitList')[0].get('name', site.get("site_name"))
                    else:
                        site_name = site.get("site_name")
                except Exception as e:
                    logger.warning(f"사이트 이름 조회 실패: {e}")
                    site_name = site.get("site_name")

            safe_site = {
                "id": site.get("id"),
                "site_code": site.get("site_code"),
                "site_name": site_name,
                "created_at": site.get("created_at"),
                "updated_at": site.get("updated_at"),
                "token_configured": bool(site.get("access_token"))
            }
            safe_sites.append(safe_site)
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": {
                "sites": safe_sites
            },
            "message": "사이트 목록 조회 성공"
        })
        
    except Exception as e:
        logger.error(f"사용자 사이트 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.get("/api/v1/threads")
async def get_threads(user=Depends(verify_auth)):
    """
    사용자의 모든 스레드 목록을 조회하는 API
    
    응답:
    {
        "status": "success",
        "data": {
            "threads": [
                {
                    "id": "스레드 ID",
                    "user_id": "사용자 ID",
                    "site_id": "사이트 ID",
                    "title": "스레드 제목",
                    "created_at": "생성일시",
                    "updated_at": "수정일시",
                    "last_message_at": "마지막 메시지 시간"
                }
            ]
        },
        "message": "스레드 목록 조회 성공"
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        user_threads = await db_helper.get_user_threads(user.id, user.id)

        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": {
                "threads": user_threads
            },
            "message": "스레드 목록 조회 성공"
        })
        
    except Exception as e:
        logger.error(f"스레드 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.get("/api/v1/threads/{thread_id}")
async def get_thread(thread_id: str, user=Depends(verify_auth)):
    """
    특정 스레드의 상세 정보를 조회하는 API
    
    경로 매개변수:
    - thread_id: 조회할 스레드 ID
    
    응답:
    {
        "status": "success",
        "data": {
            "thread": {
                "id": "스레드 ID",
                "user_id": "사용자 ID",
                "site_id": "사이트 ID",
                "title": "스레드 제목",
                "created_at": "생성일시",
                "updated_at": "수정일시",
                "last_message_at": "마지막 메시지 시간"
            }
        },
        "message": "스레드 조회 성공"
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        thread = await db_helper.get_thread_by_id(user.id, thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": {
                "thread": thread
            },
            "message": "스레드 조회 성공"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.delete("/api/v1/threads/{thread_id}")
async def delete_thread(thread_id: str, user=Depends(verify_auth)):
    """
    특정 스레드를 삭제하는 API
    
    경로 매개변수:
    - thread_id: 삭제할 스레드 ID
    
    응답:
    {
        "status": "success",
        "message": "스레드가 성공적으로 삭제되었습니다."
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        # 먼저 스레드가 존재하고 사용자 소유인지 확인
        thread = await db_helper.get_thread_by_id(user.id, thread_id)
        
        if not thread:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
        
        # 스레드 삭제 (관련 메시지들도 CASCADE로 자동 삭제됨)
        success = await db_helper.delete_thread(user.id, thread_id)
        
        if not success:
            raise HTTPException(status_code=500, detail="스레드 삭제에 실패했습니다.")
        
        # 로그 기록
        await db_helper.log_system_event(
            user_id=user.id,
            event_type='thread_deleted',
            event_data={'thread_id': thread_id}
        )
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "스레드가 성공적으로 삭제되었습니다."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 삭제 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.put("/api/v1/threads/{thread_id}/title")
async def update_thread_title(thread_id: str, request: Request, user=Depends(verify_auth)):
    """
    스레드 제목을 업데이트하는 API
    
    경로 매개변수:
    - thread_id: 업데이트할 스레드 ID
    
    요청 본문:
    {
        "title": "새로운 스레드 제목"
    }
    
    응답:
    {
        "status": "success",
        "data": {
            "thread_id": "스레드 ID",
            "title": "새로운 제목"
        },
        "message": "스레드 제목이 성공적으로 업데이트되었습니다."
    }
    
    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        request_data = await request.json()
        new_title = request_data.get("title", "").strip()
        
        if not new_title:
            raise HTTPException(status_code=400, detail="제목이 필요합니다.")
        
        if len(new_title) > 200:
            raise HTTPException(status_code=400, detail="제목은 200자를 초과할 수 없습니다.")
        
        # 스레드 존재 및 권한 확인
        thread = await db_helper.get_thread_by_id(user.id, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
        
        # 제목 업데이트
        success = await db_helper.update_thread_title(thread_id, new_title)
        if not success:
            raise HTTPException(status_code=500, detail="스레드 제목 업데이트에 실패했습니다.")
        
        # 로그 기록
        await db_helper.log_system_event(
            user_id=user.id,
            event_type='thread_title_updated',
            event_data={'thread_id': thread_id, 'new_title': new_title, 'old_title': thread.get('title')}
        )
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": {
                "thread_id": thread_id,
                "title": new_title
            },
            "message": "스레드 제목이 성공적으로 업데이트되었습니다."
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"스레드 제목 업데이트 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.get("/api/v1/messages/{thread_id}")
async def get_messages(thread_id: str, user=Depends(verify_auth)):
    """
    특정 스레드의 모든 메시지를 조회하는 API
    
    경로 매개변수:
    - thread_id: 조회할 스레드 ID
    
    응답:
    {
        "messages": [
            {
                "id": "메시지 ID",
                "thread_id": "스레드 ID",
                "user_id": "사용자 ID",
                "message": "메시지 내용",
                "message_type": "메시지 타입 (user/assistant/system)",
                "metadata": "메타데이터 (선택사항)",
                "created_at": "생성일시"
            }
        ],
        "status": "success",
    "data": null
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        # 먼저 스레드가 존재하고 사용자 소유인지 확인
        thread = await db_helper.get_thread_by_id(user.id, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
        
        # 메시지 조회
        messages = await db_helper.get_thread_messages(user.id, thread_id)
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "data": {
                "messages": messages
            },
            "message": "메시지 목록 조회 성공"
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"메시지 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.post("/api/v1/messages")
async def create_message(request: Request, user=Depends(verify_auth)):
    """
    새로운 메시지를 생성하는 API
    사용자가 메시지를 보내면 자동으로 AI 응답을 생성하여 저장합니다.
    
    요청 본문:
    {
        "thread_id": "스레드 ID",
        "message": "메시지 내용",
        "message_type": "메시지 타입 (user/assistant/system, 기본값: user)",
        "metadata": "메타데이터 (선택사항)"
    }

    응답:
    {
        "user_message": {
            "id": "사용자 메시지 ID",
            "thread_id": "스레드 ID",
            "user_id": "사용자 ID",
            "message": "메시지 내용",
            "message_type": "메시지 타입",
            "metadata": "메타데이터",
            "created_at": "생성일시"
        },
        "ai_message": {
            "id": "AI 메시지 ID",
            "thread_id": "스레드 ID",
            "user_id": "사용자 ID",
            "message": "AI 응답 내용",
            "message_type": "assistant",
            "created_at": "생성일시"
        },
        "status": "success",
    "data": null
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        request_data = await request.json()
        thread_id = request_data.get("thread_id")
        message = request_data.get("message")[:2000]
        message_type = request_data.get("message_type", "user")
        metadata = request_data.get("metadata")

        if not thread_id:
            raise HTTPException(status_code=400, detail="스레드 ID가 필요합니다.")
        
        if not message:
            raise HTTPException(status_code=400, detail="메시지 내용이 필요합니다.")

        # 스레드가 존재하고 사용자 소유인지 확인
        thread = await db_helper.get_thread_by_id(user.id, thread_id)
        if not thread:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")

        # 1. 중복 메시지 검사
        if message_type == "user":
            is_duplicate = await db_helper.check_duplicate_message(user.id, thread_id, message, message_type)
            if is_duplicate:
                raise HTTPException(status_code=409, detail="중복 메시지입니다. 잠시 후 다시 시도해주세요.")

        # 스레드의 첫 메시지인 경우, 스레드의 title을 메시지로 설정
        if not thread.get('title'):
            try:
                # 스레드 제목을 메시지로 설정
                await db_helper.update_thread_title(thread_id, message)
                thread['title'] = message  # 메모리에서도 업데이트
            except Exception as title_error:
                logger.error(f"스레드 제목 업데이트 실패: {title_error}")

        # 2. 사용자 메시지 저장
        try:
            user_message = await db_helper.create_message(
                requesting_user_id=user.id,
                thread_id=thread_id,
                message=message,
                message_type=message_type,
                metadata=metadata
            )
            
            if not user_message:
                raise HTTPException(status_code=500, detail="메시지 저장에 실패했습니다.")
                
        except HTTPException:
            raise
        except Exception as store_error:
            logger.error(f"메시지 저장 실패: {store_error}")
            raise HTTPException(status_code=500, detail=f"사용자 메시지 저장 실패: {str(store_error)}")

        # 3. AI 응답 생성 (user 메시지 타입인 경우에만)
        ai_message = None
        if message_type == "user":
            try:
                # 스레드의 전체 대화 내역 조회 (새로 추가된 사용자 메시지 포함)
                chat_history = await db_helper.get_thread_messages(user.id, thread_id)
                
                # AI 응답 생성
                ai_response = await generate_gemini_response(chat_history, user.id)
                
                # AI 응답 저장
                ai_message = await db_helper.create_message(
                    requesting_user_id=user.id,
                    thread_id=thread_id,
                    message=ai_response,
                    message_type="assistant"
                )
                
                if not ai_message:
                    logger.warning("AI 응답 저장에 실패했습니다.")
                    
            except Exception as ai_error:
                # AI 응답 생성 실패는 에러를 던지지 않고 로그만 남김
                logger.error(f"AI 응답 생성 실패: {str(ai_error)}")

        # 4. 로그 기록
        try:
            await db_helper.log_system_event(
                user_id=user.id,
                event_type='message_created',
                event_data={
                    'thread_id': thread_id,
                    'message_type': message_type,
                    'has_ai_response': bool(ai_message)
                }
            )
        except Exception as log_error:
            logger.error(f"로그 기록 실패: {str(log_error)}")

        # 응답 구성
        response_data = {
            "status": "success",
            "data": {
                "user_message": user_message,
            },
            "message": "메시지가 성공적으로 저장되었습니다."
        }
        
        if ai_message:
            response_data["data"]["ai_message"] = ai_message

        return JSONResponse(status_code=201, content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

async def refresh_imweb_token(refresh_token: str) -> Dict[str, Any]:
    """
    아임웹 리프레시 토큰을 사용하여 액세스 토큰 갱신
    
    Args:
        refresh_token: 아임웹 리프레시 토큰
        
    Returns:
        Dict: 갱신 결과 (성공/실패, 새 토큰 등)
    """
    try:
        response = requests.post(
            "https://openapi.imweb.me/oauth2/token",
            data={
                "grantType": "refresh_token",
                "clientId": IMWEB_CLIENT_ID,
                "clientSecret": IMWEB_CLIENT_SECRET,
                "refreshToken": refresh_token,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded"
            },
            timeout=10
        )

        # 응답 상태 코드 확인
        logger.warning(f"아임웹 토큰 갱신 요청: {response.status_code}")
        
        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("statusCode") == 200:
                token_data = response_data.get("data", {})
                logger.info(f"\n아임웹 토큰 갱신 성공: {token_data}\n")
                return {
                    "success": True,
                    "access_token": token_data.get("accessToken"),
                    "refresh_token": token_data.get("refreshToken")
                }
            else:
                return {
                    "success": False,
                    "error": response_data.get("error", {}).get("message", "토큰 갱신 실패")
                }
        else:
            return {
                "success": False,
                "error": f"HTTP {response.status_code}: {response.text}"
            }
            
    except Exception as e:
        logger.error(f"아임웹 토큰 갱신 실패: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/v1/tokens/refresh-all")
async def refresh_all_tokens(user=Depends(verify_auth)):
    """
    사용자의 모든 사이트 토큰 일괄 갱신
    
    응답:
    {
        "status": "success",
        "message": "토큰 갱신 완료",
        "results": [
            {
                "site_code": "사이트 코드",
                "success": true,
                "message": "갱신 성공"
            }
        ]
    }
    """
    try:
        # 사용자의 모든 사이트 조회
        user_sites = await db_helper.get_user_sites(user.id, user.id)
        if not user_sites:
            return JSONResponse(status_code=200, content={
                "status": "success",
                "message": "갱신할 사이트가 없습니다.",
                "results": []
            })
        
        refresh_results = []
        
        for site in user_sites:
            site_code = site.get('site_code')
            refresh_token = site.get('refresh_token')
            
            if not site_code or not refresh_token:
                refresh_results.append({
                    "site_code": site_code,
                    "success": False,
                    "error": "리프레시 토큰이 없습니다."
                })
                continue
            
            # 토큰 복호화
            decrypted_refresh_token = db_helper._decrypt_token(refresh_token)
            
            # 토큰 갱신 시도
            refresh_result = await refresh_imweb_token(decrypted_refresh_token)
            
            if refresh_result["success"]:
                # 새 토큰으로 데이터베이스 업데이트
                update_success = await db_helper.update_user_site_tokens(
                    user.id, 
                    site_code,
                    refresh_result["access_token"],
                    refresh_result["refresh_token"]
                )
                
                if update_success:
                    refresh_results.append({
                        "site_code": site_code,
                        "success": True,
                        "message": "토큰 갱신 성공"
                    })
                    
                    # 로그 기록
                    await db_helper.log_system_event(
                        user_id=user.id,
                        event_type='token_refreshed',
                        event_data={'site_code': site_code, 'action': 'bulk_refresh'}
                    )
                else:
                    refresh_results.append({
                        "site_code": site_code,
                        "success": False,
                        "error": "데이터베이스 업데이트 실패"
                    })
            else:
                refresh_results.append({
                    "site_code": site_code,
                    "success": False,
                    "error": refresh_result["error"]
                })
        
        success_count = sum(1 for result in refresh_results if result["success"])
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": f"{len(refresh_results)}개 사이트 중 {success_count}개 토큰 갱신 완료",
            "data": {
                "sites": refresh_results
            }
        })
        
    except Exception as e:
        logger.error(f"전체 토큰 갱신 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.get("/api/v1/tokens/status-all")
async def get_all_tokens_status(user=Depends(verify_auth)):
    """
    모든 사이트 토큰 상태 조회
    
    응답:
    {
        "status": "success",
        "tokens": [
            {
                "site_code": "사이트 코드",
                "site_name": "사이트 이름",
                "has_access_token": true,
                "has_refresh_token": true,
                "last_updated": "마지막 업데이트 시간"
            }
        ]
    }
    """
    try:
        user_sites = await db_helper.get_user_sites(user.id, user.id)

        
        token_statuses = []
        for site in user_sites:
            # 아임웹에서 사이트 이름을 가져와서 업데이트
            site_code = site.get("site_code")
            await update_site_names_from_imweb(user.id)

            token_statuses.append({
                "site_code": site.get("site_code"),
                "site_name": site.get("site_name"),
                "has_access_token": bool(site.get("access_token")),
                "has_refresh_token": bool(site.get("refresh_token")),
                "last_updated": site.get("updated_at")
            })
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "tokens": token_statuses
        })
        
    except Exception as e:
        logger.error(f"토큰 상태 조회 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.post("/api/v1/sites/{site_id}/refresh-token")
async def refresh_site_token(site_id: str, user=Depends(verify_auth)):
    """
    특정 사이트 토큰 갱신
    
    경로 매개변수:
    - site_id: 사이트 코드
    
    응답:
    {
        "status": "success",
        "message": "토큰이 성공적으로 갱신되었습니다.",
        "site_code": "사이트 코드"
    }
    """
    try:
        # 사이트 존재 확인
        site = await db_helper.get_user_site_by_code(user.id, site_id)
        if not site:
            raise HTTPException(status_code=404, detail="사이트를 찾을 수 없습니다.")
        
        refresh_token = site.get('refresh_token')
        if not refresh_token:
            raise HTTPException(status_code=400, detail="리프레시 토큰이 없습니다.")
        
        # 토큰 복호화
        decrypted_refresh_token = db_helper._decrypt_token(refresh_token)
        
        # 토큰 갱신 시도
        refresh_result = await refresh_imweb_token(decrypted_refresh_token)
        
        if not refresh_result["success"]:
            raise HTTPException(status_code=500, detail=f"토큰 갱신 실패: {refresh_result['error']}")
        
        # 새 토큰으로 데이터베이스 업데이트
        update_success = await db_helper.update_user_site_tokens(
            user.id,
            site_id,
            refresh_result["access_token"],
            refresh_result["refresh_token"]
        )
        
        if not update_success:
            raise HTTPException(status_code=500, detail="데이터베이스 업데이트 실패")
        
        # 로그 기록
        await db_helper.log_system_event(
            user_id=user.id,
            event_type='token_refreshed',
            event_data={'site_code': site_id, 'action': 'single_refresh'}
        )
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "토큰이 성공적으로 갱신되었습니다.",
            "data": {
                "site_code": site_id
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"사이트 토큰 갱신 실패: {e}")
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.post("/api/v1/threads")
async def create_thread(request: Request, user=Depends(verify_auth)):
    """
    새로운 채팅 스레드를 생성하는 API
    스레드만 생성하고, 메시지는 별도의 API로 전송합니다.
    
    요청 본문:
    {
        "siteId": "사이트 ID (선택사항)"
    }

    응답:
    {
        "threadId": "생성된 스레드 ID",
        "status": "success",
        "message": "스레드가 성공적으로 생성되었습니다."
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        request_data = await request.json()
        site_id = request_data.get("siteId")
        
        # site_id가 없으면 기본값 사용하거나 생략 가능하도록 수정
        if not site_id:
            site_id = "default"  # 기본 사이트 ID 사용
            
        # 사용자가 해당 사이트에 접근 권한이 있는지 확인 (default는 항상 허용)
        if site_id != "default":
            user_sites = await db_helper.get_user_sites(user.id, user.id)
            site_exists = any(site["id"] == site_id for site in user_sites)
            if not site_exists:
                raise HTTPException(status_code=403, detail=f"해당 사이트에 접근 권한이 없습니다.")

        # 새 스레드를 데이터베이스에 생성
        try:
            thread_data = await db_helper.create_chat_thread(user.id, site_id)
            
            if not thread_data:
                raise HTTPException(status_code=500, detail="스레드 생성에 실패했습니다.")
            
            thread_id = thread_data.get("id")
            
            # 로그 기록
            await db_helper.log_system_event(
                user_id=user.id,
                event_type='thread_created',
                event_data={'thread_id': thread_id, 'site_id': site_id}
            )
            
        except HTTPException:
            raise
        except Exception as store_error:
            logger.error(f"스레드 생성 실패: {store_error}")
            raise HTTPException(status_code=500, detail=f"데이터베이스 저장 실패: {str(store_error)}")

        return JSONResponse(status_code=201, content={
            "status": "success",
            "message": "스레드가 성공적으로 생성되었습니다.",
            "data": {
                "threadId": thread_id
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })
    

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)