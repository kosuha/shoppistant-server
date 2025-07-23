"""
애플리케이션 설정 관리
"""
import os
from typing import Optional
from pydantic import BaseModel, validator
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 서버 설정
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    DEBUG: bool = False
    SERVER_BASE_URL: str = "http://localhost:8000"
    
    # MCP 서버 설정
    MCP_SERVER_URL: str = "http://localhost:8001"
    
    # Supabase 설정
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: Optional[str] = None
    
    # Imweb API 설정
    IMWEB_CLIENT_ID: str
    IMWEB_CLIENT_SECRET: str
    IMWEB_REDIRECT_URI: str
    
    # AI 설정
    GEMINI_API_KEY: str
    
    # 보안 설정
    SECRET_KEY: str = "your-secret-key"
    
    # 로깅 설정
    LOG_LEVEL: str = "INFO"
    
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
        env_file = ".env"
        case_sensitive = True
        extra = "allow"  # 추가 환경변수 허용

# 전역 설정 인스턴스
settings = Settings()
