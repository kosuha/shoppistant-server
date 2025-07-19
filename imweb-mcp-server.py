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
async def set_session_token(session_id: str, user_id: str, sites: list, ctx: Context) -> str:
    """
    세션에 여러 사이트의 토큰을 설정합니다.
    
    Args:
        session_id: 세션 ID
        user_id: 사용자 ID
        sites: 사이트 정보 리스트 [{"site_name": "...", "site_code": "...", "access_token": "..."}, ...]
    """
    global _session_tokens
    _session_tokens[session_id] = {
        "user_id": user_id,
        "sites": sites,
        "created_at": datetime.now().isoformat()
    }
    await ctx.info(f"세션 {session_id}에 {len(sites)}개 사이트 토큰 설정 완료")
    return f"세션 {session_id}에 {len(sites)}개 사이트 토큰 설정됨"

@mcp.tool
async def get_site_info(session_id: str, site_name: str = None, site_code: str = None, ctx: Context = None) -> Dict[str, Any]:
    """
    사이트 이름 또는 사이트 코드로 사이트 정보를 조회합니다.

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
        site_name: 특정 사이트 이름 (없으면 첫 번째 사이트)
        site_code: 특정 사이트 코드 (없으면 첫 번째 사이트)
    """
    try:
        global _session_tokens
        session_data = _session_tokens.get(session_id)
        print(f"세션 데이터: {session_data}")
        
        if not session_data:
            await ctx.error("세션이 존재하지 않습니다.")
            return {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        if not sites:
            await ctx.error("세션에 사이트 정보가 없습니다.")
            return {"error": "세션에 사이트 정보가 없습니다."}
        
        # 특정 사이트 코드가 지정되면 해당 사이트 찾기, 없으면 첫 번째 사이트 사용
        target_site = None
        if site_code:
            target_site = next((site for site in sites if site["site_code"] == site_code), None)
            if not target_site:
                await ctx.error(f"사이트 코드 '{site_code}'를 찾을 수 없습니다.")
                return {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
        else:
            target_site = sites[0]  # 첫 번째 사이트 사용
        
        target_site_code = target_site["site_code"]
        access_token = target_site["access_token"]
        
        # 토큰 디버깅용 로깅 (앞 4자리와 뒤 4자리만 표시)
        masked_token = f"{access_token[:4]}...{access_token[-4:]}" if len(access_token) > 8 else "****"
        await ctx.info(f"사이트 {target_site_code} 정보 조회 중... (토큰: {masked_token})")
        print(f"전체 토큰: {access_token}")  # 개발용 - 나중에 제거

        response = requests.get("https://openapi.imweb.me/site-info",
            headers={
                "Authorization": f"Bearer {access_token}",
            }
        )
        if response.status_code != 200:
            await ctx.error(f"API 호출 실패: {response.status_code} - {response.text}")
            print(f"API 호출 실패: {response.status_code} - {response.text}")
            return {"error": f"API 호출 실패: {response.status_code}"}
        
        response_data = response.json()
        site_info = response_data.get("data", {})
        
        await ctx.info(f"사이트 {target_site_code} 정보 조회 완료")
        return site_info
        
    except Exception as e:
        await ctx.error(f"API 호출 실패: {str(e)}")
        return {"error": str(e)}

@mcp.tool
async def list_sites(session_id: str, ctx: Context = None) -> Dict[str, Any]:
    """
    사용자의 모든 사이트 목록을 조회합니다.
    
    Args:
        session_id: 세션 ID
    """
    try:
        global _session_tokens
        session_data = _session_tokens.get(session_id)
        
        if not session_data:
            await ctx.error("세션이 존재하지 않습니다.")
            return {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        
        # 토큰 정보는 제거하고 사이트 코드만 반환
        site_list = [{"site_name": site["site_name"], "site_code": site["site_code"]} for site in sites]
        
        await ctx.info(f"세션에 등록된 사이트 {len(site_list)}개 조회 완료")
        return {"sites": site_list, "total": len(site_list)}
        
    except Exception as e:
        await ctx.error(f"사이트 목록 조회 실패: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8001,
        path="/",
        log_level="debug",
    )