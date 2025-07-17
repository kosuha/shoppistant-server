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

load_dotenv()

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

client = genai.Client(api_key=GEMINI_API_KEY)

security = HTTPBearer()

app = FastAPI(title="Imweb AI Agent Server", description="A server for managing AI agents in Imweb", version="1.0.0")

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

async def generate_gemini_response(chat_history):
    """
    대화 내역을 기반으로 Gemini API를 호출하여 AI 응답을 생성합니다.
    
    Args:
        chat_history: 대화 내역 리스트
        
    Returns:
        str: AI 응답 텍스트
    """
    try:
        # 대화 내역을 Gemini 형식으로 변환
        contents = []
        for msg in chat_history:
            if msg["message_type"] == "user":
                contents.append(f"User: {msg['message']}")
            elif msg["message_type"] == "assistant":
                contents.append(f"Assistant: {msg['message']}")
        
        # 전체 대화 내역을 하나의 문자열로 결합
        conversation_context = "\n".join(contents)
        
        # 시스템 프롬프트 추가
        system_prompt = """당신은 아임웹 쇼핑몰 운영자를 도와주는 AI 어시스턴트입니다. 
쇼핑몰 관리, 상품 등록, 주문 처리, 고객 서비스 등에 대한 도움을 제공합니다.
친절하고 전문적인 톤으로 마지막 질문에 답변해주세요.

대화 내역:
""" + conversation_context

        # Gemini API 호출
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=system_prompt,
        )
        
        return response.text
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")

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
                    "created_at": datetime.now().isoformat(),
                    "updated_at": datetime.now().isoformat()
                }
                memory_store["user_sites"][user.id].append(site_data)
                
        except Exception as store_error:
            raise HTTPException(status_code=500, detail=f"메모리 저장 실패: {str(store_error)}")
        

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

        print(f"DEBUG: Retrieved messages for thread_id={thread_id}: {sorted_messages}")
        
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
                
                # AI 응답 생성
                ai_response = await generate_gemini_response(chat_history)
                
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