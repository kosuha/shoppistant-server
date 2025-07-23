"""
공통 응답 모델 및 예외 클래스
"""
from typing import Generic, TypeVar, Optional, Any, Dict
from pydantic import BaseModel
from fastapi import HTTPException
import logging

logger = logging.getLogger(__name__)

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):
    """표준 API 응답 모델"""
    status: str  # "success" or "error"
    data: Optional[T] = None
    message: Optional[str] = None
    error_code: Optional[str] = None
    
    class Config:
        schema_extra = {
            "example": {
                "status": "success",
                "data": {"key": "value"},
                "message": "작업이 성공적으로 완료되었습니다."
            }
        }

class ErrorDetail(BaseModel):
    """오류 세부 정보"""
    field: Optional[str] = None
    message: str
    code: Optional[str] = None

# 커스텀 예외 클래스들
class BusinessException(Exception):
    """비즈니스 로직 예외"""
    def __init__(self, message: str, error_code: str = None, status_code: int = 400):
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        super().__init__(message)

class AuthenticationException(BusinessException):
    """인증 관련 예외"""
    def __init__(self, message: str = "인증에 실패했습니다"):
        super().__init__(message, "AUTH_FAILED", 401)

class AuthorizationException(BusinessException):
    """권한 관련 예외"""
    def __init__(self, message: str = "접근 권한이 없습니다"):
        super().__init__(message, "ACCESS_DENIED", 403)

class NotFoundException(BusinessException):
    """리소스 찾을 수 없음 예외"""
    def __init__(self, message: str = "요청한 리소스를 찾을 수 없습니다"):
        super().__init__(message, "NOT_FOUND", 404)

class ValidationException(BusinessException):
    """입력 검증 예외"""
    def __init__(self, message: str = "입력 데이터가 유효하지 않습니다", errors: list = None):
        super().__init__(message, "VALIDATION_ERROR", 422)
        self.errors = errors or []

class ExternalServiceException(BusinessException):
    """외부 서비스 호출 예외"""
    def __init__(self, service_name: str, message: str = None):
        msg = message or f"{service_name} 서비스 호출에 실패했습니다"
        super().__init__(msg, "EXTERNAL_SERVICE_ERROR", 502)

# 응답 헬퍼 함수들
def success_response(data: Any = None, message: str = "성공") -> APIResponse:
    """성공 응답 생성"""
    return APIResponse(status="success", data=data, message=message)

def error_response(
    message: str = "오류가 발생했습니다", 
    error_code: str = None, 
    data: Any = None
) -> APIResponse:
    """오류 응답 생성"""
    return APIResponse(
        status="error", 
        message=message, 
        error_code=error_code, 
        data=data
    )

# 로깅 헬퍼
def log_operation(operation: str, user_id: str = None, data: Dict = None):
    """작업 로깅"""
    log_data = {
        "operation": operation,
        "user_id": user_id,
        **(data or {})
    }
    logger.info(f"Operation: {operation}", extra=log_data)
