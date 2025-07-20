from fastmcp import FastMCP
from typing import Dict, Any, List

from tools.session import set_session_token, list_sites
from tools.site_info import get_site_info  
from tools.member_info import (
    get_member_info_members, 
    get_member_info_members_product_cart,
    get_member_info_members_product_wish_list,
    get_member_info_member,
    get_member_info_groups,
    get_member_info_groups_members,
    get_member_info_grades
)

mcp = FastMCP(name="imweb-mcp-server")

@mcp.tool
async def set_session_token_tool(session_id: str, user_id: str, sites: list) -> str:
    print("##### CALL TOOL: set_session_token")
    """
    세션에 여러 사이트의 토큰을 설정합니다.
    
    Args:
        session_id: 세션 ID
        user_id: 사용자 ID
        sites: 사이트 정보 리스트 [{"site_name": "...", "site_code": "...", "access_token": "..."}, ...]
    """
    return await set_session_token(session_id, user_id, sites)

@mcp.tool
async def list_sites_tool(session_id: str) -> Dict[str, Any]:
    print("##### CALL TOOL: list_sites")
    """
    사용자의 연동된 모든 사이트 목록을 조회합니다.
    
    Args:
        session_id: 세션 ID
    """
    return await list_sites(session_id)

@mcp.tool
async def get_site_info_tool(session_id: str, site_name: str = None, site_code: str = None) -> Dict[str, Any]:
    print("##### CALL TOOL: get_site_info")
    """
    사이트 이름 또는 사이트 코드로 사이트 정보를 조회합니다.

    사이트 정보:
        siteCode: 사이트 코드
        unitCode: 사이트 유닛 코드
        name: 사이트 이름
        companyName: 호스팅 업체 이름
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
    return await get_site_info(session_id, site_name, site_code)

@mcp.tool
async def get_member_info_members_tool(
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
    print("##### CALL TOOL: get_member_info_members")
    """
    사이트 유닛 단위의 회원 정보 목록을 페이지로 조회합니다.
    1페이지에 최대 100개 회원 정보 조회 가능하며, 기본값은 10개입니다.
    사용자에게 필요한 회원 정보의 갯수를 묻고, 필요한 만큼 페이지를 지정하여 조회합니다.
    
    Args:
        session_id: 
            세션 ID
        
        site_code:
            Type: string
            사이트 코드 (없으면 첫 번째 사이트 사용)
        
        site_name:
            Type: string
            사이트 이름 (없으면 첫 번째 사이트 사용)

        page:
            Type: number
            min: 1
            페이지 수

        limit:
            Type: number
            min: 1
            max: 100
            한 페이지 row 양 (없으면 기본값 10으로 설정)

        join_time_range_type:
            Type: enum
            가입 시간 검색 범위
                GTE: 이상
                LTE: 이하
                BETWEEN: 범위 지정

        join_time_range_value
            Type: array string[]
            Format: date-time
            가입 시간 검색 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜)
                - GTE/LTE: ['2021-01-01T00:00:00.000Z']
                - BETWEEN: ['2021-01-01T00:00:00.000Z', '2021-01-31T23:59:59.000Z']

        last_login_time_range_type:
            Type: enum
            최근 로그인 시간 검색 범위
                GTE: 이상
                LTE: 이하
                BETWEEN: 범위 지정

        last_login_time_range_value:
            Type: array string[]
            Format:date-time
            최근 로그인 시간 검색 값 (GTE/LTE: 하나의 날짜, BETWEEN: 두 개의 날짜)
                - GTE/LTE: ['2021-01-01T00:00:00.000Z']
                - BETWEEN: ['2021-01-01T00:00:00.000Z', '2021-01-31T23:59:59.000Z']

        sms_agree
            Type: string enum
            sms 수신 여부
                Y : 수신
                N : 비수신

        email_agree
            Type: string enum
            email 수신 여부
                Y : 수신
                N : 비수신

        third_party_agree
            Type:string enum
            개인정보 제3자 제공 여부
                Y : 동의
                N : 비동의

        call_num:
            Type: string
            회원 전화번호
    """
    return await get_member_info_members(
        session_id, page, site_code, site_name, limit,
        join_time_range_type, join_time_range_value,
        last_join_time_range_type, last_join_time_range_value,
        sms_agree, email_agree, third_party_agree, call_num
    )

@mcp.tool
async def get_member_info_members_product_wish_list_tool(
    session_id: str, 
    page: int, 
    prodNo: int,
    limit: int = 10, 
    site_code: str | None = None,
    site_name: str | None = None
    ):
    print("##### CALL TOOL: member_info_members_product_wish_list")
    """
    위시리스트 상품 별 회원 목록 조회
    특정 상품을 위시리스트에 등록한 회원 목록을 조회합니다.

    Args:
        session_id: 
            세션 ID

        site_code:
            Type: string
            사이트 코드 (없으면 첫 번째 사이트 사용)
        
        site_name:
            Type: string
            사이트 이름 (없으면 첫 번째 사이트 사용)
        
        page:
            Type: number
            min: 1
            페이지 수
        
        limit:
            Type: number
            min: 1
            max: 100
            한 페이지 row 양 (없으면 기본값 10으로 설정)

        prodNo:
            Type: number
            상품 번호
    """
    return await get_member_info_members_product_wish_list(
        session_id, page, prodNo, limit, site_code, site_name
    )

@mcp.tool
async def get_member_info_members_product_cart_tool(
    session_id: str, 
    page: int, 
    prodNo: int,
    limit: int = 10, 
    site_code: str | None = None,
    site_name: str | None = None
    ):
    print("##### CALL TOOL: member_info_members_product_cart")
    """
    장바구니 상품 별 회원 목록 조회
    특정 상품을 장바구니에 담은 회원 목록을 조회합니다.

    Args:
        session_id: 
            세션 ID

        site_code:
            Type: string
            사이트 코드 (없으면 첫 번째 사이트 사용)
        
        site_name:
            Type: string
            사이트 이름 (없으면 첫 번째 사이트 사용)
        
        page:
            Type: number
            min: 1
            페이지 수
        
        limit:
            Type: number
            min: 1
            max: 100
            한 페이지 row 양 (없으면 기본값 10으로 설정)

        prodNo:
            Type: number
            상품 번호
    """
    return await get_member_info_members_product_cart(
        session_id, page, prodNo, limit, site_code, site_name
    )

@mcp.tool
async def get_member_info_member_tool(
    session_id: str, 
    member_uid: str,
    site_code: str | None = None,
    site_name: str | None = None
    ):
    print("##### CALL TOOL: member_info_member")
    """
    회원 조회
    특정 회원의 ID를 통해 상세 정보를 조회합니다.

    Args:
        session_id: 
            세션 ID

        site_code:
            Type: string
            사이트 코드 (없으면 첫 번째 사이트 사용)
        
        site_name:
            Type: string
            사이트 이름 (없으면 첫 번째 사이트 사용)
        
        member_uid:
            Type: string
            회원 ID (회원 고유 식별자)
    """
    return await get_member_info_member(session_id, member_uid, site_code, site_name)

@mcp.tool
async def get_member_info_groups_tool(
    session_id: str, 
    page: int, 
    limit: int = 10,
    site_code: str | None = None,
    site_name: str | None = None
    ):
    print("##### CALL TOOL: member_info_groups")
    """
    회원 그룹 목록 조회
    특정 사이트의 회원 그룹 목록을 페이지 단위로 조회합니다.

    Args:
        session_id: 
            세션 ID

        page:
            Type: number
            min: 1
            페이지 수
        
        limit:
            Type: number
            min: 1
            max: 100
            한 페이지 row 양 (없으면 기본값 10으로 설정)

        site_code:
            Type: string
            사이트 코드 (없으면 첫 번째 사이트 사용)
        
        site_name:
            Type: string
            사이트 이름 (없으면 첫 번째 사이트 사용)
    """
    return await get_member_info_groups(session_id, page, limit, site_code, site_name)

@mcp.tool
async def get_member_info_groups_members_tool(
    session_id: str, 
    page: int, 
    member_group_code: str,
    limit: int = 10,
    site_code: str | None = None,
    site_name: str | None = None
    ):
    print("##### CALL TOOL: get_member_info_groups_members")
    """
    회원 그룹별 회원 목록 조회
    회원그룹 아이디를 통해 회원 그룹의 회원 목록을 페이지 단위로 조회합니다.

    Args:
        session_id: 
            세션 ID

        page:
            Type: number
            min: 1
            페이지 수
        
        member_group_code:
            Type: string
            회원 그룹 코드
        
        limit:
            Type: number
            min: 1
            max: 100
            한 페이지 row 양 (없으면 기본값 10으로 설정)

        site_code:
            Type: string
            사이트 코드 (없으면 첫 번째 사이트 사용)
        
        site_name:
            Type: string
            사이트 이름 (없으면 첫 번째 사이트 사용)
    """
    return await get_member_info_groups_members(session_id, page, member_group_code, limit, site_code, site_name)

@mcp.tool
async def get_member_info_grades_tool(
    session_id: str, 
    page: int, 
    limit: int = 10,
    site_code: str | None = None,
    site_name: str | None = None
    ):
    print("##### CALL TOOL: member_info_grades_tool")
    """
    회원 쇼핑 등급 목록 조회
    특정 사이트의 회원 쇼핑 등급 목록을 페이지 단위로 조회합니다.

    Args:
        session_id: 
            세션 ID

        page:
            Type: number
            min: 1
            페이지 수
        
        limit:
            Type: number
            min: 1
            max: 100
            한 페이지 row 양 (없으면 기본값 10으로 설정)

        site_code:
            Type: string
            사이트 코드 (없으면 첫 번째 사이트 사용)
        
        site_name:
            Type: string
            사이트 이름 (없으면 첫 번째 사이트 사용)
    """
    return await get_member_info_grades(session_id, page, limit, site_code, site_name)

if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8001,
        path="/",
        log_level="debug",
    )