"""
서비스 기본 클래스
"""
import logging
from typing import Dict, Any, Optional
from core.responses import success_response, error_response, BusinessException
from core.interfaces import IDatabaseHelper

logger = logging.getLogger(__name__)

class BaseService:
    """모든 서비스의 기본 클래스"""
    
    def __init__(self, db_helper: IDatabaseHelper):
        self.db_helper = db_helper
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def handle_operation(self, operation_name: str, operation_func, *args, **kwargs) -> Dict[str, Any]:
        """공통 작업 처리 래퍼"""
        try:
            result = await operation_func(*args, **kwargs)
            return {"success": True, "data": result}
        except BusinessException as e:
            self.logger.warning(f"{operation_name} 비즈니스 오류: {e.message}")
            return {
                "success": False,
                "error": e.message,
                "error_code": e.error_code,
                "status_code": e.status_code
            }
        except Exception as e:
            self.logger.error(f"{operation_name} 실패: {e}")
            return {
                "success": False,
                "error": str(e),
                "status_code": 500
            }
    
    async def log_user_action(self, user_id: str, action: str, data: Dict[str, Any] = None):
        """사용자 액션 로깅"""
        try:
            await self.db_helper.log_system_event(
                event_type=f"user_{action}",
                event_data=data or {},
                user_id=user_id
            )
        except Exception as e:
            self.logger.warning(f"액션 로깅 실패: {e}")
    
    def validate_required_fields(self, data: Dict[str, Any], required_fields: list):
        """필수 필드 검증"""
        missing_fields = [field for field in required_fields if not data.get(field)]
        if missing_fields:
            raise BusinessException(
                f"필수 필드가 누락되었습니다: {', '.join(missing_fields)}",
                "MISSING_REQUIRED_FIELDS",
                400
            )
