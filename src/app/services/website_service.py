import logging
import uuid
from datetime import datetime
from typing import Dict, Any
from database_helper import DatabaseHelper

logger = logging.getLogger(__name__)

class WebsiteService:
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str, db_helper: DatabaseHelper):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.db_helper = db_helper

    async def add_website(self, user_id: str, domain: str) -> Dict[str, Any]:
        """
        새로운 웹사이트 추가 - 도메인 기반 단순 연동
        
        Args:
            user_id: 사용자 ID
            domain: 웹사이트 도메인
            
        Returns:
            Dict: 사이트 코드와 연동 스크립트를 포함한 결과
        """
        try:
            # 도메인 정규화 (프로토콜, 경로, 파라미터, 앵커 모두 제거)
            normalized_domain = domain.replace("https://", "").replace("http://", "")
            # URL 경로, 파라미터, 앵커 제거 (첫 번째 /, ?, # 이후 모든 내용 제거)
            if "/" in normalized_domain:
                normalized_domain = normalized_domain.split("/")[0]
            if "?" in normalized_domain:
                normalized_domain = normalized_domain.split("?")[0]
            if "#" in normalized_domain:
                normalized_domain = normalized_domain.split("#")[0]
            normalized_domain = normalized_domain.strip()
            
            # 사이트 코드 생성 (ws + 날짜시분초 + UUID)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            uuid_part = str(uuid.uuid4())[:8]
            site_code = f"ws{timestamp}{uuid_part}"
            
            # 연동 스크립트 생성
            import os
            server_base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")
            module_script = f"<script>document.head.appendChild(Object.assign(document.createElement('script'),{{'src':'{server_base_url}/api/v1/sites/{site_code}/script','type':'module'}}))</script>"
            
            # 데이터베이스에 사이트 정보 저장
            site_data = await self.db_helper.create_user_site(
                user_id=user_id,
                site_code=site_code,
                site_name=normalized_domain,
                domain=normalized_domain
            )
            
            if not site_data:
                return {"success": False, "error": "사이트 생성에 실패했습니다."}
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='website_added',
                event_data={
                    'site_code': site_code,
                    'domain': normalized_domain,
                    'method': 'domain_based'
                }
            )
            
            return {
                "success": True,
                "data": {
                    "site_code": site_code,
                    "script": module_script,
                    "domain": normalized_domain
                }
            }
            
        except Exception as e:
            logger.error(f"웹사이트 추가 실패: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_sites(self, user_id: str) -> Dict[str, Any]:
        """
        사용자의 사이트 목록 조회
        
        Args:
            user_id: 사용자 ID
            
        Returns:
            Dict: 사이트 목록을 포함한 결과
        """
        try:
            sites = await self.db_helper.get_user_sites(user_id, user_id)
            
            # 사이트 정보 정리 (domain 필드 추가, 민감한 정보 제거)
            safe_sites = []
            for site in sites:
                safe_site = {
                    "id": site.get("id"),
                    "site_code": site.get("site_code"),
                    "site_name": site.get("site_name"),
                    "domain": site.get("primary_domain"),
                    "created_at": site.get("created_at"),
                    "updated_at": site.get("updated_at")
                }
                safe_sites.append(safe_site)
            
            return {
                "success": True,
                "data": {"sites": safe_sites}
            }
            
        except Exception as e:
            logger.error(f"사이트 목록 조회 실패: {e}")
            return {"success": False, "error": str(e)}
    
    async def delete_site(self, user_id: str, site_id: str) -> Dict[str, Any]:
        """
        사이트 삭제
        
        Args:
            user_id: 사용자 ID
            site_id: 삭제할 사이트 ID
            
        Returns:
            Dict: 삭제 결과
        """
        try:
            success = await self.db_helper.delete_site(user_id, site_id)
            
            if not success:
                return {"success": False, "error": "사이트 삭제에 실패했습니다."}
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='website_deleted',
                event_data={
                    'site_id': site_id
                }
            )
            
            return {"success": True}
            
        except Exception as e:
            logger.error(f"사이트 삭제 실패: {e}")
            return {"success": False, "error": str(e)}
    
    async def update_site_name(self, user_id: str, site_id: str, site_name: str) -> Dict[str, Any]:
        """
        사이트 이름 업데이트
        
        Args:
            user_id: 사용자 ID
            site_id: 사이트 ID
            site_name: 새로운 사이트 이름
            
        Returns:
            Dict: 업데이트된 사이트 정보
        """
        try:
            # 먼저 사이트 정보를 가져와서 site_code 확인
            sites = await self.db_helper.get_user_sites(user_id, user_id)
            target_site = None
            for site in sites:
                if site.get("id") == site_id:
                    target_site = site
                    break
            
            if not target_site:
                return {"success": False, "error": "사이트를 찾을 수 없습니다."}
            
            site_code = target_site.get("site_code")
            success = await self.db_helper.update_site_name(user_id, site_code, site_name)
            
            if not success:
                return {"success": False, "error": "사이트 이름 업데이트에 실패했습니다."}
            
            # 업데이트된 사이트 정보 조회
            updated_site = await self.db_helper.get_user_site_by_code(user_id, site_code)
            safe_site = {
                "id": updated_site.get("id"),
                "site_code": updated_site.get("site_code"),
                "site_name": updated_site.get("site_name"),
                "domain": updated_site.get("primary_domain"),
                "created_at": updated_site.get("created_at"),
                "updated_at": updated_site.get("updated_at")
            }
            
            # 로그 기록
            await self.db_helper.log_system_event(
                user_id=user_id,
                event_type='website_name_updated',
                event_data={
                    'site_id': site_id,
                    'old_name': target_site.get("site_name"),
                    'new_name': site_name
                }
            )
            
            return {
                "success": True,
                "data": {"site": safe_site}
            }
            
        except Exception as e:
            logger.error(f"사이트 이름 업데이트 실패: {e}")
            return {"success": False, "error": str(e)}

