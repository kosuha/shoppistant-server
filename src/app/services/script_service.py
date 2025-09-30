import logging
from typing import Dict, Any

try:
    from app.utils.code_bundle import build_active_output, merge_language_sources, build_language_source
except ModuleNotFoundError:
    from utils.code_bundle import build_active_output, merge_language_sources, build_language_source

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

            deployed_script = script_data.get('script_content') or ''
            deployed_css = script_data.get('css_content') or ''
            draft_script = script_data.get('draft_script_content') or deployed_script
            draft_css = script_data.get('draft_css_content') or deployed_css

            if '/*#FILE' not in draft_script and '/*#FILE' not in draft_css:
                legacy_files = [{
                    'id': 'legacy',
                    'name': 'main',
                    'active': True,
                    'order': 1,
                    'javascript': draft_script or deployed_script,
                    'css': draft_css or deployed_css,
                }]
                draft_script = build_language_source(legacy_files, 'javascript')
                draft_css = build_language_source(legacy_files, 'css')

            files = merge_language_sources(draft_script, draft_css)

            return {
                "script_content": deployed_script,
                "css_content": deployed_css,
                "draft_script_content": draft_script,
                "draft_css_content": draft_css,
                "draft_updated_at": script_data.get('draft_updated_at'),
                "version": script_data.get('version', 1),
                "last_updated": script_data.get('updated_at', script_data.get('created_at'))
            }
        else:
            self.logger.debug(f"사이트 {site_code}의 활성 스크립트가 없음")
            return {
                "script_content": '',
                "css_content": '',
                "draft_script_content": '',
                "draft_css_content": '',
                "draft_updated_at": None,
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
        
        current_script = await self.db_helper.get_site_script(user_id, site_code)
        if not current_script:
            raise BusinessException("저장된 스크립트가 없습니다", "SCRIPT_NOT_FOUND", 404)

        draft_script = scripts_data.get('draft_script_content', '').strip() or current_script.get('draft_script_content', '') or ''
        draft_css = scripts_data.get('draft_css_content', '').strip() or current_script.get('draft_css_content', '') or ''

        if '/*#FILE' not in draft_script and '/*#FILE' not in draft_css:
            legacy_files = [{
                'id': 'legacy',
                'name': 'main',
                'active': True,
                'order': 1,
                'javascript': draft_script,
                'css': draft_css,
            }]
            draft_script = build_language_source(legacy_files, 'javascript')
            draft_css = build_language_source(legacy_files, 'css')

        files = merge_language_sources(draft_script, draft_css)

        if not draft_script.strip() and not draft_css.strip():
            return await self._handle_script_deletion(user_id, site_code)

        active_js, active_css = build_active_output(files) if files else ('', '')

        script_record = await self.db_helper.update_site_script_separated(
            user_id,
            site_code,
            active_css,
            active_js,
            draft_css,
            draft_script,
        )
        if not script_record:
            raise BusinessException("스크립트 데이터베이스 저장 실패", "DB_SAVE_FAILED", 500)

        return {
            "site_code": site_code,
            "message": "스크립트가 배포되었습니다.",
            "script_content": script_record.get('script_content', active_js),
            "css_content": script_record.get('css_content', active_css),
            "draft_script_content": script_record.get('draft_script_content', draft_script),
            "draft_css_content": script_record.get('draft_css_content', draft_css),
            "draft_updated_at": script_record.get('draft_updated_at'),
            "version": script_record.get('version'),
            "updated_at": script_record.get('updated_at'),
        }

    async def save_site_script_draft(self, user_id: str, site_code: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        """특정 사이트의 스크립트를 임시 저장합니다."""
        return await self.handle_operation(
            "사이트 스크립트 임시 저장",
            self._save_site_script_draft_internal,
            user_id, site_code, scripts_data
        )

    async def _save_site_script_draft_internal(self, user_id: str, site_code: str, scripts_data: Dict[str, str]) -> Dict[str, Any]:
        self.validate_required_fields(
            {"user_id": user_id, "site_code": site_code},
            ["user_id", "site_code"]
        )

        site = await self.db_helper.get_user_site_by_code(user_id, site_code)
        if not site:
            raise BusinessException("사이트를 찾을 수 없거나 접근 권한이 없습니다", "SITE_NOT_FOUND", 404)

        current_script = await self.db_helper.get_site_script(user_id, site_code)

        draft_script = scripts_data.get('draft_script_content', '').strip()
        draft_css = scripts_data.get('draft_css_content', '').strip()

        if '/*#FILE' not in draft_script and '/*#FILE' not in draft_css:
            legacy_files = [{
                'id': 'legacy',
                'name': 'main',
                'active': True,
                'order': 1,
                'javascript': draft_script,
                'css': draft_css,
            }]
            draft_script = build_language_source(legacy_files, 'javascript')
            draft_css = build_language_source(legacy_files, 'css')

        files = merge_language_sources(draft_script, draft_css)
        draft_active_js, draft_active_css = build_active_output(files) if files else ('', '')

        if draft_active_css and len(draft_active_css.encode('utf-8')) > 50 * 1024:
            raise ValidationException("CSS 크기가 50KB를 초과합니다.")

        if draft_active_js:
            validation_result = self.validate_script_content(draft_active_js)
            if not validation_result.is_valid:
                error_messages = [err.message for err in validation_result.errors]
                raise ValidationException(f"JavaScript 검증 실패: {'; '.join(error_messages)}")

        script_record = await self.db_helper.update_site_script_draft(
            user_id,
            site_code,
            draft_css,
            draft_script,
        )
        if not script_record:
            raise BusinessException("스크립트 초안 저장에 실패했습니다.", "DB_SAVE_FAILED", 500)

        await self.log_user_action(user_id, "script_draft_saved", {
            "site_code": site_code,
            "draft_updated_at": script_record.get('draft_updated_at')
        })

        return {
            "site_code": site_code,
            "message": "스크립트 초안이 저장되었습니다.",
            "draft_script_content": script_record.get('draft_script_content', draft_script),
            "draft_css_content": script_record.get('draft_css_content', draft_css),
            "draft_updated_at": script_record.get('draft_updated_at'),
            "script_content": script_record.get('script_content', current_script.get('script_content') if current_script else ''),
            "css_content": script_record.get('css_content', current_script.get('css_content') if current_script else ''),
            "version": script_record.get('version', current_script.get('version') if current_script else 0),
            "updated_at": script_record.get('updated_at', current_script.get('updated_at') if current_script else None),
        }
    
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
