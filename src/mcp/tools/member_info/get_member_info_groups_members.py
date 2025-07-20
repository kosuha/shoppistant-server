import requests
from ..session import get_session_data

async def get_member_info_groups_members(
    session_id: str, 
    page: int, 
    member_group_code: str,
    limit: int = 10,
    site_code: str | None = None,
    site_name: str | None = None
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
            f"https://openapi.imweb.me/member-info/groups/{member_group_code}/members",
            headers={
                "Authorization": f"Bearer {access_token}"
            },
            params={
                "page": page,
                "limit": limit,
                "unitCode": target_site["unit_code"]
            }
        )
        if response.status_code != 200:
            return {"error": f"회원 그룹 목록 조회 실패: {response}"}
        
        response_data = response.json()
        data = response_data.get("data", {})
        return data
    
    except Exception as e:
        return {"error": str(e)}