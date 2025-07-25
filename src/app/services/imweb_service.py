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

