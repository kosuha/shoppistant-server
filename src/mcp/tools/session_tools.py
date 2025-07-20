import requests
from datetime import datetime
from typing import Dict, Any

class SessionTools:
    def __init__(self, mcp):
        self.mcp = mcp
        self._session_tokens = {}
        self._register_tools()
    
    def _register_tools(self):
        self.mcp.tool(self.set_session_token_tool)
        self.mcp.tool(self.list_sites_tool)
    
    def get_session_data(self, session_id: str):
        """세션 데이터를 가져오는 헬퍼 함수"""
        return self._session_tokens.get(session_id)
    
    async def set_session_token_tool(self, session_id: str, user_id: str, sites: list) -> str:
        """
        세션에 여러 사이트의 토큰을 설정합니다.
        
        Args:
            session_id: 세션 ID
            user_id: 사용자 ID
            sites: 사이트 정보 리스트 [{"site_name": "...", "site_code": "...", "access_token": "..."}, ...]
        """
        print("##### CALL TOOL: set_session_token")
        self._session_tokens[session_id] = {
            "user_id": user_id,
            "sites": sites,
            "created_at": datetime.now().isoformat()
        }
        return f"세션 {session_id}에 {len(sites)}개 사이트 토큰 설정됨"

    async def list_sites_tool(self, session_id: str) -> Dict[str, Any]:
        """
        사용자의 연동된 모든 사이트 목록을 조회합니다.
        
        Args:
            session_id: 세션 ID
        """
        print("##### CALL TOOL: list_sites")
        try:
            session_data = self.get_session_data(session_id)
            
            if not session_data:
                return {"error": "세션이 존재하지 않습니다."}
            
            sites = session_data.get("sites", [])

            for site in sites:
                if "access_token" in site:
                    response = requests.get("https://openapi.imweb.me/site-info",
                        headers={
                            "Authorization": f"Bearer {site['access_token']}",
                        }
                    )
                    if response.status_code != 200:
                        print(f"사이트 호출 실패: {response.status_code} - {response.text}")
                        return {"error": f"사이트 호출 실패: {response.status_code}"}
                    site_info = response.json().get("data", {})
                    site["unit_code"] = site_info.get("unitList", [{}])[0].get("unitCode", "")
            
            site_list = [{"site_name": site["site_name"], "site_code": site["site_code"], "unit_code": site["unit_code"]} for site in sites]

            return {"sites": site_list, "total": len(site_list)}
            
        except Exception as e:
            return {"error": str(e)}