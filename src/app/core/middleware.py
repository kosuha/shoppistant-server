"""
전역 예외 처리 미들웨어
"""
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exception_handlers import http_exception_handler
import logging

from core.responses import error_response, BusinessException

logger = logging.getLogger(__name__)

async def business_exception_handler(request: Request, exc: BusinessException):
    """비즈니스 예외 처리기"""
    logger.warning(f"Business exception: {exc.message}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.message,
            error_code=exc.error_code
        ).model_dump()
    )

async def http_exception_handler_custom(request: Request, exc: HTTPException):
    """HTTP 예외 처리기"""
    logger.warning(f"HTTP exception: {exc.detail}")
    
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            message=exc.detail,
            error_code="HTTP_ERROR"
        ).model_dump()
    )

async def general_exception_handler(request: Request, exc: Exception):
    """일반 예외 처리기"""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content=error_response(
            message="내부 서버 오류가 발생했습니다",
            error_code="INTERNAL_SERVER_ERROR"
        ).model_dump()
    )

def setup_exception_handlers(app):
    """예외 처리기 설정"""
    app.add_exception_handler(BusinessException, business_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler_custom)
    app.add_exception_handler(Exception, general_exception_handler)
