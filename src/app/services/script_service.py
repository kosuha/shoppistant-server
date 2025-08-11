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
            self.logger.debug(f"사이트 {site_code}의 활성 스크립트 발견")
            
            await self.log_user_action(user_id, "script_viewed", {
                "site_code": site_code,
                "script_version": script_data.get('version')
            })
            
            # CSS/JS 분리 응답 (하위 호환성을 위해 script도 포함)
            return {
                "css_content": script_data.get('css_content', ''),
                "js_content": script_data.get('script_content', ''),  # JS는 script_content 컬럼 사용
                "script": script_data.get('script_content', ''),  # 하위 호환성
                "version": script_data.get('version', 1),
                "last_updated": script_data.get('updated_at', script_data.get('created_at'))
            }
        else:
            self.logger.debug(f"사이트 {site_code}의 활성 스크립트가 없음")
            return {
                "css_content": '',
                "js_content": '',  # JS는 script_content 컬럼 사용
                "script": '',  # 하위 호환성
                "version": 0,
                "last_updated": None
            }

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
        
        # 도메인 정보 확인
        domain = site.get('primary_domain') or site.get('domain')
        if not domain:
            raise BusinessException("사이트의 도메인 정보가 설정되지 않았습니다", "DOMAIN_NOT_SET", 400)
        
        # CSS/JS 스크립트 데이터 처리
        css_content = scripts_data.get('css_content', '').strip()
        js_content = scripts_data.get('js_content', '').strip()
        
        if not css_content and not js_content:
            # 빈 스크립트 - 삭제 처리
            return await self._handle_script_deletion(user_id, site_code)
        else:
            # 스크립트 배포 처리 (CSS/JS 분리)
            return await self._handle_script_deployment_separated(user_id, site_code, css_content, js_content)
    
    async def _handle_script_deletion(self, user_id: str, site_code: str) -> Dict[str, Any]:
        """스크립트 삭제 처리"""
        # DB에서 기존 스크립트 삭제 (비활성화)
        await self.db_helper.delete_site_script(user_id, site_code)
        
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
    
    async def _handle_script_deployment_separated(self, user_id: str, site_code: str, css_content: str, js_content: str) -> Dict[str, Any]:
        """CSS/JS 분리 스크립트 배포 처리"""
        # CSS 검증 (기본 크기 검증)
        if css_content and len(css_content.encode('utf-8')) > 50 * 1024:  # 50KB 제한
            raise ValidationException("CSS 크기가 50KB를 초과합니다.")
            
        # JS 검증
        if js_content:
            validation_result = self.validate_script_content(js_content)
            if not validation_result.is_valid:
                error_messages = [err.message for err in validation_result.errors]
                raise ValidationException(f"JavaScript 검증 실패: {'; '.join(error_messages)}")
        
        # 1단계: DB에 CSS/JS 분리 저장
        script_record = await self.db_helper.update_site_script_separated(user_id, site_code, css_content, js_content)
        if not script_record:
            raise BusinessException("스크립트 데이터베이스 저장 실패", "DB_SAVE_FAILED", 500)
        
        return {
            "site_code": site_code,
            "message": "CSS와 JavaScript가 분리되어 데이터베이스에 저장되고 배포되었습니다."
        }

    async def _handle_script_deployment(self, user_id: str, site_code: str, script_content: str) -> Dict[str, Any]:
        """기존 통합 스크립트 배포 처리 (하위 호환성)"""
        # 스크립트 검증
        validation_result = self.validate_script_content(script_content)
        if not validation_result.is_valid:
            error_messages = [err.message for err in validation_result.errors]
            raise ValidationException(f"스크립트 검증 실패: {'; '.join(error_messages)}")
        
        # 1단계: DB에 스크립트 저장
        script_record = await self.db_helper.update_site_script(user_id, site_code, script_content)
        if not script_record:
            raise BusinessException("스크립트 데이터베이스 저장 실패", "DB_SAVE_FAILED", 500)
        
        return {
            "site_code": site_code,
            "message": "스크립트가 데이터베이스에 저장되고 모듈 형태로 배포되었습니다."
        }
