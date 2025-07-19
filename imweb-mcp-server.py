from fastmcp import FastMCP, Context
from fastmcp.server.auth import BearerAuthProvider
import requests
import jwt
import os
from typing import Dict, Any, List
from datetime import datetime
from enum import Enum

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
async def set_session_token(session_id: str, user_id: str, sites: list) -> str:
    print("##### CALL TOOL: set_session_token")
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
    return f"세션 {session_id}에 {len(sites)}개 사이트 토큰 설정됨"

@mcp.tool
async def list_sites(session_id: str) -> Dict[str, Any]:
    print("##### CALL TOOL: list_sites")
    """
    사용자의 연동된 모든 사이트 목록을 조회합니다.
    
    Args:
        session_id: 세션 ID
    """
    try:
        global _session_tokens
        session_data = _session_tokens.get(session_id)
        
        if not session_data:
            return {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        
        # 토큰 정보는 제거하고 사이트 코드만 반환
        site_list = [{"site_name": site["site_name"], "site_code": site["site_code"]} for site in sites]

        return {"sites": site_list, "total": len(site_list)}
        
    except Exception as e:
        return {"error": str(e)}

# Site-Info

@mcp.tool
async def get_site_info(session_id: str, site_name: str = None, site_code: str = None) -> Dict[str, Any]:
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
    try:
        global _session_tokens
        session_data = _session_tokens.get(session_id)
        
        if not session_data:
            return {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        if not sites:
            return {"error": "세션에 사이트 정보가 없습니다."}
        
        # 특정 사이트 코드가 지정되면 해당 사이트 찾기, 없으면 첫 번째 사이트 사용
        target_site = None
        if site_code:
            target_site = next((site for site in sites if site["site_code"] == site_code), None)
            if not target_site:
                return {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
        else:
            target_site = sites[0]  # 첫 번째 사이트 사용
        
        access_token = target_site["access_token"]

        response = requests.get("https://openapi.imweb.me/site-info",
            headers={
                "Authorization": f"Bearer {access_token}",
            }
        )
        if response.status_code != 200:
            print(f"사이트 호출 실패: {response.status_code} - {response.text}")
            return {"error": f"사이트 호출 실패: {response.status_code}"}
        
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
            return {"error": f"사이트 단위 정보 조회 실패: {response.status_code}"}
        
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

# Member-Info
class RANGE_TYPE(Enum):
    GTE = "GTE"
    LTE = "LTE"
    BETWEEN = "BETWEEN"

class AGREE_TYPE(Enum):
    YES = "Y"
    NO = "N"

@mcp.tool
async def get_member_info_members(
    session_id: str, 
    page: int, 
    unit_code: str,
    site_code: str,
    site_name: str | None = None,
    limit: int = 10, 
    join_time_range_type: RANGE_TYPE | None = None,
    join_time_range_value: List[str] | None = None,
    last_join_time_range_type: RANGE_TYPE | None = None,
    last_join_time_range_value: List[str] | None = None,
    sms_agree: AGREE_TYPE | None = None,
    email_agree: AGREE_TYPE | None = None,
    third_party_agree: AGREE_TYPE | None = None,
    call_num: str | None = None,
    ):
    print("##### CALL TOOL: get_member_info_members")
    """
    사이트 유닛 단위의 회원 정보 목록을 페이지로 조회합니다.
    유닛코드를 모르는 경우 get_site_info를 호출해 사이트 코드와 유닛코드를 조회할 수 있습니다.
    1페이지에 최대 100개 회원 정보 조회 가능하며, 기본값은 10개입니다.
    사용자에게 필요한 회원 정보의 갯수를 묻고, 필요한 만큼 페이지를 지정하여 조회합니다.
    
    Args:
        session_id: 
            세션 ID
        
        site_code:
            Type: string
            사이트 코드
        
        page:
            Type: number
            min: 1
            페이지 수
        
        unitCode:
            Type: string
            사이트 유닛 코드

        limit:
            Type: number
            min: 1
            max: 100
            default: 10
            한 페이지 row 양

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
    try:
        global _session_tokens
        session_data = _session_tokens.get(session_id)
        
        if not session_data:
            return {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        if not sites:
            return {"error": "세션에 사이트 정보가 없습니다."}
        
        # 특정 사이트가 지정
        target_site = None
        if site_code or site_name:
            target_site = next((site for site in sites if site["site_code"] == site_code or site["site_name"] == site_name), None)
            if not target_site:
                return {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
        else:
            target_site = sites[0]  # 첫 번째 사이트 사용
        
        access_token = target_site["access_token"]

        response = requests.get(
            "https://openapi.imweb.me/member-info/members",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            params={
                "page": "1",
                "limit": "10",
                "joinTimeRangeType": join_time_range_type,
                "joinTimeRangeValue": join_time_range_value,
                "lastJoinTimeRangeType": last_join_time_range_type,
                "lastJoinTimeRangeValue": last_join_time_range_value,
                "unitCode": unit_code,
                "smsAgree": sms_agree,
                "emailAgree": email_agree,
                "thirdPartyAgree": third_party_agree,
                "callNum": call_num
            }
        )
        if response.status_code != 200:
            print(f"회원 정보 조회 실패: {response.status_code} - {response.text}")
            return {"error": f"회원 정보 조회 실패: {response.status_code}"}
        response_data = response.json()
        data = response_data.get("data", {})
        return data
        
    except Exception as e:
        return {"error": str(e)}


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=8001,
        path="/",
        log_level="debug",
    )