import requests
from .session_tools import SessionTools
from enum import Enum
from typing import List

class Position(Enum):
    HEADER = "header"
    BODY = "body"
    FOOTER = "footer"

class Script:
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
        self.mcp.tool(self.get_script)
        self.mcp.tool(self.post_script)
        self.mcp.tool(self.put_script)
        self.mcp.tool(self.delete_script)
        
    async def get_script(
        self, 
        session_id: str, 
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: get_script")
        """
        스크립트 조회
        아임웹 사이트에 등록된 스크립트를 조회합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        
        Returns:
            [
                {
                    "siteCode": 해당 사이트 코드,
                    "unitCode": 해당 사이트 유닛 코드,
                    "position": 스크립트 위치 ("header", "body", "footer" 중 하나),
                    "scriptContent": 스크립트 내용,
                    "wtime": 작성시간 (2022-05-15T00:00:00.000Z),
                    "mtime": 수정시간 (2022-05-15T00:00:00.000Z)
                },
                ...
            ]
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site.get("access_token")
            primary_domain = target_site.get("primary_domain")

            response = requests.get(
                "https://openapi.imweb.me/script",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params={
                    "unitCode": target_site["unit_code"]
                }
            )
            
            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def post_script(
        self, 
        session_id: str, 
        position: Position,
        script_content: str,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: post_script")
        """
        스크립트 등록
        아임웹 사이트에 스크립트를 등록합니다.

        Args:
            session_id: 세션 ID
            position: 스크립트 위치
            script_content: 스크립트 내용
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site.get("access_token")
            primary_domain = target_site.get("primary_domain")

            response = requests.post(
                "https://openapi.imweb.me/script",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json={
                    "unitCode": target_site["unit_code"],
                    "position": position.value,
                    "scriptContent": script_content
                }
            )
            
            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def put_script(
        self, 
        session_id: str, 
        position: Position,
        script_content: str,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: put_script")
        """
        스크립트 수정
        아임웹 사이트의 스크립트를 수정합니다.

        Args:
            session_id: 세션 ID
            position: 스크립트 위치
            script_content: 스크립트 내용
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site.get("access_token")
            primary_domain = target_site.get("primary_domain")

            response = requests.put(
                "https://openapi.imweb.me/script",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json={
                    "unitCode": target_site["unit_code"],
                    "position": position.value,
                    "scriptContent": script_content
                }
            )
            
            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def delete_script(
        self, 
        session_id: str, 
        position: Position,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: delete_script")
        """
        스크립트 삭제
        아임웹 사이트의 스크립트를 삭제합니다.

        Args:
            session_id: 세션 ID
            position: 스크립트 위치
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site.get("access_token")
            primary_domain = target_site.get("primary_domain")

            response = requests.delete(
                "https://openapi.imweb.me/script",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params={
                    "unitCode": target_site["unit_code"],
                    "position": position.value
                }
            )
            
            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}