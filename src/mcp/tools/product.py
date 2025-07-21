import requests
from .session_tools import SessionTools
from enum import Enum
from typing import List

class Product:
    def __init__(self, mcp, session_tools: SessionTools = None):
        self.mcp = mcp
        self.session_tools = session_tools
        self._register_tools()
    
    def get_session_data(self, session_id: str):
        """세션 데이터를 가져오는 헬퍼 함수"""
        if self.session_tools:
            return self.session_tools.get_session_data(session_id)
        return None
    
    def _get_site_and_token(self, session_id: str, site_code: str = None, site_name: str = None):
        """사이트 정보와 토큰을 가져오는 공통 헬퍼 함수"""
        session_data = self.get_session_data(session_id)
        
        if not session_data:
            return None, {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        if not sites:
            return None, {"error": "세션에 사이트 정보가 없습니다."}
        
        target_site = None
        if site_code:
            target_site = next((site for site in sites if site["site_code"] == site_code), None)
            if not target_site:
                return None, {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
        elif site_name:
            target_site = next((site for site in sites if site["site_name"] == site_name), None)
            if not target_site:
                return None, {"error": f"사이트 이름 '{site_name}'을 찾을 수 없습니다."}
        else:
            target_site = sites[0]
        
        return target_site, None
    
    def _register_tools(self):
        self.mcp.tool(self.post_product)
        
    async def post_product(
        self, 
        session_id: str, 
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: post_product")
        """
        상품 등록
        상품 등록을 위해 필요한 정보가 너무 많아서 상품 등록 URL을 제공하여 직접 등록하도록 안내합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            primary_domain = target_site.get("primary_domain")

            url = f"https://{primary_domain}/admin/shopping/product"
            return {
                "message": "상품 등록을 위해 필요한 정보가 너무 많습니다. 상품 등록 페이지에서 직접 등록해주세요.",
                "direct_link": f"[상품 등록 페이지]({url})",
            }
            
        except Exception as e:
            return {"error": str(e)}