"""
AI 응답을 위한 구조화된 출력 스키마 정의
Google Gemini의 구조화된 출력을 활용하여 스크립트 관련 응답을 정확하게 파싱합니다.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Literal
from datetime import datetime
import uuid

class ScriptContent(BaseModel):
    """개별 스크립트 내용을 나타내는 모델"""
    content: Optional[str] = Field(
        None, 
        description="스크립트 내용. 전체 스크립트"
    )
    description: Optional[str] = Field(
        None,
        description="스크립트에 대한 설명"
    )

class ScriptUpdate(BaseModel):
    """AI가 스크립트 수정 시 반환하는 구조화된 응답"""
    script: Optional[ScriptContent] = Field(
        None,
        description="스크립트 업데이트 내용"
    )

class CurrentScripts(BaseModel):
    """현재 사이트의 스크립트 상태를 나타내는 모델"""
    script: Optional[str] = Field(None, description="현재 스크립트")

class ScriptDeployRequest(BaseModel):
    """스크립트 배포 요청을 위한 모델"""
    script: Optional[str] = Field(None, description="스크립트 내용")

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
    script: Optional[str] = Field(None, description="스크립트 내용")

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

class SiteScriptRecord(BaseModel):
    """데이터베이스의 site_scripts 테이블 레코드를 나타내는 모델"""
    id: str = Field(..., description="스크립트 고유 ID")
    site_code: str = Field(..., description="사이트 코드")
    user_id: str = Field(..., description="스크립트 소유자 ID")
    script_content: str = Field(..., description="스크립트 내용")
    version: int = Field(..., description="스크립트 버전")
    is_active: bool = Field(..., description="활성 스크립트 여부")
    created_at: str = Field(..., description="생성 시간 (ISO 8601 형식)")
    updated_at: str = Field(..., description="수정 시간 (ISO 8601 형식)")

class ScriptHistoryResponse(BaseModel):
    """스크립트 버전 히스토리 응답을 위한 모델"""
    scripts: List[SiteScriptRecord] = Field(
        default_factory=list,
        description="스크립트 버전 목록 (최신순)"
    )
    total_count: int = Field(..., description="전체 스크립트 버전 개수")

class ScriptModuleResponse(BaseModel):
    """스크립트 모듈 배포 응답을 위한 확장 모델"""
    deployed_at: str = Field(..., description="배포 완료 시간 (ISO 8601 형식)")
    site_code: str = Field(..., description="배포된 사이트 ID")
    script_version: Optional[int] = Field(None, description="배포된 스크립트 버전")
    module_url: str = Field(..., description="모듈 스크립트 URL")
    deployed_scripts: Dict[str, Optional[str]] = Field(
        ..., 
        description="실제로 배포된 스크립트들"
    )

# Message Status Types
MessageStatus = Literal["pending", "in_progress", "completed", "error"]
MessageType = Literal["user", "assistant", "system"]

class ChatMessage(BaseModel):
    """채팅 메시지 모델"""
    id: str = Field(..., description="메시지 고유 ID")
    thread_id: str = Field(..., description="스레드 ID")
    user_id: str = Field(..., description="사용자 ID")
    message: str = Field(..., description="메시지 내용")
    message_type: MessageType = Field(..., description="메시지 타입")
    status: MessageStatus = Field(default="completed", description="메시지 처리 상태")
    metadata: Optional[Dict] = Field(default={}, description="메타데이터")
    created_at: Optional[datetime] = Field(default=None, description="생성 시간")

class ChatMessageCreate(BaseModel):
    """새 메시지 생성 요청"""
    message: str = Field(..., description="메시지 내용", min_length=1, max_length=2000)
    message_type: MessageType = Field(default="user", description="메시지 타입")
    status: MessageStatus = Field(default="pending", description="초기 메시지 상태")
    metadata: Optional[Dict] = Field(default={}, description="메타데이터")

class ChatMessageUpdate(BaseModel):
    """메시지 상태 업데이트 요청"""
    status: MessageStatus = Field(..., description="변경할 메시지 상태")
    message: Optional[str] = Field(None, description="메시지 내용 (선택적)")
    metadata: Optional[Dict] = Field(None, description="메타데이터 (선택적)")

class ChatMessageResponse(BaseModel):
    """메시지 응답"""
    success: bool = Field(..., description="성공 여부")
    data: Optional[ChatMessage] = Field(None, description="메시지 데이터")
    message: Optional[str] = Field(None, description="응답 메시지")
    error: Optional[str] = Field(None, description="오류 메시지")

class ChatThread(BaseModel):
    """채팅 스레드 모델"""
    id: str = Field(..., description="스레드 ID")
    user_id: str = Field(..., description="사용자 ID")
    site_code: Optional[str] = Field(None, description="사이트 코드")
    title: Optional[str] = Field(None, description="스레드 제목")
    created_at: Optional[datetime] = Field(default=None, description="생성 시간")
    updated_at: Optional[datetime] = Field(default=None, description="수정 시간")
    last_message_at: Optional[datetime] = Field(default=None, description="마지막 메시지 시간")