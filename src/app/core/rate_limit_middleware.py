"""
일일 요청 제한 미들웨어
멤버십 레벨에 따른 daily_requests 제한 적용
"""
import logging
from typing import Callable, Dict, Any
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse

from core.membership_config import MembershipConfig

logger = logging.getLogger(__name__)

class RateLimitMiddleware:
    def __init__(self):
        self.excluded_paths = {
            '/health',
            '/docs',
            '/openapi.json',
            '/auth/login',
            '/auth/register',
            '/auth/refresh',
            '/membership/config',  # 멤버십 정보는 제한하지 않음
        }
        
        # 메시지 전송 API만 제한 대상으로 설정
        self.rate_limited_paths = {
            '/api/v1/messages',
        }
    
    def should_apply_rate_limit(self, path: str, method: str) -> bool:
        """경로와 메서드가 요청 제한 대상인지 확인"""
        # POST 요청이 아니면 제한하지 않음
        if method != 'POST':
            return False
            
        # 제외 경로 확인
        if path in self.excluded_paths:
            return False
        
        # 특정 패턴 제외 (정적 파일, 헬스체크 등)
        excluded_patterns = ['/static/', '/favicon.ico', '/metrics']
        if any(pattern in path for pattern in excluded_patterns):
            return False
        
        # 메시지 전송 API인지 확인
        return any(pattern in path for pattern in self.rate_limited_paths)
    
    async def __call__(self, request: Request, call_next: Callable) -> Response:
        """미들웨어 실행"""
        try:
            logger.info(f"RateLimitMiddleware 실행: {request.url.path}")
            
            # 요청 제한 대상인지 확인
            if not self.should_apply_rate_limit(request.url.path, request.method):
                logger.info(f"요청 제한 대상이 아님: {request.method} {request.url.path}")
                return await call_next(request)
            
            logger.info(f"요청 제한 대상: {request.url.path}")
            
            # 인증된 사용자 확인
            user_id = await self._get_user_id_from_request(request)
            logger.info(f"추출된 사용자 ID: {user_id}")
            
            if not user_id:
                logger.warning("사용자 ID를 추출할 수 없음 - 인증 미들웨어에서 처리")
                return await call_next(request)
            
            # 데이터베이스 헬퍼 가져오기
            db_helper = await self._get_db_helper(request)
            if not db_helper:
                logger.warning("DB 헬퍼를 가져올 수 없음 - 요청 제한 스킵")
                return await call_next(request)
            
            # 사용자 멤버십 조회
            membership = await db_helper.get_user_membership(user_id)
            membership_level = membership.get('membership_level', 0) if membership else 0
            
            # 멤버십별 일일 요청 제한 가져오기
            features = MembershipConfig.get_features(membership_level)
            daily_limit = features.daily_requests
            
            # 무제한인 경우 스킵
            if daily_limit == -1:
                await db_helper.increment_daily_request(user_id, request.url.path)
                return await call_next(request)
            
            # 현재 요청 수 확인
            limit_info = await db_helper.check_daily_request_limit(user_id, daily_limit)
            
            # 제한 초과 확인
            if limit_info['exceeded']:
                logger.warning(f"일일 요청 제한 초과: user_id={user_id}, count={limit_info['current_count']}, limit={daily_limit}")
                
                return JSONResponse(
                    status_code=429,
                    content={
                        "success": False,
                        "message": f"일일 요청 제한을 초과했습니다. (제한: {daily_limit}회)",
                        "error_code": "DAILY_REQUEST_LIMIT_EXCEEDED",
                        "data": {
                            "current_count": limit_info['current_count'],
                            "limit": daily_limit,
                            "remaining": limit_info['remaining'],
                            "reset_time": limit_info['reset_time'],
                            "membership_level": membership_level
                        }
                    },
                    headers={
                        "X-RateLimit-Limit": str(daily_limit),
                        "X-RateLimit-Remaining": str(limit_info['remaining']),
                        "X-RateLimit-Reset": limit_info['reset_time']
                    }
                )
            
            # 요청 수 증가
            logger.info(f"일일 요청 수 증가: user_id={user_id}, path={request.url.path}")
            increment_result = await db_helper.increment_daily_request(user_id, request.url.path)
            logger.info(f"요청 수 증가 결과: {increment_result}")
            
            # 요청 처리
            response = await call_next(request)
            
            # 응답 헤더에 제한 정보 추가
            response.headers["X-RateLimit-Limit"] = str(daily_limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit_info['remaining'] - 1))
            response.headers["X-RateLimit-Reset"] = limit_info['reset_time']
            
            return response
            
        except Exception as e:
            logger.error(f"요청 제한 미들웨어 오류: {e}")
            # 오류 발생 시 요청을 그대로 진행
            return await call_next(request)
    
    async def _get_user_id_from_request(self, request: Request) -> str:
        """요청에서 사용자 ID 추출"""
        try:
            # Authorization 헤더에서 토큰 추출
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return None
            
            # Supabase를 통한 JWT 토큰 검증
            from core.config import settings
            from supabase import create_client
            
            token = auth_header.replace('Bearer ', '')
            supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_ANON_KEY)
            
            response = supabase.auth.get_user(token)
            return response.user.id if response.user else None
            
        except Exception as e:
            logger.debug(f"사용자 ID 추출 실패: {e}")
            return None
    
    async def _get_db_helper(self, request: Request):
        """요청에서 DB 헬퍼 가져오기"""
        try:
            # FastAPI의 dependency injection을 통해 DB 헬퍼 가져오기
            if hasattr(request.app.state, 'db_helper'):
                return request.app.state.db_helper
            
            # main.py에서 글로벌 변수로 접근
            import main
            if hasattr(main, 'db_helper'):
                return main.db_helper
                
            return None
        except Exception as e:
            logger.error(f"DB 헬퍼 가져오기 실패: {e}")
            return None