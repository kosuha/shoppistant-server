import requests
from .session_tools import SessionTools

class SiteInfo:
    def __init__(self, mcp, session_tools: SessionTools = None):
        self.mcp = mcp
        self.session_tools = session_tools
        self._register_tools()
    
    def _register_tools(self):
        self.mcp.tool(self.get_site_info)
    
    def get_session_data(self, session_id: str):
        """세션 데이터를 가져오는 헬퍼 함수"""
        if self.session_tools:
            return self.session_tools.get_session_data(session_id)
        return None
    
    async def get_site_info(self, session_id: str, site_name: str = None, site_code: str = None):
        """
        사이트 이름 또는 사이트 코드로 사이트 정보를 조회합니다.

        사이트 정보:
            siteCode: 사이트 코드
            unitCode: 사이트 유닛 코드
            name: 사이트 이름
            companyName: 회사/단체 이름
            presidentName: 대표자 이름
            phone: 사이트 전화번호
            email: 사이트 이메일
            address1: 사이트 건물주소
            address2: 사이트 상세주소
            companyRegistrationNo: 사업자 등록번호
            primaryDomain: 사이트 기본 도메인
        
        Args:
            session_id: 세션 ID
            site_name: 특정 사이트 이름 (없으면 첫 번째 사이트)
            site_code: 특정 사이트 코드 (없으면 첫 번째 사이트)
        """
        print("##### CALL TOOL: get_site_info")
        try:
            session_data = self.get_session_data(session_id)
            
            if not session_data:
                return {"error": "세션이 존재하지 않습니다."}
            
            sites = session_data.get("sites", [])
            if not sites:
                return {"error": "세션에 사이트 정보가 없습니다."}
            
            target_site = None
            if site_code:
                target_site = next((site for site in sites if site["site_code"] == site_code), None)
                if not target_site:
                    return {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
            else:
                target_site = sites[0]
            
            access_token = target_site["access_token"]

            response = requests.get("https://openapi.imweb.me/site-info",
                headers={
                    "Authorization": f"Bearer {access_token}",
                }
            )
            if response.status_code != 200:
                print(f"사이트 호출 실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            response_data = response.json()
            site_info = response_data.get("data", {})
            unit_code = site_info.get("unitList", [{}])[0].get("unitCode", "")
            if not unit_code:
                return {"error": "사이트 단위 정보가 없습니다."}

            response = requests.get(
                f"https://openapi.imweb.me/site-info/unit/{unit_code}",
                headers={
                    "Authorization": f"Bearer {access_token}"
                }
            )
            if response.status_code != 200:
                print(f"사이트 단위 정보 조회 실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            unit_info = response.json().get("data", {})
            return {
                "siteCode": unit_info.get("siteCode", ""),
                "unitCode": unit_info.get("unitCode", ""),
                "name": unit_info.get("name", ""),
                "companyName": unit_info.get("companyName", ""),
                "presidentName": unit_info.get("presidentName", ""),
                "phone": unit_info.get("phone", ""),
                "email": unit_info.get("email", ""),
                "address1": unit_info.get("address1", ""),
                "address2": unit_info.get("address2", ""),
                "companyRegistrationNo": unit_info.get("companyRegistrationNo", ""),
                "primaryDomain": unit_info.get("primaryDomain", ""),
            }
            
        except Exception as e:
            return {"error": str(e)}
        
    