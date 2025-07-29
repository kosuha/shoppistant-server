"""
멤버십별 설정 및 제한사항 관리
"""
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import IntEnum

class MembershipLevel(IntEnum):
    """멤버십 레벨"""
    FREE = 0
    BASIC = 1
    PREMIUM = 2
    MAX = 3

@dataclass
class MembershipFeatures:
    """멤버십별 기능 설정"""
    # AI 모델 설정
    ai_model: str
    thinking_budget: int  # -1은 무제한
    
    # 사용량 제한
    daily_requests: int  # 일일 요청 제한 (-1은 무제한)
    max_sites: int  # 연결 가능한 사이트 수 (-1은 무제한)
    is_image_uploads: bool  # 이미지 업로드 가능 여부

class MembershipConfig:
    """멤버십 설정 관리자"""
    
    # 멤버십별 설정 정의
    MEMBERSHIP_CONFIGS = {
        MembershipLevel.FREE: MembershipFeatures(
            ai_model="gemini-2.5-flash-lite",
            thinking_budget=-1,  # 사고 토큰
            daily_requests=10,
            max_sites=1,
            is_image_uploads=False  # 이미지 업로드 불가,
        ),
        MembershipLevel.BASIC: MembershipFeatures(
            ai_model="gemini-2.5-flash",
            thinking_budget=-1,
            daily_requests=20,
            max_sites=4,
            is_image_uploads=True,
        ),
        MembershipLevel.PREMIUM: MembershipFeatures(
            ai_model="gemini-2.5-flash",
            thinking_budget=-1,  # 무제한
            daily_requests=100,
            max_sites=10,
            is_image_uploads=True,
        ),
        MembershipLevel.MAX: MembershipFeatures(
            ai_model="gemini-2.5-pro",
            thinking_budget=-1,  # 무제한
            daily_requests=-1,  # 무제한
            max_sites=20,  # 무제한
            is_image_uploads=True,  # 이미지 업로드 가능
        )
    }
    
    @classmethod
    def get_features(cls, membership_level: int) -> MembershipFeatures:
        """멤버십 레벨에 따른 기능 설정 반환"""
        level = MembershipLevel(membership_level)
        return cls.MEMBERSHIP_CONFIGS.get(level, cls.MEMBERSHIP_CONFIGS[MembershipLevel.FREE])
    
    @classmethod
    def get_ai_model(cls, membership_level: int) -> str:
        """멤버십 레벨에 따른 AI 모델 반환"""
        features = cls.get_features(membership_level)
        return features.ai_model
    
    @classmethod
    def get_thinking_budget(cls, membership_level: int) -> int:
        """멤버십 레벨에 따른 사고 토큰 예산 반환"""
        features = cls.get_features(membership_level)
        return features.thinking_budget
    
    @classmethod
    def can_use_feature(cls, membership_level: int, feature: str) -> bool:
        """특정 기능 사용 가능 여부 확인"""
        features = cls.get_features(membership_level)
        return getattr(features, feature, False)
    
    @classmethod
    def get_limit(cls, membership_level: int, limit_type: str) -> int:
        """멤버십 레벨에 따른 제한값 반환"""
        features = cls.get_features(membership_level)
        return getattr(features, limit_type, 0)
    
    @classmethod
    def get_membership_info(cls, membership_level: int) -> Dict[str, Any]:
        """멤버십 정보 전체 반환"""
        features = cls.get_features(membership_level)
        level_name = MembershipLevel(membership_level).name
        
        return {
            "level": membership_level,
            "level_name": level_name,
            "ai_model": features.ai_model,
            "thinking_budget": features.thinking_budget,
            "daily_requests": features.daily_requests,
            "max_sites": features.max_sites,
            "is_image_uploads": features.is_image_uploads
        }
    
    @classmethod
    def is_upgrade_available(cls, current_level: int) -> bool:
        """업그레이드 가능 여부 확인"""
        return current_level < max(cls.MEMBERSHIP_CONFIGS.keys())