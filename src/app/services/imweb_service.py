import requests
import logging
from typing import Dict, Any
from database_helper import DatabaseHelper

logger = logging.getLogger(__name__)


class ImwebService:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, db_helper: DatabaseHelper):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.db_helper = db_helper

    async def fetch_site_info_from_imweb(self, access_token: str) -> Dict[str, Any]:
        """
        아임웹 API를 통해 사이트 정보를 조회합니다.
        
        Args:
            access_token: 아임웹 API 액세스 토큰
            
        Returns:
            Dict: 사이트 정보 또는 에러 정보
        """
        try:
            response = requests.get(
                "https://openapi.imweb.me/site-info",
                headers={
                    "Authorization": f"Bearer {access_token}",
                },
                timeout=10
            )
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("statusCode") == 200:
                    return {"success": True, "data": response_data.get("data", {})}
                else:
                    return {"success": False, "error": response_data.get("error", {}).get("message", "알 수 없는 오류")}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
                
        except Exception as e:
            logger.error(f"아임웹 API 호출 실패: {e}")
            return {"success": False, "error": str(e)}

    async def update_site_names_from_imweb(self, user_id: str) -> Dict[str, Any]:
        """
        사용자의 모든 사이트 정보를 아임웹 API로 조회하여 데이터베이스의 사이트 이름을 업데이트합니다.
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Dict: 업데이트 결과
        """
        try:
            # 사용자의 모든 사이트 조회
            user_sites = await self.db_helper.get_user_sites(user_id, user_id)
            if not user_sites:
                return {"success": False, "message": "연결된 사이트가 없습니다."}
            
            update_results = []
            
            for site in user_sites:
                site_code = site.get('site_code')
                access_token = site.get('access_token')
                current_site_name = site.get('site_name')
                
                if not site_code or not access_token:
                    update_results.append({
                        "site_code": site_code,
                        "success": False,
                        "error": "사이트 코드 또는 토큰이 없습니다."
                    })
                    continue
                
                # 토큰 복호화
                decrypted_token = self.db_helper._decrypt_token(access_token)
                
                # 아임웹 API로 사이트 정보 조회
                site_info_result = await self.fetch_site_info_from_imweb(decrypted_token)
                
                if site_info_result["success"]:
                    site_data = site_info_result["data"]
                    # 아임웹에서 사이트 이름 가져오기 (siteName 또는 title 필드)
                    imweb_site_name = site_data.get('unitList')[0].get('name')
                    
                    if imweb_site_name and imweb_site_name != current_site_name:
                        # 데이터베이스 업데이트
                        update_success = await self.db_helper.update_site_name(user_id, site_code, imweb_site_name)
                        update_results.append({
                            "site_code": site_code,
                            "success": update_success,
                            "old_name": current_site_name,
                            "new_name": imweb_site_name
                        })
                    else:
                        update_results.append({
                            "site_code": site_code,
                            "success": True,
                            "message": "사이트 이름이 이미 최신상태입니다."
                        })
                else:
                    update_results.append({
                        "site_code": site_code,
                        "success": False,
                        "error": site_info_result["error"]
                    })
            
            success_count = sum(1 for result in update_results if result["success"])
            
            return {
                "success": True,
                "message": f"{len(update_results)}개 사이트 중 {success_count}개 사이트 이름 업데이트 완료",
                "results": update_results
            }
            
        except Exception as e:
            logger.error(f"사이트 이름 업데이트 실패: {e}")
            return {"success": False, "error": str(e)}

    async def refresh_imweb_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        아임웹 리프레시 토큰을 사용하여 액세스 토큰 갱신
        
        Args:
            refresh_token: 아임웹 리프레시 토큰
            
        Returns:
            Dict: 갱신 결과 (성공/실패, 새 토큰 등)
        """
        try:
            response = requests.post(
                "https://openapi.imweb.me/oauth2/token",
                data={
                    "grantType": "refresh_token",
                    "clientId": self.client_id,
                    "clientSecret": self.client_secret,
                    "refreshToken": refresh_token,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=10
            )

            # 응답 상태 코드 확인
            logger.warning(f"아임웹 토큰 갱신 요청: {response.status_code}")
            
            if response.status_code == 200:
                response_data = response.json()
                if response_data.get("statusCode") == 200:
                    token_data = response_data.get("data", {})
                    logger.info(f"\n아임웹 토큰 갱신 성공: {token_data}\n")
                    return {
                        "success": True,
                        "access_token": token_data.get("accessToken"),
                        "refresh_token": token_data.get("refreshToken")
                    }
                else:
                    return {
                        "success": False,
                        "error": response_data.get("error", {}).get("message", "토큰 갱신 실패")
                    }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}: {response.text}"
                }
                
        except Exception as e:
            logger.error(f"아임웹 토큰 갱신 실패: {e}")
            return {"success": False, "error": str(e)}

    async def get_oauth_token(self, auth_code: str) -> Dict[str, Any]:
        """
        아임웹 OAuth 인가 코드를 사용하여 액세스 토큰 발급
        
        Args:
            auth_code: OAuth 인가 코드
            
        Returns:
            Dict: 토큰 발급 결과
        """
        try:
            response = requests.post(
                "https://openapi.imweb.me/oauth2/token",
                data={
                    "grantType": "authorization_code",
                    "clientId": self.client_id,
                    "clientSecret": self.client_secret,
                    "code": auth_code,
                    "redirectUri": self.redirect_uri,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded"
                },
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"아임웹 토큰 발급 요청 실패: {response.json()}")
                return {"success": False, "error": "아임웹 토큰 발급 요청 실패"}
            
            response_data = response.json()
            if response_data.get("statusCode") != 200:
                logger.error(f"아임웹 토큰 발급 실패: {response_data}")
                return {"success": False, "error": "아임웹 토큰 발급 실패"}
            
            token_data = response_data.get("data", {})
            access_token = token_data.get("accessToken")
            refresh_token = token_data.get("refreshToken")

            if not access_token or not refresh_token:
                return {"success": False, "error": "토큰 발급에 실패했습니다."}
            
            return {
                "success": True,
                "access_token": access_token,
                "refresh_token": refresh_token
            }
            
        except Exception as e:
            logger.error(f"OAuth 토큰 발급 실패: {e}")
            return {"success": False, "error": str(e)}

    async def complete_integration(self, access_token: str) -> Dict[str, Any]:
        """
        아임웹에 연동 완료 요청
        
        Args:
            access_token: 아임웹 액세스 토큰
            
        Returns:
            Dict: 연동 완료 결과
        """
        try:
            response = requests.patch(
                "https://openapi.imweb.me/site-info/integration-complete",
                headers={
                    "Authorization": f"Bearer {access_token}"
                },
                timeout=10
            )
            
            if response.status_code != 200:
                return {"success": False, "error": f"HTTP {response.status_code}: {response.text}"}
            
            response_data = response.json()
            if response_data.get("statusCode") != 200:
                if response_data.get("statusCode") == 404:
                    return {"success": False, "error": "이미 연동된 사이트입니다.", "error_code": 404}
                return {"success": False, "error": "아임웹 연동 완료 요청 실패"}
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"아임웹 연동 완료 실패: {e}")
            return {"success": False, "error": str(e)}