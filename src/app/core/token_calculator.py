"""
멀티 프로바이더 토큰 사용량 및 비용 계산기
 - Gemini(기존)
 - OpenAI (gpt-4o, gpt-4o-mini)
 - Anthropic (claude-3-5-sonnet)
"""
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)
from core.model_catalog import get_supported_models as catalog_supported_models, get_pricing_table

class TokenUsageCalculator:
    """토큰 사용량 및 비용 계산기 (멀티 프로바이더)"""
    
    # Gemini 모델별 가격 정보 (per million tokens)
    # 단일 카탈로그에서 가격 테이블을 추출하여 사용
    MODEL_PRICING = get_pricing_table()
    
    
    # USD to KRW 환율 (대략적인 값)
    USD_TO_KRW_RATE = 1350
    
    @classmethod
    def calculate_cost(cls, usage_metadata, model_name: str = "gemini-2.5-pro", 
                      input_type: str = "text_image_video") -> Dict[str, Any]:
        """
    Gemini 전용 usage_metadata 객체를 기반으로 비용을 계산합니다.
        
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
    def calculate_cost_from_counts(
        cls,
        input_tokens: int,
        output_tokens: int,
        model_name: str,
        input_type: str = "text_image_video",
    ) -> Dict[str, Any]:
        """
        프로바이더에 상관없이 토큰 카운트(입력/출력)를 기반으로 비용 계산.
        LangChain usage_metadata(input/output/total tokens)에 대응.
        """
        pricing = cls.MODEL_PRICING.get(model_name)
        if pricing is None:
            # 카탈로그에는 있으나 가격표가 없는 경우와 완전히 알 수 없는 모델을 구분
            supported = model_name in catalog_supported_models()
            note = 'pricing_not_available' if supported else 'model_unknown'
            return {
                'model_name': model_name,
                'total_tokens': (input_tokens or 0) + (output_tokens or 0),
                'input_tokens': input_tokens or 0,
                'output_tokens': output_tokens or 0,
                'thoughts_tokens': 0,
                'input_cost_usd': 0.0,
                'output_cost_usd': 0.0,
                'total_cost_usd': 0.0,
                'total_cost_krw': 0.0,
                'input_type': input_type,
                'note': note,
            }

        # pricing=None 인 경우는 아직 미지원 모델(가격 미정)
        if pricing is None:
            return {
                'model_name': model_name,
                'total_tokens': (input_tokens or 0) + (output_tokens or 0),
                'input_tokens': input_tokens or 0,
                'output_tokens': output_tokens or 0,
                'thoughts_tokens': 0,
                'input_cost_usd': 0.0,
                'output_cost_usd': 0.0,
                'total_cost_usd': 0.0,
                'total_cost_krw': 0.0,
                'input_type': input_type,
                'note': 'pricing_not_available',
            }

        # 입력 비용
        # 우선: 입력 타입이 명시적 키로 제공되면 그대로 사용 (예: cache_write_5m / cache_hit 등)
        if input_type in pricing['input']:
            in_price = pricing['input'][input_type]
        elif input_type == 'cached' and 'cached' in pricing['input']:
            in_price = pricing['input']['cached']
        elif 'all' in pricing['input']:
            in_price = pricing['input']['all']
        elif model_name.startswith('gemini-2.5'):
            # Gemini 규칙 재사용
            in_price = pricing['input'].get('audio' if input_type == 'audio' else 'text_image_video', 0)
        else:
            in_price = 0

        # 출력 비용
        if 'all' in pricing['output']:
            out_price = pricing['output']['all']
        elif model_name == 'gemini-2.5-pro':
            # 컨텍스트 크기에 따른 차등 (입력 기준)
            context_threshold = 200000
            is_large_context = (input_tokens or 0) > context_threshold
            out_price = pricing['output']['large_context' if is_large_context else 'small_context']
        else:
            out_price = 0

        input_cost_usd = ((input_tokens or 0) * in_price) / 1_000_000
        output_cost_usd = ((output_tokens or 0) * out_price) / 1_000_000
        total_cost_usd = input_cost_usd + output_cost_usd
        total_cost_krw = total_cost_usd * cls.USD_TO_KRW_RATE

        return {
            'model_name': model_name,
            'total_tokens': (input_tokens or 0) + (output_tokens or 0),
            'input_tokens': input_tokens or 0,
            'output_tokens': output_tokens or 0,
            'thoughts_tokens': 0,
            'input_cost_usd': round(input_cost_usd, 6),
            'output_cost_usd': round(output_cost_usd, 6),
            'total_cost_usd': round(total_cost_usd, 6),
            'total_cost_krw': round(total_cost_krw, 2),
            'input_type': input_type,
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
            # 공통 규칙: 'cached' 가 있으면 우선, 다음으로 'all', 없으면 text/audio 분기
            if input_type == 'cached' and 'cached' in pricing['input']:
                price = pricing['input']['cached']
            elif 'all' in pricing['input']:
                price = pricing['input']['all']
            else:
                # Flash, Flash-Lite 모델은 입력 타입에 따른 요금
                if input_type == 'audio':
                    price = pricing['input'].get('audio', pricing['input'].get('text_image_video', 0))
                else:
                    price = pricing['input'].get('text_image_video', 0)
        
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
        """지원되는 모델 목록 반환 (단일 소스 참조)"""
        # 단일 카탈로그에서 계산된 결과 사용
        return catalog_supported_models()
    
    @classmethod
    def compare_model_costs(cls, input_tokens: int, output_tokens: int, 
                          input_type: str = "text_image_video") -> Dict[str, Dict]:
        """여러 모델의 비용 비교"""
        results = {}
        
        for model_name in cls.get_supported_models():
            cost_info = cls.estimate_cost(input_tokens, output_tokens, model_name, input_type)
            results[model_name] = cost_info
        
        return results