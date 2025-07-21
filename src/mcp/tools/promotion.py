import requests
from .session_tools import SessionTools
from enum import Enum
from typing import List

class BoolType(Enum):
    Y = "Y"
    N = "N"

class RangeType(Enum):
    GTE = "GTE"
    LTE = "LTE" 
    BETWEEN = "BETWEEN"

class PointType(Enum):
    JOIN = "join"
    APP = "app"
    ORDER_USE = "order_use"
    CANCEL_ORDER_USED = "cancel_order_used"
    ORDER_REWARD = "order_reward"
    ORDER_FAIL = "order_fail"
    CANCEL_ORDER_REWARD = "cancel_order_reward"
    REVIEW = "review"
    PHOTO_REVIEW = "photo_review"
    REVIEW_CHAR = "review_char"
    REVIEW_DELETE = "review_delete"
    ETC = "etc"
    RECOMMEND = "recommend"
    BE_RECOMMENDED = "be_recommended"
    POINT_EXPIRE = "point_expire"

class ChangeType(Enum):
    INCREASE = "increase"
    DECREASE = "decrease"

class DivisionType(Enum):
    GRUOP = "group"
    GRADE = "grade"

class CouponType(Enum):
    TARGETED = "targeted"
    DOWN = "down"
    AUTO = "auto"
    CREATE = "create"

class Promotion:
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
        self.mcp.tool(self.get_promotion_shop_point)
        self.mcp.tool(self.get_promotion_shop_point_log)
        self.mcp.tool(self.put_promotion_shop_point_change_member)
        self.mcp.tool(self.put_promotion_shop_point_change_type)
        self.mcp.tool(self.get_shop_coupon)
        self.mcp.tool(self.get_shop_coupon_list)
        self.mcp.tool(self.post_shop_coupon_issue)
        self.mcp.tool(self.get_promotion_shop_coupon_coupon_issue)
        self.mcp.tool(self.get_promotion_shop_coupon_member_coupon_issue)
        self.mcp.tool(self.post_shop_coupon)

    async def get_promotion_shop_point(
        self, 
        session_id: str, 
        page: int,
        limit: int,
        member_uid: str = None,
        point_type: RangeType = None,
        point_value: List[int] = None,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: get_promotion_shop_point")
        """
        적립금 정보 조회
        회원의 적립금 정보를 조회합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, min:1, max: 100)
            member_uid: 회원 ID(회원 고유 식별자, 보통 이메일 사용) (없으면 전체 조회)
            point_type: 포인트 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정, 없으면 전체 조회)
            point_value: 포인트 검색 범위 값 (GTE/LTE: 하나의 포인트, BETWEEN: 두 개의 포인트, 없으면 전체 조회)
                - 예시 [1000] 또는 [1000, 2000]
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "page": page,
                "limit": limit,
                "unitCode": target_site["unit_code"]
            }

            if member_uid:
                params["memberUid"] = member_uid
            if point_type and point_value:
                params["pointType"] = point_type.value
                params["pointValue[]"] = point_value
            
            response = requests.get(
                "https://openapi.imweb.me/promotion/shop-point",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params=params
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}

    async def get_promotion_shop_point_log(
        self, 
        session_id: str, 
        page: int,
        limit: int,
        point_type: PointType = None,
        member_uid: str = None,
        admin_uid: str = None,
        order_no: int = None,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: get_promotion_shop_point_log")
        """
        적립금 이력 조회
        회원의 적립금 이력을 조회합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, min:1, max: 100)
            point_type: 포인트 지급 타입 (없으면 전체 조회)
            member_uid: 회원 ID(회원 고유 식별자, 보통 이메일 사용) (없으면 전체 조회)
            admin_uid: 관리자 ID (없으면 전체 조회)
            order_no: 주문 번호 (없으면 전체 조회)
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "page": page,
                "limit": limit,
                "unitCode": target_site["unit_code"]
            }

            if point_type:
                params["pointType"] = point_type.value
            if member_uid:
                params["memberUid"] = member_uid
            if admin_uid:
                params["adminUid"] = admin_uid
            if order_no:
                params["orderNo"] = order_no
            
            response = requests.get(
                "https://openapi.imweb.me/promotion/shop-point-log",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                params=params
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    async def put_promotion_shop_point_change_member(
        self, 
        session_id: str, 
        member_uid: str,
        change_type: ChangeType,
        point: int,
        reason: str,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: put_promotion_shop_point_change_member")
        """
        회원별 적립금 지급/차감 처리
        회원의 적립금을 지급하거나 차감합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            member_uid: 회원 ID(회원 고유 식별자, 보통 이메일 사용)
            change_type: 포인트 변경 타입 (INCREASE: 증가, DECREASE: 감소)
            point: 포인트 증감 수치
            reason: 포인트 증감 사유
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            json_data = {
                "unitCode": target_site["unit_code"],
                "changeType": change_type.value,
                "point": point,
                "reason": reason
            }
            
            response = requests.put(
                f"https://openapi.imweb.me/promotion/shop-point/change/member/{member_uid}",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json=json_data
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    async def put_promotion_shop_point_change_type(
        self, 
        session_id: str, 
        division: DivisionType,
        group_code: str,
        change_type: ChangeType,
        point: int,
        reason: str,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: put_promotion_shop_point_change_member")
        """
        회원등급/쇼핑그룹별 적립금 지급/차감 처리
        회원의 등급 또는 쇼핑그룹에 전체에 대한 적립금을 지급하거나 차감합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            division: 포인트 변경 대상 (GRUOP: 그룹, GRADE: 등급)
            group_code: 포인트 변경 대상 그룹 또는 등급 코드
            change_type: 포인트 변경 타입 (INCREASE: 증가, DECREASE: 감소)
            point: 포인트 증감 수치
            reason: 포인트 증감 사유
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            json_data = {
                "unitCode": target_site["unit_code"],
                "division": division.value,
                "groupCode": group_code,
                "changeType": change_type.value,
                "point": point,
                "reason": reason
            }
            
            response = requests.put(
                f"https://openapi.imweb.me/promotion/shop-point/change/type",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json=json_data
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_shop_coupon(
        self, 
        session_id: str, 
        shop_coupon_code: str,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: get_shop_coupon")
        """
        쿠폰 조회

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            shop_coupon_code: 쿠폰 코드
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "unitCode": target_site["unit_code"]
            }
            
            response = requests.get(
                f"https://openapi.imweb.me/promotion/shop-coupon/{shop_coupon_code}",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params=params
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_shop_coupon_list(
        self, 
        session_id: str, 
        page: int,
        limit: int,
        coupon_type: CouponType = None,
        start_date_type: RangeType = None,
        start_date_value: List[str] = None,
        end_date_type: RangeType = None,
        end_date_value: List[str] = None,
        is_unlimited_date: BoolType = None,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: get_shop_coupon_list")
        """
        쿠폰 목록 조회

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, min:1, max: 100)
            coupon_type: 쿠폰 형식 (없으면 전체 조회)
            start_date_type: 시작일 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정, 없으면 전체 조회)
            start_date_value: 시작일 검색 범위 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜, 없으면 전체 조회)
                - 예시 ['2021-01-01T00:00:00', '2021-01-31T23:59:59']
            end_date_type: 종료일 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정, 없으면 전체 조회)
            end_date_value: 종료일 검색 범위 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜, 없으면 전체 조회)
                - 예시 ['2021-01-01T00:00:00', '2021-01-31T23:59:59']
            is_unlimited_date: 무제한 날짜 여부 (Y: 무제한, N: 제한, 없으면 전체 조회)
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "page": page,
                "limit": limit,
                "unitCode": target_site["unit_code"]
            }

            if coupon_type:
                params["couponType"] = coupon_type.value
            if start_date_type and start_date_value:    
                params["startDateType"] = start_date_type.value
                params["startDateValue[]"] = start_date_value
            if end_date_type and end_date_value:
                params["endDateType"] = end_date_type.value
                params["endDateValue[]"] = end_date_value
            if is_unlimited_date:
                params["isUnlimitedDate"] = is_unlimited_date.value
            
            response = requests.get(
                "https://openapi.imweb.me/promotion/shop-coupon",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params=params
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    async def post_shop_coupon_issue(
        self, 
        session_id: str, 
        coupon_code: str,
        member_uid: str,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: post_shop_coupon_issue")
        """
        쿠폰 발급하기
        특정 회원에게 쿠폰을 발급합니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            coupon_code: 발급할 쿠폰 코드
            member_uid: 쿠폰을 받을 회원 ID(회원 고유 식별자, 보통 이메일 사용)
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            json_data = {
                "unitCode": target_site["unit_code"],
                "memberUid": member_uid
            }
            
            response = requests.post(
                f"https://openapi.imweb.me/promotion/shop-coupon/{coupon_code}/issue",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}"
                },
                json=json_data
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}

    async def get_promotion_shop_coupon_coupon_issue(
        self, 
        session_id: str, 
        shop_coupon_code: str,
        page: int,
        limit: int,
        member_uid: str = None,
        start_date_type: RangeType = None,
        start_date_value: List[str] = None,
        end_date_type: RangeType = None,
        end_date_value: List[str] = None,
        is_use: BoolType = None,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: get_promotion_shop_coupon_coupon_issue")
        """
        쿠폰별 발급 목록 조회

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, min:1, max: 100)
            shop_coupon_code: 쿠폰 코드
            member_uid: 회원 ID(회원 고유 식별자, 보통 이메일 사용)
            start_date_type: 시작일 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정, 없으면 전체 조회)
            start_date_value: 시작일 검색 범위 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜, 없으면 전체 조회)
                - 예시 ['2021-01-01T00:00:00', '2021-01-31T23:59:59']
            end_date_type: 종료일 검색 범위 (GTE: 이상, LTE: 이하, BETWEEN: 범위 지정, 없으면 전체 조회)
            end_date_value: 종료일 검색 범위 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜, 없으면 전체 조회)
                - 예시 ['2021-01-01T00:00:00', '2021-01-31T23:59:59']
            is_use: 사용 여부 (Y: 사용, N: 미사용, 없으면 전체 조회)
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "page": page,
                "limit": limit,
                "unitCode": target_site["unit_code"]
            }

            if member_uid:
                params["memberUid"] = member_uid
            if start_date_type and start_date_value:
                params["startDateType"] = start_date_type.value
                params["startDateValue[]"] = start_date_value
            if end_date_type and end_date_value:
                params["endDateType"] = end_date_type.value
                params["endDateValue[]"] = end_date_value
            if is_use:
                params["isUse"] = is_use.value
            
            response = requests.get(
                f"https://openapi.imweb.me/promotion/shop-coupon/{shop_coupon_code}/coupon-issue",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params=params
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    async def get_promotion_shop_coupon_member_coupon_issue(
        self, 
        session_id: str, 
        member_uid: str,
        page: int,
        limit: int,
        is_use: BoolType = None,
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: get_promotion_shop_coupon_member_coupon_issue")
        """
        회원별 쿠폰 발급 목록 조회
        특정 회원의 쿠폰 발급 목록을 조회합니다. 쿠폰 사용 여부로 필터링할 수 있습니다.

        Args:
            session_id: 세션 ID
            site_code: 사이트 코드 (없으면 첫 번째 사이트 사용)
            site_name: 사이트 이름 (없으면 첫 번째 사이트 사용)
            member_uid: 회원 ID(회원 고유 식별자, 보통 이메일 사용)
            page: 페이지 수 (min: 1)
            limit: 한 페이지 row 양 (없으면 기본값 10으로 설정, min:1, max: 100)
            is_use: 사용 여부 (Y: 사용, N: 미사용, 없으면 전체 조회)
        """
        try:
            target_site, error = self._get_site_and_token(session_id, site_code, site_name)
            if error:
                return error
            
            access_token = target_site["access_token"]

            params = {
                "page": page,
                "limit": limit,
                "unitCode": target_site["unit_code"]
            }

            if is_use:
                params["isUse"] = is_use.value
            
            response = requests.get(
                f"https://openapi.imweb.me/promotion/shop-coupon/member/{member_uid}/coupon-issue",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                params=params
            )

            if response.status_code != 200:
                print(f"실패: {response.status_code} - {response.text}")
                return response.json().get("error", {})
            
            data = response.json().get("data", {})
            return data
            
        except Exception as e:
            return {"error": str(e)}
    
    async def post_shop_coupon(
        self, 
        session_id: str, 
        site_code: str = None, 
        site_name: str = None
    ):
        print("##### CALL TOOL: post_shop_coupon")
        """
        쿠폰 만들기
        API에 아직 쿠폰 생성 기능이 없으므로, 쿠폰 생성 URL을 제공하여 직접 생성하도록 안내합니다.

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
                "message": "상품 등록은 저희 서비스에서 지원하지 않습니다. 직접 상품 등록 페이지에서 상품을 등록해주세요.",
                "direct_link": f"[상품 등록 페이지]({url})",
            }
            
        except Exception as e:
            return {"error": str(e)}
