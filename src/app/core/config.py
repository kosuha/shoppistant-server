"""
애플리케이션 설정 관리
"""
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import validator
from pydantic_settings import BaseSettings


_FILE_PATH = Path(__file__).resolve()


def _collect_env_files(file_path: Path) -> tuple[Path, ...]:
    """환경 파일 후보를 가까운 디렉터리부터 수집"""

    collected: list[Path] = []
    seen: set[Path] = set()

    for directory in file_path.parents:
        for name in (".env", ".env.local"):
            candidate = directory / name
            if candidate.exists() and candidate not in seen:
                collected.append(candidate)
                seen.add(candidate)

    return tuple(collected)


_ENV_FILES = _collect_env_files(_FILE_PATH)


def _load_dotenv_files() -> None:
    """프로젝트 전체에서 활용할 .env 파일들을 순차적으로 로드"""

    for dotenv_path in _ENV_FILES:
        load_dotenv(dotenv_path, override=False)


_load_dotenv_files()

class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 서버 설정
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    SERVER_BASE_URL: str = "http://localhost:8000"
    
    # Supabase 설정
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    
    # Imweb API 설정
    WEB_BASE_URL: str
    
    # AI 설정
    GEMINI_API_KEY: str
    # 선택적: 다양한 LLM 공급자 지원을 위한 키들 (있으면 사용)
    OPENAI_API_KEY: Optional[str] = None
    CLAUDE_API_KEY: Optional[str] = None
    # Claude 출력 토큰 상한 (기본 8192)
    CLAUDE_MAX_TOKENS: int = 8192
    
    # 보안 설정
    SECRET_KEY: str = "your-secret-key"
    
    # 로깅 설정
    LOG_LEVEL: str = "INFO"
    # 상세 요청/응답 로깅 플래그 (대용량 마스킹 포함)
    DEBUG_HTTP_LOGS: bool = False
    # 로그 최대 길이(문자). 0 또는 음수면 무제한(잘라내지 않음)
    DEBUG_HTTP_LOGS_MAXLEN: int = 0

    # Paddle Billing 설정
    PADDLE_API_KEY: Optional[str] = None
    PADDLE_API_BASE_URL: str = "https://api.paddle.com"
    PADDLE_PRODUCT_ID_MEMBERSHIP: Optional[str] = None
    PADDLE_PRODUCT_ID_CREDITS: Optional[str] = None
    PADDLE_PRICE_ID_MEMBERSHIP: Optional[str] = None
    PADDLE_PRICE_ID_CREDITS: Optional[str] = None
    
    @validator('SUPABASE_URL')
    def validate_supabase_url(cls, v):
        if not v:
            raise ValueError('SUPABASE_URL은 필수입니다')
        return v
    
    @validator('SUPABASE_ANON_KEY')
    def validate_supabase_anon_key(cls, v):
        if not v:
            raise ValueError('SUPABASE_ANON_KEY는 필수입니다')
        return v
    
    @validator('GEMINI_API_KEY')
    def validate_gemini_api_key(cls, v):
        if not v:
            raise ValueError('GEMINI_API_KEY는 필수입니다')
        return v
    
    class Config:
        env_file = tuple(str(path) for path in _ENV_FILES) if _ENV_FILES else None
        case_sensitive = True
        extra = "allow"  # 추가 환경변수 허용

# 전역 설정 인스턴스
settings = Settings()
