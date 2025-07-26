import requests
from datetime import datetime
from typing import Dict, Any

class SessionTools:
    def __init__(self, mcp):
        self.mcp = mcp
        self._session_tokens = {}
        self._register_tools()
    
    def _register_tools(self):
        self.mcp.tool(self.set_session_token)
        self.mcp.tool(self.site_info)
    
    def get_session_data(self, session_id: str):
        """세션 데이터를 가져오는 헬퍼 함수"""
        return self._session_tokens.get(session_id)
    
    async def set_session_token(self, session_id: str, user_id: str, site: dict) -> str:
        """
        세션에 선택된 사이트 정보를 설정합니다. (OAuth 토큰 제거됨)
        
        Args:
            session_id: 세션 ID
            user_id: 사용자 ID
            site: 사이트 정보 딕셔너리 {"site_name": "...", "site_code": "...", "domain": "..."}
        """
        print("##### CALL TOOL: set_session_token")

        # 도메인 정보 확인
        if "domain" not in site:
            return f"사이트 {site.get('site_name', 'Unknown')}에 도메인 정보가 없습니다."

        self._session_tokens[session_id] = {
            "user_id": user_id,
            "site": site,  # 단일 사이트 정보
            "created_at": datetime.now().isoformat()
        }
        return f"세션 {session_id}에 사이트 '{site.get('site_name', site.get('site_code'))}' 설정됨"

    async def site_info(self, session_id: str) -> Dict[str, Any]:
        """
        현재 스레드에서 선택된 사이트 정보를 조회합니다.
        
        Args:
            session_id: 세션 ID
        """
        print("##### CALL TOOL: site_info")
        try:
            session_data = self.get_session_data(session_id)
            
            if not session_data:
                return {"error": "세션이 존재하지 않습니다."}
            
            site = session_data.get("site")
            
            if not site:
                return {"error": "세션에 사이트 정보가 없습니다."}

            # 단일 사이트 정보 반환
            site_info = {
                "site_name": site.get("site_name", "Unknown"),
                "site_code": site.get("site_code", ""),
                "domain": site.get("domain", "")
            }

            return {"site": site_info}
            
        except Exception as e:
            return {"error": str(e)}