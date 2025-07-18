from fastmcp import FastMCP, Context
from fastmcp.server.auth import BearerAuthProvider
import requests
import jwt
import os
from typing import Dict, Any
from datetime import datetime

# JWT 시크릿 키 (환경 변수에서 관리)
JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key-change-this-in-production")

# Bearer 인증 프로바이더 설정 (JWT 검증용)
# FastMCP는 RSA 비대칭키만 지원하므로 임시로 인증 제거
# 실제 운영에서는 RSA 키 쌍을 생성하여 사용해야 함
auth = None  # 개발 단계에서는 인증 제거

# 세션 기반 토큰 저장소
_session_tokens = {}

mcp = FastMCP(name="imweb-mcp-server")

@mcp.tool
async def set_session_token(session_id: str, user_id: str, site_code: str, access_token: str, ctx: Context) -> str:
    """
    세션에 토큰을 설정합니다.
    
    Args:
        session_id: 세션 ID
        user_id: 사용자 ID
        site_code: 사이트 코드
        access_token: 아임웹 API 액세스 토큰
    """
    global _session_tokens
    _session_tokens[session_id] = {
        "user_id": user_id,
        "site_code": site_code,
        "access_token": access_token,
        "created_at": datetime.now().isoformat()
    }
    await ctx.info(f"세션 {session_id} 토큰 설정 완료")
    return f"세션 {session_id} 토큰 설정됨"

@mcp.tool
async def get_site_info(session_id: str, ctx: Context) -> Dict[str, Any]:
    """
    사이트 정보를 조회합니다.

    사이트 정보:
        siteCode: 사이트 코드
        firstOrderTime: 첫 주문 시간
        ownerUid: 사이트 소유자 ID
        unitList: 사이트 단위 목록
        unitList.0.unitCode: 단위 코드
        unitList.0.name: 사이트 단위 이름
        unitList.0.currency: 사이트 단위 통화
    
    Args:
        session_id: 세션 ID
    """
    try:
        global _session_tokens
        session_data = _session_tokens.get(session_id)
        
        if not session_data:
            await ctx.error("세션이 존재하지 않습니다.")
            return {"error": "세션이 존재하지 않습니다."}
        
        site_code = session_data["site_code"]
        access_token = session_data["access_token"]
        
        await ctx.info(f"사이트 {site_code} 정보 조회 중...")

        response = requests.get("https://openapi.imweb.me/site-info",
            headers={
                "Authorization": f"Bearer {access_token}",
            }
        )
        if response.status_code != 200:
            await ctx.error(f"API 호출 실패: {response.status_code} - {response.text}")
            return {"error": f"API 호출 실패: {response.status_code}"}
        
        response_data = response.json()
        site_info = response_data.get("data", {})
        
        await ctx.info("사이트 정보 조회 완료")
        return site_info
        
    except Exception as e:
        await ctx.error(f"API 호출 실패: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8001,
        path="/",
        log_level="debug",
    )