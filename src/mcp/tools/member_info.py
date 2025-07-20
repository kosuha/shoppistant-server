import requests
from typing import List
from enum import Enum

class RangeType(Enum):
    GTE = "GTE"
    LTE = "LTE" 
    BETWEEN = "BETWEEN"

class BoolType(Enum):
    Y = "Y"
    N = "N"

class MemberInfo:
    def __init__(self, mcp, session_tools=None):
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
        self.mcp.tool(self.get_member_info_members)
        self.mcp.tool(self.get_member_info_members_product_wish_list)
        self.mcp.tool(self.get_member_info_members_product_cart)
        self.mcp.tool(self.get_member_info_member)
        self.mcp.tool(self.get_member_info_groups)
        self.mcp.tool(self.get_member_info_groups_members)
        self.mcp.tool(self.get_member_info_grades)
        self.mcp.tool(self.get_member_info_grades_members)
        self.mcp.tool(self.get_member_info_admin_groups)
        self.mcp.tool(self.get_member_info_admin_groups_members)
        self.mcp.tool(self.get_member_info_admin)
        self.mcp.tool(self.patch_member_info_members_agree_info)
        self.mcp.tool(self.put_member_info_members_groups)
        self.mcp.tool(self.put_member_info_members_grade)
        self.mcp.tool(self.get_member_info_members_wish_list)
        self.mcp.tool(self.get_member_info_members_carts)
        
    async def get_member_info_members(
        self,
        session_id: str, 
        page: int, 
        site_code: str,
        site_name: str | None = None,
        limit: int = 10, 
        join_time_range_type: str | None = None,
        join_time_range_value: List[str] | None = None,
        last_join_time_range_type: str | None = None,
        last_join_time_range_value: List[str] | None = None,
        sms_agree: str | None = None,
        email_agree: str | None = None,
        third_party_agree: str | None = None,
        call_num: str | None = None,
    ):
        """
        사이트 유닛 단위의 회원 정보 목록을 페이지로 조회합니다.
        1페이지에 최대 100개 회원 정보 조회 가능하며, 기본값은 10개입니다.
        사용자에게 필요한 회원 정보의 갯수를 묻고, 필요한 만큼 페이지를 지정하여 조회합니다.
        
        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            join_time_range_type: 가입 시간 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정)
            join_time_range_value: 가입 시간 검색 값
            last_join_time_range_type: 최근 로그인 시간 검색 범위
            last_join_time_range_value: 최근 로그인 시간 검색 값
            sms_agree: sms 수신 여부 (Y: 수신, N: 비수신)
            email_agree: email 수신 여부 (Y: 수신, N: 비수신)
            third_party_agree: 개인정보 제3자 제공 여부 (Y: 동의, N: 비동의)
            call_num: 회원 전화번호
        """
        print("##### CALL TOOL: get_member_info_members")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            unit_code = target_site.get("unit_code", "")
            
            params = {
                "page": page,
                "limit": limit,
                "unitCode": unit_code
            }
            
            # 필터 파라미터 추가 (None이 아닌 경우에만)
            if join_time_range_type:
                params["joinTimeRangeType"] = join_time_range_type
            if join_time_range_value:
                params["joinTimeRangeValue"] = join_time_range_value
            if last_join_time_range_type:
                params["lastLoginTimeRangeType"] = last_join_time_range_type
            if last_join_time_range_value:
                params["lastLoginTimeRangeValue"] = last_join_time_range_value
            if sms_agree:
                params["smsAgree"] = sms_agree
            if email_agree:
                params["emailAgree"] = email_agree
            if third_party_agree:
                params["thirdPartyAgree"] = third_party_agree
            if call_num:
                params["callNum"] = call_num
            
            response = requests.get(
                "https://openapi.imweb.me/member-info/members",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"회원 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}

    async def get_member_info_members_product_wish_list(
        self,
        session_id: str, 
        page: int, 
        prodNo: int,
        limit: int = 10, 
        site_code: str | None = None,
        site_name: str | None = None
    ):
        """
        위시리스트 상품 별 회원 목록 조회
        특정 상품을 위시리스트에 등록한 회원 목록을 조회합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            prodNo: 상품 번호
        """
        print("##### CALL TOOL: get_member_info_members_product_wish_list")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            params = {
                "page": page,
                "limit": limit,
                "prodNo": prodNo
            }
            
            response = requests.get(
                "https://openapi.imweb.me/member-info/members/product/wish-list",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"위시리스트 회원 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"위시리스트 회원 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}

    async def get_member_info_members_product_cart(
        self,
        session_id: str, 
        page: int, 
        prodNo: int,
        limit: int = 10, 
        site_code: str | None = None,
        site_name: str | None = None
    ):
        """
        장바구니 상품 별 회원 목록 조회
        특정 상품을 장바구니에 담은 회원 목록을 조회합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            prodNo: 상품 번호
        """
        print("##### CALL TOOL: get_member_info_members_product_cart")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            unit_code = target_site.get("unit_code", "")
            
            params = {
                "page": page,
                "limit": limit,
                "prodNo": prodNo,
                "unitCode": unit_code
            }
            
            response = requests.get(
                "https://openapi.imweb.me/member-info/members/product/carts",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"장바구니 회원 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"장바구니 회원 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}

    async def get_member_info_member(
        self,
        session_id: str, 
        member_uid: str,
        site_code: str | None = None,
        site_name: str | None = None
    ):
        """
        회원 조회
        특정 회원의 ID를 통해 상세 정보를 조회합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            member_uid: 회원 ID (회원 고유 식별자)
        """
        print("##### CALL TOOL: get_member_info_member")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            response = requests.get(
                f"https://openapi.imweb.me/member-info/members/{member_uid}",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                print(f"회원 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}

    async def get_member_info_groups(
        self,
        session_id: str, 
        page: int, 
        limit: int = 10,
        site_code: str | None = None,
        site_name: str | None = None
    ):
        """
        회원 그룹 목록 조회
        특정 사이트의 회원 그룹 목록을 페이지 단위로 조회합니다.

        Args:
            session_id: 세션 ID
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_groups")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            unit_code = target_site.get("unit_code", "")
            
            params = {
                "page": page,
                "limit": limit,
                "unitCode": unit_code
            }
            
            response = requests.get(
                "https://openapi.imweb.me/member-info/groups",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"회원 그룹 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 그룹 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}

    async def get_member_info_groups_members(
        self,
        session_id: str, 
        page: int, 
        member_group_code: str,
        limit: int = 10,
        site_code: str | None = None,
        site_name: str | None = None
    ):
        """
        회원 그룹별 회원 목록 조회
        회원그룹 아이디를 통해 회원 그룹의 회원 목록을 페이지 단위로 조회합니다.

        Args:
            session_id: 세션 ID
            page: 페이지 수 (min: 1)
            member_group_code: 회원 그룹 코드
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_groups_members")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            unit_code = target_site.get("unit_code", "")
            
            params = {
                "page": page,
                "limit": limit,
                "unitCode": unit_code
            }
            
            response = requests.get(
                f"https://openapi.imweb.me/member-info/groups/{member_group_code}/members",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"회원 그룹별 회원 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 그룹별 회원 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}

    async def get_member_info_grades(
        self,
        session_id: str, 
        page: int, 
        limit: int = 10,
        site_code: str | None = None,
        site_name: str | None = None
    ):
        """
        회원 쇼핑 등급 목록 조회
        특정 사이트의 회원 쇼핑 등급 목록을 페이지 단위로 조회합니다.

        Args:
            session_id: 세션 ID
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_grades")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            unit_code = target_site.get("unit_code", "")
            
            params = {
                "page": page,
                "limit": limit,
                "unitCode": unit_code
            }
            
            response = requests.get(
                "https://openapi.imweb.me/member-info/grades",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"회원 등급 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 등급 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_member_info_grades_members(
        self,
        session_id: str, 
        page: int, 
        is_default_grade: BoolType,
        limit: int = 10,
        member_grade_code: str | None = None,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        회원 쇼핑 등급 목록 조회
        특정 사이트의 회원 쇼핑 등급 목록을 페이지 단위로 조회합니다.

        Args:
            session_id: 세션 ID
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            is_default_grade: 기본 등급 여부 (Y: 기본 등급, N: 기본 등급 아님)
            member_grade_code: 회원 등급 코드 (없으면 전체 조회)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_grades_members")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            unit_code = target_site.get("unit_code", "")
            
            params = {
                "page": page,
                "limit": limit,
                "unitCode": unit_code
            }

            # 필터 파라미터 추가 (None이 아닌 경우에만)
            if is_default_grade:
                params["isDefaultGrade"] = is_default_grade.value
            if member_grade_code:
                params["memberGradeCode"] = member_grade_code
            
            response = requests.get(
                "https://openapi.imweb.me/member-info/grades",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"회원 쇼핑 등급 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 쇼핑 등급 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_member_info_admin_groups(
        self,
        session_id: str, 
        page: int, 
        limit: int = 10,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        운영진 그룹 목록 조회
        특정 사이트의 운영진 그룹 목록을 페이지 단위로 조회합니다.

        Args:
            session_id: 세션 ID
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_admin_groups")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            params = {
                "page": page,
                "limit": limit
            }
            
            response = requests.get(
                "https://openapi.imweb.me/member-info/admin/groups",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"운영진 그룹 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"운영진 그룹 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_member_info_admin_groups_members(
        self,
        session_id: str, 
        site_group_code: str,
        page: int, 
        limit: int = 10,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        운영진 그룹별 회원 목록 조회
        특정 사이트의 운영진 그룹별 회원 목록을 페이지 단위로 조회합니다.

        Args:
            session_id: 세션 ID
            site_group_code: 운영진 그룹 코드
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, max: 100)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_admin_groups_members")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            params = {
                "page": page,
                "limit": limit,
                "unitCode": target_site.get("unit_code", "")
            }
            
            response = requests.get(
                f"https://openapi.imweb.me/member-info/admin/groups/{site_group_code}/members",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"운영진 그룹 목록 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"운영진 그룹 목록 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}

    async def get_member_info_admin(
        self,
        session_id: str, 
        admin_uid: str,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        운영진 조회
        특정 사이트의 운영진 정보를 조회합니다.

        Args:
            session_id: 세션 ID
            admin_uid: 운영진 ID (운영진 고유 식별자)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_admin")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            response = requests.get(
                f"https://openapi.imweb.me/member-info/admin/{admin_uid}",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                print(f"운영진 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"운영진 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def patch_member_info_members_agree_info(
        self,
        session_id: str, 
        member_uid: str,
        sms_agree: BoolType | None = None,
        email_agree: BoolType | None = None,
        third_party_agree: BoolType | None = None,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        회원 동의 정보 수정
        특정 회원의 SMS, 이메일, 제3자 제공 동의 정보를 수정합니다.

        Args:
            session_id: 세션 ID
            member_uid: 회원 ID (회원 고유 식별자)
            sms_agree: SMS 수신 동의 여부 (Y: 동의, N: 비동의)
            email_agree: 이메일 수신 동의 여부 (Y: 동의, N: 비동의)
            third_party_agree: 제3자 제공 동의 여부 (Y: 동의, N: 비동의)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: patch_member_info_members_agree_info")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            json_data = {}
            if sms_agree is not None:
                json_data["smsAgree"] = sms_agree.value
            if email_agree is not None:
                json_data["emailAgree"] = email_agree.value
            if third_party_agree is not None:
                json_data["thirdPartyAgree"] = third_party_agree.value
            
            response = requests.patch(
                f"https://openapi.imweb.me/member-info/members/{member_uid}/agree-info",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json=json_data
            )
            
            if response.status_code != 200:
                print(f"회원 동의 정보 수정 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 동의 정보 수정 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def put_member_info_members_groups(
        self,
        session_id: str, 
        member_uid: str,
        group_codes: List[str],
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        회원 그룹 변경
        특정 회원을 지정한 그룹으로 변경합니다.

        Args:
            session_id: 세션 ID
            member_uid: 회원 ID (회원 고유 식별자)
            group_codes: 변경할 그룹 코드 목록
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: put_member_info_members_groups")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            json_data = {
                "unitCode": target_site.get("unit_code", ""),
                "groupCodes": group_codes
            }
            
            response = requests.patch(
                f"https://openapi.imweb.me/member-info/members/{member_uid}/groups",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json=json_data
            )
            
            if response.status_code != 200:
                print(f"회원 그룹 변경 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 그룹 변경 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def put_member_info_members_grade(
        self,
        session_id: str, 
        member_uid: str,
        is_default_grade: BoolType,
        member_grade_code: str,
        useAutoGrade: BoolType | None = None,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        회원 등급 변경
        특정 회원을 지정한 등급으로 변경합니다.

        Args:
            session_id: 세션 ID
            member_uid: 회원 ID (회원 고유 식별자)
            is_default_grade: 기본 등급 여부 (Y: 기본 등급, N: 기본 등급 아님)
            member_grade_code: 변경할 회원 등급 코드
            useAutoGrade: 자동 등급 적용 여부 (Y: 자동 적용, N: 수동 적용)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: put_member_info_members_groups")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            json_data = {
                "unitCode": target_site.get("unit_code", ""),
                "isDefaultGrade": is_default_grade.value,
                "memberGradeCode": member_grade_code
            }
            if useAutoGrade is not None:
                json_data["useAutoGrade"] = useAutoGrade.value
            
            response = requests.patch(
                f"https://openapi.imweb.me/member-info/members/{member_uid}/grade",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json=json_data
            )
            
            if response.status_code != 200:
                print(f"회원 그룹 변경 실패: {response.status_code} - {response.text}")
                return {"error": f"회원 그룹 변경 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_member_info_members_wish_list(
        self,
        session_id: str, 
        member_uid: str,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        특정 회원의 위시리스트 조회
        특정 회원이 위시리스트에 추가한 상품 목록을 조회합니다.

        Args:
            session_id: 세션 ID
            member_uid: 회원 ID (회원 고유 식별자)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_members_wish_list")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]
            
            response = requests.get(
                f"https://openapi.imweb.me/member-info/members/{member_uid}/wish-list",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            
            if response.status_code != 200:
                print(f"운영진 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"운영진 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_member_info_members_carts(
        self,
        session_id: str, 
        member_uid: str,
        site_code: str | None = None,
        site_name: str | None = None,
    ):
        """
        특정 회원의 장바구니 목록 조회
        특정 회원이 장바구니에 추가한 상품 목록을 조회합니다.

        Args:
            session_id: 세션 ID
            member_uid: 회원 ID (회원 고유 식별자)
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
        """
        print("##### CALL TOOL: get_member_info_members_carts")
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "unitCode": target_site.get("unit_code", "")
            }
            
            response = requests.get(
                f"https://openapi.imweb.me/member-info/members/{member_uid}/carts",
                headers={"Authorization": f"Bearer {access_token}"},
                params=params
            )
            
            if response.status_code != 200:
                print(f"운영진 조회 실패: {response.status_code} - {response.text}")
                return {"error": f"운영진 조회 실패: {response.status_code}"}
            
            return response.json().get("data", {})
            
        except Exception as e:
            return {"error": str(e)}