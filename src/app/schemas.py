"""
AI 응답을 위한 구조화된 출력 스키마 정의
Google Gemini의 구조화된 출력을 활용하여 스크립트 관련 응답을 정확하게 파싱합니다.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from enum import Enum

class ScriptPosition(str, Enum):
    """스크립트 위치를 나타내는 열거형"""
    HEADER = "header"
    BODY = "body"
    FOOTER = "footer"

class ScriptContent(BaseModel):
    """개별 스크립트 내용을 나타내는 모델"""
    content: Optional[str] = Field(
        None, 
        description="스크립트 내용. <script> 태그로 감싸인 전체 스크립트"
    )
    description: Optional[str] = Field(
        None,
        description="스크립트에 대한 설명"
    )

class ScriptUpdate(BaseModel):
    """AI가 스크립트 수정 시 반환하는 구조화된 응답"""
    header: Optional[ScriptContent] = Field(
        None,
        description="헤더 스크립트 업데이트 내용"
    )
    body: Optional[ScriptContent] = Field(
        None,
        description="바디 스크립트 업데이트 내용"
    )
    footer: Optional[ScriptContent] = Field(
        None,
        description="푸터 스크립트 업데이트 내용"
    )

class CurrentScripts(BaseModel):
    """현재 사이트의 스크립트 상태를 나타내는 모델"""
    header: Optional[str] = Field(None, description="현재 헤더 스크립트")
    body: Optional[str] = Field(None, description="현재 바디 스크립트")
    footer: Optional[str] = Field(None, description="현재 푸터 스크립트")

class ScriptDeployRequest(BaseModel):
    """스크립트 배포 요청을 위한 모델"""
    header: Optional[str] = Field(None, description="헤더 스크립트 내용")
    body: Optional[str] = Field(None, description="바디 스크립트 내용")
    footer: Optional[str] = Field(None, description="푸터 스크립트 내용")

class ScriptDeployResponse(BaseModel):
    """스크립트 배포 응답을 위한 모델"""
    deployed_at: str = Field(..., description="배포 완료 시간 (ISO 8601 형식)")
    site_code: str = Field(..., description="배포된 사이트 ID")
    deployed_scripts: Dict[str, Optional[str]] = Field(
        ..., 
        description="실제로 배포된 스크립트들"
    )

class ScriptListResponse(BaseModel):
    """스크립트 조회 응답을 위한 모델"""
    header: Optional[str] = Field(None, description="헤더 스크립트")
    body: Optional[str] = Field(None, description="바디 스크립트")  
    footer: Optional[str] = Field(None, description="푸터 스크립트")

class AIScriptResponse(BaseModel):
    """AI의 스크립트 관련 응답을 위한 통합 모델"""
    message: str = Field(
        ...,
        description="사용자에게 보여줄 응답 메시지"
    )
    script_updates: Optional[ScriptUpdate] = Field(
        None,
        description="스크립트 수정이 필요한 경우의 업데이트 정보"
    )

class ScriptValidationError(BaseModel):
    """스크립트 검증 오류를 나타내는 모델"""
    field: str = Field(..., description="오류가 발생한 필드")
    error_type: str = Field(..., description="오류 타입")
    message: str = Field(..., description="오류 메시지")

class ScriptValidationResult(BaseModel):
    """스크립트 검증 결과를 나타내는 모델"""
    is_valid: bool = Field(..., description="검증 통과 여부")
    errors: List[ScriptValidationError] = Field(
        default_factory=list,
        description="검증 오류 목록"
    )
    warnings: List[str] = Field(
        default_factory=list,
        description="경고 메시지 목록"
    )