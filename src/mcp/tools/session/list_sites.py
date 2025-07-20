import requests
from typing import Dict, Any
from .helper import get_session_data

async def list_sites(session_id: str) -> Dict[str, Any]:
    try:
        session_data = get_session_data(session_id)
        
        if not session_data:
            return {"error": "세션이 존재하지 않습니다."}
        
        sites = session_data.get("sites", [])

        for site in sites:
            if "access_token" in site:
                response = requests.get("https://openapi.imweb.me/site-info",
                    headers={
                        "Authorization": f"Bearer {site['access_token']}",
                    }
                )
                if response.status_code != 200:
                    print(f"사이트 호출 실패: {response.status_code} - {response.text}")
                    return {"error": f"사이트 호출 실패: {response.status_code}"}
                site_info = response.json().get("data", {})
                site["unit_code"] = site_info.get("unitList", [{}])[0].get("unitCode", "")
        
        site_list = [{"site_name": site["site_name"], "site_code": site["site_code"], "unit_code": site["unit_code"]} for site in sites]

        return {"sites": site_list, "total": len(site_list)}
        
    except Exception as e:
        return {"error": str(e)}