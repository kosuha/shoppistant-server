import requests
from typing import Dict, Any
from ..session import get_session_data

async def get_site_info(session_id: str, site_name: str = None, site_code: str = None) -> Dict[str, Any]:
    try:
        session_data = get_session_data(session_id)
        
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