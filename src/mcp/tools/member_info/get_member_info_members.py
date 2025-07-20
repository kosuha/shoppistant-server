import requests
from typing import List
from ..session import get_session_data

async def get_member_info_members(
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
    
    try:
        session_data = get_session_data(session_id)
        
        if not session_data:
            return {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])
        if not sites:
            return {"error": "세션에 사이트 정보가 없습니다."}
        
        target_site = None
        if site_code or site_name:
            target_site = next((site for site in sites if site["site_code"] == site_code or site["site_name"] == site_name), None)
            if not target_site:
                return {"error": f"사이트 코드 '{site_code}'를 찾을 수 없습니다."}
        else:
            target_site = sites[0]
        
        access_token = target_site["access_token"]

        response = requests.get(
            "https://openapi.imweb.me/member-info/members",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
            params={
                "page": page,
                "limit": limit,
                "joinTimeRangeType": join_time_range_type,
                "joinTimeRangeValue": join_time_range_value,
                "lastJoinTimeRangeType": last_join_time_range_type,
                "lastJoinTimeRangeValue": last_join_time_range_value,
                "unitCode": target_site["unit_code"],
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