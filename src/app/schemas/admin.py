from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class MembershipGrantRequest(BaseModel):
    target_level: int = Field(..., ge=0, description="적용할 멤버십 레벨")
    duration_days: int = Field(30, ge=1, description="연장할 기간(일)")


class MembershipExtendRequest(BaseModel):
    duration_days: int = Field(..., ge=1, description="추가 연장 기간(일)")


class CreditAdjustRequest(BaseModel):
    amount: float = Field(..., gt=0, description="조정할 금액(USD)")
    reason: Optional[str] = Field(None, description="조정 사유")


class RefundRequest(BaseModel):
    transaction_id: str = Field(..., description="환불 처리할 거래 ID")
    reason: Optional[str] = Field(None, description="환불 사유")


class EventReplayRequest(BaseModel):
    reason: Optional[str] = Field(None, description="재처리 사유")
