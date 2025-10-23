"""
AI 응답을 위한 구조화된 출력 스키마 정의
Google Gemini의 구조화된 출력을 활용하여 스크립트 관련 응답을 정확하게 파싱합니다.
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, List, Literal, Any
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

class CodeDiff(BaseModel):
    """코드 변경에 대한 diff 페이로드"""
    file_id: str = Field(..., description="변경 대상 파일 ID")
    diff: str = Field(..., description="코드 변경 diff 또는 전체 코드")

class ChangesPayload(BaseModel):
    """지원하는 코드 타입별 변경 집합"""
    javascript: Optional[CodeDiff] = Field(None, description="JavaScript 코드 변경")
    css: Optional[CodeDiff] = Field(None, description="CSS 코드 변경")

class AIChangeResponse(BaseModel):
    """현재 채팅 응답에 사용하는 구조화된 출력 스키마"""
    message: str = Field(..., description="사용자에게 보여줄 응답 메시지")
    changes: Optional[ChangesPayload] = Field(
        default=None,
        description="선택적 코드 변경 사항 (javascript/css)"
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
    image_data: Optional[List[str]] = Field(default=None, description="이미지 데이터 배열 (Base64 형식)")
    created_at: Optional[datetime] = Field(default=None, description="생성 시간")

class ChatMessageCreate(BaseModel):
    """새 메시지 생성 요청"""
    message: str = Field(..., description="메시지 내용", min_length=1, max_length=2000)
    message_type: MessageType = Field(default="user", description="메시지 타입")
    status: MessageStatus = Field(default="pending", description="초기 메시지 상태")
    metadata: Optional[Dict] = Field(default={}, description="메타데이터")
    image_data: Optional[List[str]] = Field(default=None, description="이미지 데이터 배열 (Base64 형식)")

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

# Membership Types
MembershipLevelType = Literal[0, 1, 2, 3]

class UserMembership(BaseModel):
    """사용자 멤버십 모델"""
    id: str = Field(..., description="멤버십 ID")
    user_id: str = Field(..., description="사용자 ID")
    membership_level: MembershipLevelType = Field(..., description="멤버십 레벨 (0:무료, 1:베이직, 2:프리미엄, 3:최상위)")
    expires_at: Optional[datetime] = Field(None, description="만료일")
    next_billing_at: Optional[datetime] = Field(None, description="다음 결제 예정일")
    cancel_at_period_end: Optional[bool] = Field(False, description="만료 시 자동 해지 예정 여부")
    cancel_requested_at: Optional[datetime] = Field(None, description="해지 요청 일시")
    created_at: Optional[datetime] = Field(default=None, description="생성 시간")
    updated_at: Optional[datetime] = Field(default=None, description="수정 시간")

class MembershipStatus(BaseModel):
    """멤버십 상태 모델"""
    level: MembershipLevelType = Field(..., description="현재 멤버십 레벨")
    expires_at: Optional[datetime] = Field(None, description="만료일")
    next_billing_at: Optional[datetime] = Field(None, description="다음 결제 예정일")
    is_expired: bool = Field(..., description="만료 여부")
    days_remaining: Optional[int] = Field(None, description="남은 일수")
    cancel_at_period_end: Optional[bool] = Field(False, description="만료 시 자동 해지 예정 여부")
    cancel_requested_at: Optional[datetime] = Field(None, description="해지 요청 일시")

class MembershipUpgradeRequest(BaseModel):
    """멤버십 업그레이드 요청"""
    target_level: MembershipLevelType = Field(..., description="목표 멤버십 레벨")
    duration_days: int = Field(default=30, description="구독 기간 (일)", ge=1, le=365)

class MembershipExtendRequest(BaseModel):
    """멤버십 연장 요청"""
    extend_days: int = Field(..., description="연장할 일수", ge=1, le=365)

class MembershipResponse(BaseModel):
    """멤버십 응답 모델"""
    status: str = Field(..., description="응답 상태 (success/error)")
    data: Optional[UserMembership] = Field(None, description="멤버십 데이터")
    message: Optional[str] = Field(None, description="응답 메시지")
    error_code: Optional[str] = Field(None, description="오류 코드")

class MembershipStatusResponse(BaseModel):
    """멤버십 상태 응답 모델"""
    status: str = Field(..., description="응답 상태 (success/error)")
    data: Optional[MembershipStatus] = Field(None, description="멤버십 상태 데이터")
    message: Optional[str] = Field(None, description="응답 메시지")
    error_code: Optional[str] = Field(None, description="오류 코드")

class BatchCleanupResult(BaseModel):
    """배치 정리 결과 모델"""
    status: str = Field(..., description="응답 상태 (success/error)")
    data: Optional[Any] = Field(None, description="정리 결과 데이터")
    message: Optional[str] = Field(None, description="응답 메시지")
    error_code: Optional[str] = Field(None, description="오류 코드")
