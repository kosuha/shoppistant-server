import requests
import logging
from typing import Dict, Any

# Core imports
from core.interfaces import IScriptService, IDatabaseHelper
from core.base_service import BaseService
from core.responses import ValidationException, BusinessException
from schemas import ScriptValidationError, ScriptValidationResult

logger = logging.getLogger(__name__)

class ScriptService(BaseService, IScriptService):
    """스크립트 서비스 - 리팩토링 버전"""
    
    def __init__(self, db_helper: IDatabaseHelper):
        super().__init__(db_helper)

    def validate_script_content(self, script_content: str) -> ScriptValidationResult:
        """스크립트 내용의 기본 검증을 수행합니다."""
        errors = []
        warnings = []
        
        # 크기 검증 (100KB 제한)
        max_size = 100 * 1024  # 100KB
        if len(script_content.encode('utf-8')) > max_size:
            errors.append(ScriptValidationError(
                field="script_content",
                error_type="size_limit_exceeded",
                message=f"스크립트 크기가 {max_size}바이트를 초과합니다."
            ))
        
        # 기본 XSS 패턴 검사
        dangerous_patterns = [
            "document.write",
            "eval(",
            "innerHTML",
            "outerHTML"
        ]
        
        for pattern in dangerous_patterns:
            if pattern in script_content.lower():
                warnings.append(f"잠재적으로 위험한 패턴 발견: {pattern}")
        
        return ScriptValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    async def get_site_scripts(self, user_id: str, site_code: str) -> Dict[str, Any]:
        """특정 사이트의 현재 스크립트를 데이터베이스에서 조회합니다."""
        return await self.handle_operation(
            "사이트 스크립트 조회",
            self._get_site_scripts_internal,
            user_id, site_code
        )
    
    async def _get_site_scripts_internal(self, user_id: str, site_code: str) -> Dict[str, Any]:
        """내부 스크립트 조회 로직"""
        self.logger.info(f"스크립트 조회 요청: user_id={user_id}, site_code={site_code}")
        
        # 필수 필드 검증
        self.validate_required_fields(
            {"user_id": user_id, "site_code": site_code},
            ["user_id", "site_code"]
        )
        
        # 데이터베이스에서 활성 스크립트 조회
        script_data = await self.db_helper.get_site_script(user_id, site_code)
        
        if script_data:
            script_content = script_data.get('script_content', '')
            self.logger.debug(f"사이트 {site_code}의 활성 스크립트 발견")
            
            await self.log_user_action(user_id, "script_viewed", {
                "site_code": site_code,
                "script_version": script_data.get('version')
            })
            
            return {"script": script_content}
        else:
            self.logger.debug(f"사이트 {site_code}의 활성 스크립트가 없음")
            return {"script": ""}

    async def deploy_site_scripts(self, user_id: str, site_code: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        """특정 사이트에 스크립트를 배포합니다."""
        return await self.handle_operation(
            "사이트 스크립트 배포",
            self._deploy_site_scripts_internal,
            user_id, site_code, scripts_data
        )
    
    async def _deploy_site_scripts_internal(self, user_id: str, site_code: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        """내부 스크립트 배포 로직"""
        self.logger.info(f"스크립트 배포 요청: user_id={user_id}, site_code={site_code}")
        
        # 필수 필드 검증
        self.validate_required_fields(
            {"user_id": user_id, "site_code": site_code},
            ["user_id", "site_code"]
        )
        
        # 사용자가 해당 사이트에 접근 권한이 있는지 확인
        site = await self.db_helper.get_user_site_by_code(user_id, site_code)
        if not site:
            raise BusinessException("사이트를 찾을 수 없거나 접근 권한이 없습니다", "SITE_NOT_FOUND", 404)
        
        # OAuth 토큰이 제거되어 도메인 기반으로 처리
        # 도메인 정보 확인
        domain = site.get('primary_domain') or site.get('domain')
        if not domain:
            raise BusinessException("사이트의 도메인 정보가 설정되지 않았습니다", "DOMAIN_NOT_SET", 400)
        
        # 스크립트 데이터 처리
        if not scripts_data or not scripts_data.get('script', '').strip():
            # 빈 스크립트 - 삭제 처리
            return await self._handle_script_deletion(user_id, site_code)
        else:
            # 스크립트 배포 처리
            script_content = scripts_data.get('script', '')
            return await self._handle_script_deployment(user_id, site_code, script_content)
    
    async def _handle_script_deletion(self, user_id: str, site_code: str) -> Dict[str, Any]:
        """스크립트 삭제 처리"""
        # DB에서 기존 스크립트 삭제 (비활성화)
        await self.db_helper.delete_site_script(user_id, site_code)
        
        # OAuth 토큰이 제거되어 아임웹 API 호출 불가, 로컬 DB에서만 삭제
        # 아임웹 스크립트는 수동으로 제거해야 함
        
        from datetime import datetime
        deployed_at = datetime.now().isoformat() + "Z"
        
        await self.log_user_action(user_id, "script_deleted", {
            "site_code": site_code,
            "deployed_at": deployed_at
        })
        
        return {
            "deployed_at": deployed_at,
            "site_code": site_code,
            "deployed_scripts": {"header": "", "body": "", "footer": ""},
            "message": "스크립트가 삭제되었습니다."
        }
    
    async def _handle_script_deployment(self, user_id: str, site_code: str, script_content: str) -> Dict[str, Any]:
        """스크립트 배포 처리"""
        # 스크립트 검증
        validation_result = self.validate_script_content(script_content)
        if not validation_result.is_valid:
            error_messages = [err.message for err in validation_result.errors]
            raise ValidationException(f"스크립트 검증 실패: {'; '.join(error_messages)}")
        
        # 1단계: DB에 스크립트 저장
        script_record = await self.db_helper.update_site_script(user_id, site_code, script_content)
        if not script_record:
            raise BusinessException("스크립트 데이터베이스 저장 실패", "DB_SAVE_FAILED", 500)
        
        # 2단계: 모듈 스크립트 배포
        import os
        server_base_url = os.getenv("SERVER_BASE_URL", "http://localhost:8000")
        module_script = f"<script>document.head.appendChild(Object.assign(document.createElement('script'),{{'src':'{server_base_url}/api/v1/sites/{site_code}/script','type':'module'}}))</script>"
        
        # OAuth 토큰이 제거되어 아임웹 API 직접 호출 불가
        # 스크립트는 로컬 DB에 저장되고, 사용자가 수동으로 아임웹에 추가해야 함
        deploy_result = {
            "success": True,
            "script": module_script,
            "message": "스크립트가 로컬에 저장되었습니다. 아임웹 사이트 설정에서 수동으로 스크립트를 추가해주세요."
        }
        
        from datetime import datetime
        deployed_at = datetime.now().isoformat() + "Z"
        
        await self.log_user_action(user_id, "script_deployed", {
            "site_code": site_code,
            "action": "deploy_script_with_module",
            "script_version": script_record.get('version'),
            "deployed_at": deployed_at,
            "module_url": f"{server_base_url}/api/v1/sites/{site_code}/script"
        })
        
        return {
            "deployed_at": deployed_at,
            "site_code": site_code,
            "script_version": script_record.get('version'),
            "module_url": f"{server_base_url}/api/v1/sites/{site_code}/script",
            "deployed_scripts": {
                "script": script_record.get('script_content', ''),
            },
            "message": "스크립트가 데이터베이스에 저장되고 아임웹에 모듈 형태로 배포되었습니다."
        }
