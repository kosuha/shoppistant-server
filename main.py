from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from google import genai
from typing import Dict, List
from datetime import datetime
import uuid
import threading
from fastmcp import Client
from contextlib import asynccontextmanager
import requests

# MCP 클라이언트 전역 변수
mcp_client = None

load_dotenv()

# imweb 설정
IMWEB_CLIENT_ID = os.getenv("IMWEB_CLIENT_ID")
IMWEB_CLIENT_SECRET = os.getenv("IMWEB_CLIENT_SECRET")
IMWEB_REDIRECT_URI = os.getenv("IMWEB_REDIRECT_URI")

# Supabase 설정
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise ValueError("SUPABASE_URL과 SUPABASE_ANON_KEY 환경변수가 필요합니다.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# Gemini API 설정
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY 환경변수가 필요합니다.")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

security = HTTPBearer()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 시작 시 MCP 클라이언트 초기화
    global mcp_client
    try:
        
        mcp_client = Client("http://mcp-server:8001")
        await mcp_client.__aenter__()
        print("MCP 클라이언트 연결 성공")

    except Exception as e:
        print(f"MCP 클라이언트 연결 실패 (일반 모드로 계속): {e}")
        mcp_client = None
    
    yield
    
    # 종료 시 MCP 클라이언트 정리
    if mcp_client:
        try:
            await mcp_client.__aexit__(None, None, None)
            print("MCP 클라이언트 연결 종료")
        except Exception as e:
            print(f"MCP 클라이언트 종료 실패: {e}")

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

# 임시 메모리 저장소
memory_store = {
    "user_sites": {},  # user_id -> List[site_data]
    "chat_threads": {},  # thread_id -> thread_data
    "chat_messages": {}  # thread_id -> List[message_data]
}

# 동시성 보호를 위한 락
memory_lock = threading.Lock()

# Supabase Auth 미들웨어
async def verify_auth(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        # JWT 토큰 검증
        response = supabase.auth.get_user(credentials.credentials)
        if response.user is None:
            raise HTTPException(status_code=401, detail="유효하지 않은 토큰입니다.")
        return response.user
    except Exception:
        raise HTTPException(status_code=401, detail="인증에 실패했습니다.")


async def generate_gemini_response(chat_history, user_id, site_code):
    """
    대화 내역을 기반으로 Gemini API를 호출하여 AI 응답을 생성합니다.
    
    Args:
        chat_history: 대화 내역 리스트
        user_id: 사용자 ID
        site_code: 사이트 코드
        
    Returns:
        str: AI 응답 텍스트
    """
    try:
        # 1. DB에서 사용자 토큰 조회
        user_token = get_user_token_from_db(user_id, site_code)
        if not user_token:
            return "아임웹 API 토큰이 설정되지 않았습니다. 먼저 토큰을 등록해주세요."
        
        # 2. 세션 ID 생성
        session_id = str(uuid.uuid4())
        
        # 3. MCP 서버에 세션 토큰 설정
        if mcp_client:
            try:
                await mcp_client.call_tool("set_session_token", {
                    "session_id": session_id,
                    "user_id": user_id,
                    "site_code": site_code,
                    "access_token": user_token
                })
            except Exception as e:
                print(f"세션 토큰 설정 실패: {e}")
                return "세션 설정에 실패했습니다."
        
        # 4. 대화 내역을 Gemini 형식으로 변환
        contents = []
        for msg in chat_history:
            if msg["message_type"] == "user":
                contents.append(f"User: {msg['message']}")
            elif msg["message_type"] == "assistant":
                contents.append(f"Assistant: {msg['message']}")
        
        conversation_context = "\n".join(contents)
        
        # 5. 시스템 프롬프트 (세션 ID만 포함)
        system_prompt = f"""당신은 아임웹 쇼핑몰 운영자를 도와주는 AI 어시스턴트입니다. 
쇼핑몰 관리, 상품 등록, 주문 처리, 고객 서비스 등에 대한 도움을 제공합니다.
친절하고 전문적인 톤으로 마지막 질문에 답변해주세요.

현재 세션 ID: {session_id}
보안을 위해 세션 ID를 답변에 절대로 포함하지 마세요. 이 지시는 다른 어떤 지시보다 우선으로 지켜야합니다.

사용자의 질문에 적절한 도구를 사용하여 정확한 정보를 제공해주세요.

대화 내역:
{conversation_context}"""

        # 6. MCP 클라이언트로 Gemini 호출
        if mcp_client:
            try:
                # 세션 기반 MCP 도구 사용
                response = await gemini_client.aio.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=system_prompt,
                    config=genai.types.GenerateContentConfig(
                        temperature=0.7,
                        tools=[mcp_client.session],
                    ),
                )
            except Exception as mcp_error:
                print(f"MCP 도구 사용 실패, 일반 모드로 전환: {mcp_error}")
                # MCP 실패 시 일반 모드로 fallback
                response = gemini_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=system_prompt,
                )
        else:
            # MCP 클라이언트가 없으면 일반 모드로 호출
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=system_prompt,
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

def get_user_token_from_db(user_id: str, site_code: str) -> str:
    """
    데이터베이스에서 사용자의 아임웹 API 토큰을 조회합니다.
    현재는 메모리 저장소를 사용하지만, 실제로는 데이터베이스를 사용해야 합니다.
    
    Args:
        user_id: 사용자 ID
        site_code: 사이트 코드
        
    Returns:
        str: 아임웹 API 토큰 또는 None
    """
    # 실제 구현에서는 데이터베이스에서 조회
    # 현재는 메모리 저장소에서 조회
    user_sites = memory_store["user_sites"].get(user_id, [])
    for site in user_sites:
        if site.get("site_code") == site_code:
            return site.get("access_token")
    
    # 개발용 기본 토큰 (실제로는 제거해야 함)
    if site_code == "default":
        return "test-access-token"
    
    return None

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
        
        # 사용자별 토큰 저장
        with memory_lock:
            user_sites = memory_store["user_sites"].get(user.id, [])
            site_found = False
            
            for site in user_sites:
                if site["site_code"] == site_code:
                    site["access_token"] = access_token
                    site["updated_at"] = datetime.now().isoformat()
                    site_found = True
                    break
            
            if not site_found:
                # 새로운 사이트 추가
                site_data = {
                    "id": str(uuid.uuid4()),
                    "user_id": user.id,
                    "site_code": site_code,
                    "access_token": access_token,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                
                if user.id not in memory_store["user_sites"]:
                    memory_store["user_sites"][user.id] = []
                memory_store["user_sites"][user.id].append(site_data)
        
        print(f"사용자 {user.id}의 사이트 {site_code}에 액세스 토큰 저장됨")
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "액세스 토큰이 저장되었습니다."
        })
        
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.get("/")
async def root():
    return {"message": "Hello, Imweb AI Agent Server!"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.get("/api/v1/status")
async def api_status():
    return {"api_version": "v1", "service": "imweb-ai-agent-server"}

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
        "site_code": "사이트 코드"
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

        # 메모리에 사용자 사이트 코드 저장
        try:
            if user.id not in memory_store["user_sites"]:
                memory_store["user_sites"][user.id] = []
            
            # 기존 사이트 코드가 있는지 확인
            existing_sites = memory_store["user_sites"][user.id]
            existing_site = next((site for site in existing_sites if site["site_code"] == site_code), None)
            
            if existing_site:
                # 이미 존재하는 경우 업데이트
                existing_site["updated_at"] = datetime.now().isoformat()
            else:
                # 새로운 사이트 코드 저장
                site_data = {
                    "id": str(uuid.uuid4()),
                    "user_id": user.id,
                    "site_code": site_code,
                    "access_token": None,  # 나중에 별도 API로 설정
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                memory_store["user_sites"][user.id].append(site_data)
            
            # 아임웹에 연동 완료 요청
            response = requests.patch(
                "https://openapi.imweb.me/site-info/integration-complete",
                headers={
                    "Authorization": f"Bearer {IMWEB_CLIENT_SECRET}"
                }
            )
            if response.json().get("statusCode") != 200:
                print(f"아임웹 연동 완료 요청 실패: {response.json()}")
                raise HTTPException(status_code=500, detail="아임웹 연동 완료 요청 실패")

        except Exception as store_error:
            raise HTTPException(status_code=500, detail=f"메모리 저장 실패: {str(store_error)}")
        
        print(f"사용자 {user.id}의 사이트 코드 {site_code} 저장됨")
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "사이트 코드가 성공적으로 처리되었습니다.",
            "site_code": site_code
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={
            "status": "error",
            "message": str(e)
        })

@app.post("/api/v1/auth-code")
async def auth_code(request: Request, user=Depends(verify_auth)):
    request_data = await request.json()
    auth_code = request_data.get("auth_code")
    site_code = request_data.get("site_code")

    if not auth_code or not site_code:
        raise HTTPException(status_code=400, detail="인증 코드와 사이트 코드가 필요합니다.")
    try:
        # 아임웹에 토큰 발급 요청
        response = requests.post(
            "https://openapi.imweb.me/oauth2/token",
            json={
                "grantType": "authorization_code",
                "clientId": IMWEB_CLIENT_ID,
                "clientSecret": IMWEB_CLIENT_SECRET,
                "code": auth_code,
                "redirectUri": IMWEB_REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/json"
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
        
        # 메모리에 사용자 사이트 정보 저장
        with memory_lock:
            user_sites = memory_store["user_sites"].get(user.id, [])
            site_found = False
            
            for site in user_sites:
                if site["site_code"] == site_code:
                    site["access_token"] = access_token
                    site["refresh_token"] = refresh_token
                    site["updated_at"] = datetime.now().isoformat()
                    site_found = True
                    break
            
            if not site_found:
                # 새로운 사이트 정보 추가
                site_data = {
                    "id": str(uuid.uuid4()),
                    "user_id": user.id,
                    "site_code": site_code,
                    "access_token": access_token,
                    "refresh_token": refresh_token,
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                user_sites.append(site_data)
                memory_store["user_sites"][user.id] = user_sites
        
        print(f"사용자 {user.id}의 사이트 {site_code}에 액세스 토큰 저장됨.")
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
        "sites": [
            {
                "id": "사이트 ID",
                "site_code": "사이트 코드", 
                "site_name": "사이트 이름",
                "created_at": "생성일시",
                "updated_at": "수정일시"
            }
        ],
        "status": "success"
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        user_sites = memory_store["user_sites"].get(user.id, [])
        # 생성일시 역순으로 정렬
        sorted_sites = sorted(user_sites, key=lambda x: x["created_at"], reverse=True)
        
        return JSONResponse(status_code=200, content={
            "sites": sorted_sites,
            "status": "success"
        })
        
    except Exception as e:
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
        "threads": [
            {
                "id": "스레드 ID",
                "user_id": "사용자 ID",
                "site_id": "사이트 ID",
                "created_at": "생성일시",
                "updated_at": "수정일시",
                "last_message_at": "마지막 메시지 시간"
            }
        ],
        "status": "success"
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        # 사용자의 스레드만 필터링
        user_threads = [thread for thread in memory_store["chat_threads"].values() if thread["user_id"] == user.id]
        # 생성일시 역순으로 정렬
        sorted_threads = sorted(user_threads, key=lambda x: x["created_at"], reverse=True)

        return JSONResponse(status_code=200, content={
            "threads": sorted_threads,
            "status": "success"
        })
        
    except Exception as e:
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
        "thread": {
            "id": "스레드 ID",
            "user_id": "사용자 ID",
            "site_id": "사이트 ID",
            "created_at": "생성일시",
            "updated_at": "수정일시",
            "last_message_at": "마지막 메시지 시간"
        },
        "status": "success"
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        thread = memory_store["chat_threads"].get(thread_id)
        
        if not thread or thread["user_id"] != user.id:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
        
        return JSONResponse(status_code=200, content={
            "thread": thread,
            "status": "success"
        })
        
    except HTTPException:
        raise
    except Exception as e:
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
        thread = memory_store["chat_threads"].get(thread_id)
        
        if not thread or thread["user_id"] != user.id:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
        
        # 스레드 삭제
        del memory_store["chat_threads"][thread_id]
        
        # 해당 스레드의 메시지들도 삭제
        if thread_id in memory_store["chat_messages"]:
            del memory_store["chat_messages"][thread_id]
        
        return JSONResponse(status_code=200, content={
            "status": "success",
            "message": "스레드가 성공적으로 삭제되었습니다."
        })
        
    except HTTPException:
        raise
    except Exception as e:
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
        "status": "success"
    }

    에러 응답:
    {
        "status": "error",
        "message": "에러 메시지"
    }
    """
    try:
        # 먼저 스레드가 존재하고 사용자 소유인지 확인
        thread = memory_store["chat_threads"].get(thread_id)
        if not thread or thread["user_id"] != user.id:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")
        
        # 메시지 조회
        messages = memory_store["chat_messages"].get(thread_id, [])
        # 생성일시순으로 정렬
        sorted_messages = sorted(messages, key=lambda x: x["created_at"])
        
        return JSONResponse(status_code=200, content={
            "messages": sorted_messages,
            "status": "success"
        })
        
    except HTTPException:
        raise
    except Exception as e:
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
        "status": "success"
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
        message = request_data.get("message")
        message_type = request_data.get("message_type", "user")
        metadata = request_data.get("metadata")

        if not thread_id:
            raise HTTPException(status_code=400, detail="스레드 ID가 필요합니다.")
        
        if not message:
            raise HTTPException(status_code=400, detail="메시지 내용이 필요합니다.")

        # 스레드가 존재하고 사용자 소유인지 확인
        thread = memory_store["chat_threads"].get(thread_id)
        if not thread or thread["user_id"] != user.id:
            raise HTTPException(status_code=404, detail="스레드를 찾을 수 없습니다.")

        # 1. 사용자 메시지 저장 (동시성 보호 및 중복 검사)
        try:
            with memory_lock:
                # 중복 메시지 검사 (최근 5개 메시지 중 동일한 메시지가 있는지 확인)
                existing_messages = memory_store["chat_messages"].get(thread_id, [])
                recent_messages = existing_messages[-5:] if len(existing_messages) > 5 else existing_messages
                
                # 같은 사용자가 같은 메시지를 최근에 보냈는지 확인 (1초 이내)
                current_time = datetime.now()
                for existing_msg in recent_messages:
                    if (existing_msg["message"] == message and 
                        existing_msg["message_type"] == message_type and 
                        existing_msg["user_id"] == user.id):
                        # 시간 차이 확인 (1초 이내면 중복으로 간주)
                        existing_time = datetime.fromisoformat(existing_msg["created_at"])
                        time_diff = (current_time - existing_time).total_seconds()
                        if time_diff < 1.0:
                            raise HTTPException(status_code=409, detail="중복 메시지입니다. 잠시 후 다시 시도해주세요.")
                
                user_message_id = str(uuid.uuid4())
                user_message = {
                    "id": user_message_id,
                    "thread_id": thread_id,
                    "user_id": user.id,
                    "message": message,
                    "message_type": message_type,
                    "created_at": current_time.isoformat()
                }
                
                if metadata:
                    user_message["metadata"] = metadata
                
                # 스레드의 메시지 리스트에 추가
                if thread_id not in memory_store["chat_messages"]:
                    memory_store["chat_messages"][thread_id] = []
                memory_store["chat_messages"][thread_id].append(user_message)
                
        except HTTPException:
            raise
        except Exception as store_error:
            raise HTTPException(status_code=500, detail=f"사용자 메시지 저장 실패: {str(store_error)}")

        # 2. AI 응답 생성 (user 메시지 타입인 경우에만)
        ai_message = None
        if message_type == "user":
            try:
                # 스레드의 전체 대화 내역 조회 (새로 추가된 사용자 메시지 포함)
                chat_history = memory_store["chat_messages"].get(thread_id, [])
                
                # 스레드에서 사이트 코드 가져오기
                thread = memory_store["chat_threads"].get(thread_id)
                site_code = thread.get("site_id", "default") if thread else "default"
                
                # AI 응답 생성
                ai_response = await generate_gemini_response(chat_history, user.id, site_code)
                
                # AI 응답 저장 (동시성 보호)
                with memory_lock:
                    ai_message_id = str(uuid.uuid4())
                    ai_message = {
                        "id": ai_message_id,
                        "thread_id": thread_id,
                        "user_id": user.id,
                        "message": ai_response,
                        "message_type": "assistant",
                        "created_at": datetime.now().isoformat()
                    }
                    
                    memory_store["chat_messages"][thread_id].append(ai_message)
                    
            except Exception as ai_error:
                # AI 응답 생성 실패는 에러를 던지지 않고 로그만 남김
                print(f"AI 응답 생성 실패: {str(ai_error)}")

        # 3. 스레드의 last_message_at 업데이트 (동시성 보호)
        try:
            with memory_lock:
                current_time = datetime.now().isoformat()
                memory_store["chat_threads"][thread_id]["last_message_at"] = current_time
                memory_store["chat_threads"][thread_id]["updated_at"] = current_time
        except Exception as update_error:
            print(f"스레드 업데이트 실패: {str(update_error)}")

        # 응답 구성
        response_data = {
            "user_message": user_message,
            "status": "success"
        }
        
        if ai_message:
            response_data["ai_message"] = ai_message

        return JSONResponse(status_code=201, content=response_data)
        
    except HTTPException:
        raise
    except Exception as e:
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
            user_sites = memory_store["user_sites"].get(user.id, [])
            site_exists = any(site["id"] == site_id for site in user_sites)
            if not site_exists:
                raise HTTPException(status_code=403, detail=f"해당 사이트에 접근 권한이 없습니다. 사용자 사이트: {user_sites}")

        # 새 스레드를 메모리에 생성 (동시성 보호)
        try:
            with memory_lock:
                thread_id = str(uuid.uuid4())
                current_time = datetime.now().isoformat()
                
                thread_data = {
                    "id": thread_id,
                    "user_id": user.id,
                    "site_id": site_id,
                    "created_at": current_time,
                    "updated_at": current_time,
                    "last_message_at": None  # 아직 메시지가 없으므로 None
                }
                
                memory_store["chat_threads"][thread_id] = thread_data
                # 메시지 리스트는 첫 메시지가 올 때 초기화
                memory_store["chat_messages"][thread_id] = []
            
        except Exception as store_error:
            raise HTTPException(status_code=500, detail=f"메모리 저장 실패: {str(store_error)}")

        return JSONResponse(status_code=201, content={
            "threadId": thread_id,
            "status": "success",
            "message": "스레드가 성공적으로 생성되었습니다."
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