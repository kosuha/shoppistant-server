"""
Gemini API 토큰 사용량 및 비용 계산기
"""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class TokenUsageCalculator:
    """Gemini API 토큰 사용량 및 비용 계산기"""
    
    # Gemini 모델별 가격 정보 (per million tokens)
    MODEL_PRICING = {
        'gemini-2.5-pro': {
            'input': {
                'small_context': 1.25,   # <= 200K tokens
                'large_context': 2.50    # > 200K tokens
            },
            'output': {
                'small_context': 10.00,  # <= 200K tokens
                'large_context': 15.00   # > 200K tokens
            }
        },
        'gemini-2.5-flash': {
            'input': {
                'text_image_video': 0.30,  # 텍스트/이미지/비디오
                'audio': 1.00              # 오디오
            },
            'output': {
                'all': 2.50               # 모든 출력
            }
        },
        'gemini-2.5-flash-lite': {
            'input': {
                'text_image_video': 0.10,  # 텍스트/이미지/비디오
                'audio': 0.30              # 오디오
            },
            'output': {
                'all': 0.40               # 모든 출력
            }
        }
    }
    
    # USD to KRW 환율 (대략적인 값)
    USD_TO_KRW_RATE = 1350
    
    @classmethod
    def calculate_cost(cls, usage_metadata, model_name: str = "gemini-2.5-pro", 
                      input_type: str = "text_image_video") -> Dict[str, Any]:
        """
        토큰 사용량을 기반으로 비용을 계산합니다.
        
        Args:
            usage_metadata: Gemini API에서 반환된 usage_metadata
            model_name: 사용된 모델명 (gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite)
            input_type: 입력 타입 (text_image_video, audio)
            
        Returns:
            Dict: 토큰 사용량 및 비용 정보
        """
        if not usage_metadata:
            return cls._empty_result()
        
        # 토큰 수 추출
        input_tokens = usage_metadata.prompt_token_count or 0
        output_tokens = usage_metadata.candidates_token_count or 0
        thoughts_tokens = usage_metadata.thoughts_token_count or 0
        total_tokens = usage_metadata.total_token_count or 0
        
        # 모델별 가격 정보 가져오기
        pricing = cls.MODEL_PRICING.get(model_name)
        if not pricing:
            logger.warning(f"알 수 없는 모델: {model_name}. 기본값(gemini-2.5-pro) 사용")
            pricing = cls.MODEL_PRICING['gemini-2.5-pro']
        
        # 입력 토큰 비용 계산
        input_cost_usd = cls._calculate_input_cost(input_tokens, pricing, model_name, input_type)
        
        # 출력 토큰 비용 계산 (thoughts 토큰도 출력 요금으로 청구)
        total_output_tokens = output_tokens + thoughts_tokens
        output_cost_usd = cls._calculate_output_cost(total_output_tokens, pricing, model_name, input_tokens)
        
        # 총 비용 계산
        total_cost_usd = input_cost_usd + output_cost_usd
        total_cost_krw = total_cost_usd * cls.USD_TO_KRW_RATE
        
        return {
            'model_name': model_name,
            'total_tokens': total_tokens,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'thoughts_tokens': thoughts_tokens,
            'input_cost_usd': round(input_cost_usd, 6),
            'output_cost_usd': round(output_cost_usd, 6),
            'total_cost_usd': round(total_cost_usd, 6),
            'total_cost_krw': round(total_cost_krw, 2),
            'input_type': input_type
        }
    
    @classmethod
    def _calculate_input_cost(cls, input_tokens: int, pricing: Dict, model_name: str, input_type: str) -> float:
        """입력 토큰 비용 계산"""
        if input_tokens == 0:
            return 0.0
        
        if model_name == 'gemini-2.5-pro':
            # Pro 모델은 컨텍스트 크기에 따른 차등 요금
            context_threshold = 200000
            is_large_context = input_tokens > context_threshold
            
            if is_large_context:
                price = pricing['input']['large_context']
            else:
                price = pricing['input']['small_context']
        else:
            # Flash, Flash-Lite 모델은 입력 타입에 따른 요금
            if input_type == 'audio':
                price = pricing['input'].get('audio', pricing['input']['text_image_video'])
            else:
                price = pricing['input']['text_image_video']
        
        return (input_tokens * price) / 1_000_000
    
    @classmethod
    def _calculate_output_cost(cls, output_tokens: int, pricing: Dict, model_name: str, input_tokens: int = 0) -> float:
        """출력 토큰 비용 계산"""
        if output_tokens == 0:
            return 0.0
        
        if model_name == 'gemini-2.5-pro':
            # Pro 모델은 컨텍스트 크기에 따른 차등 요금
            context_threshold = 200000
            is_large_context = input_tokens > context_threshold
            
            if is_large_context:
                price = pricing['output']['large_context']
            else:
                price = pricing['output']['small_context']
        else:
            # Flash, Flash-Lite 모델은 단일 출력 요금
            price = pricing['output']['all']
        
        return (output_tokens * price) / 1_000_000
    
    @classmethod
    def _empty_result(cls) -> Dict[str, Any]:
        """빈 결과 반환"""
        return {
            'model_name': 'unknown',
            'total_tokens': 0,
            'input_tokens': 0,
            'output_tokens': 0,
            'thoughts_tokens': 0,
            'input_cost_usd': 0,
            'output_cost_usd': 0,
            'total_cost_usd': 0,
            'total_cost_krw': 0,
            'input_type': 'text_image_video'
        }
    
    @classmethod
    def estimate_cost(cls, input_tokens: int, output_tokens: int, model_name: str = "gemini-2.5-pro", 
                     input_type: str = "text_image_video") -> Dict[str, Any]:
        """
        예상 비용 계산 (API 호출 전 예상치)
        
        Args:
            input_tokens: 예상 입력 토큰 수
            output_tokens: 예상 출력 토큰 수
            model_name: 사용할 모델명
            input_type: 입력 타입
            
        Returns:
            Dict: 예상 비용 정보
        """
        pricing = cls.MODEL_PRICING.get(model_name)
        if not pricing:
            pricing = cls.MODEL_PRICING['gemini-2.5-pro']
        
        input_cost_usd = cls._calculate_input_cost(input_tokens, pricing, model_name, input_type)
        output_cost_usd = cls._calculate_output_cost(output_tokens, pricing, model_name, input_tokens)
        total_cost_usd = input_cost_usd + output_cost_usd
        total_cost_krw = total_cost_usd * cls.USD_TO_KRW_RATE
        
        return {
            'model_name': model_name,
            'estimated_input_tokens': input_tokens,
            'estimated_output_tokens': output_tokens,
            'estimated_input_cost_usd': round(input_cost_usd, 6),
            'estimated_output_cost_usd': round(output_cost_usd, 6),
            'estimated_total_cost_usd': round(total_cost_usd, 6),
            'estimated_total_cost_krw': round(total_cost_krw, 2),
            'input_type': input_type
        }
    
    @classmethod
    def get_model_pricing_info(cls, model_name: str) -> Optional[Dict[str, Any]]:
        """특정 모델의 가격 정보 반환"""
        return cls.MODEL_PRICING.get(model_name)
    
    @classmethod
    def get_supported_models(cls) -> list:
        """지원되는 모델 목록 반환"""
        return list(cls.MODEL_PRICING.keys())
    
    @classmethod
    def compare_model_costs(cls, input_tokens: int, output_tokens: int, 
                          input_type: str = "text_image_video") -> Dict[str, Dict]:
        """여러 모델의 비용 비교"""
        results = {}
        
        for model_name in cls.get_supported_models():
            cost_info = cls.estimate_cost(input_tokens, output_tokens, model_name, input_type)
            results[model_name] = cost_info
        
        return results