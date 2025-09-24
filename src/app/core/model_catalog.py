"""
모델 정보 단일 소스 (Single Source of Truth)
MODEL_CATALOG: 각 모델 키에 대해 provider, provider_model, pricing을 함께 보유합니다.
헬퍼 함수로 목록/매핑/가격 정보에 접근합니다.
"""
from __future__ import annotations
from typing import Dict, Any, Tuple, List, Optional

MODEL_CATALOG: Dict[str, Dict[str, Any]] = {
    # Google Gemini
    'gemini-2.5-pro': {
        'provider': 'google', 'provider_model': 'gemini-2.5-pro',
        'pricing': {
            'input': {'small_context': 1.25, 'large_context': 2.50},
            'output': {'small_context': 10.00, 'large_context': 15.00}
        }
    },
    'gemini-2.5-flash': {
        'provider': 'google', 'provider_model': 'gemini-2.5-flash',
        'pricing': {
            'input': {'text_image_video': 0.30, 'audio': 1.00},
            'output': {'all': 2.50}
        }
    },
    'gemini-2.5-flash-lite': {
        'provider': 'google', 'provider_model': 'gemini-2.5-flash-lite',
        'pricing': {
            'input': {'text_image_video': 0.10, 'audio': 0.30},
            'output': {'all': 0.40}
        }
    },

    # OpenAI
    'gpt-5': {
        'provider': 'openai', 'provider_model': 'gpt-5',
        'pricing': {'input': {'all': 1.25, 'cached': 0.125}, 'output': {'all': 10.00}}
    },
    'gpt-5-mini': {
        'provider': 'openai', 'provider_model': 'gpt-5-mini',
        'pricing': {'input': {'all': 0.25, 'cached': 0.025}, 'output': {'all': 2.00}}
    },
    'gpt-5-nano': {
        'provider': 'openai', 'provider_model': 'gpt-5-nano',
        'pricing': {'input': {'all': 0.05, 'cached': 0.005}, 'output': {'all': 0.40}}
    },
    'gpt-5-codex': {
        'provider': 'openai', 'provider_model': 'gpt-5-codex',
        'pricing': {'input': {'all': 1.25, 'cached': 0.125}, 'output': {'all': 10.00}}
    },

    # Anthropic
    'claude-sonnet-4': {
        'provider': 'anthropic', 'provider_model': 'claude-sonnet-4-20250514',
        'pricing': {
            'input': {
                'all': 3.00, 'cache_write_5m': 3.75, 'cache_write_1h': 6.00, 'cache_hit': 0.30, 'cached': 0.30
            },
            'output': {'all': 15.00}
        }
    },
    'claude-opus-4.1': {
        'provider': 'anthropic', 'provider_model': 'claude-opus-4-1-20250805',
        'pricing': {
            'input': {
                'all': 15.00, 'cache_write_5m': 18.75, 'cache_write_1h': 30.00, 'cache_hit': 1.50, 'cached': 1.50
            },
            'output': {'all': 75.00}
        }
    },
}

def get_supported_models() -> List[str]:
    return sorted(MODEL_CATALOG.keys())

def get_model_pricing_info(model_name: str) -> Optional[Dict[str, Any]]:
    entry = MODEL_CATALOG.get(model_name)
    return entry.get('pricing') if entry else None

def get_provider_mapping(model_name: str) -> Optional[Tuple[str, str]]:
    entry = MODEL_CATALOG.get(model_name)
    if not entry:
        return None
    provider = entry.get('provider')
    prov_model = entry.get('provider_model')
    if provider and prov_model:
        return provider, prov_model
    return None

def get_pricing_table() -> Dict[str, Dict[str, Any]]:
    """TokenUsageCalculator 호환을 위해 model->pricing 맵만 추출"""
    return {k: v['pricing'] for k, v in MODEL_CATALOG.items() if 'pricing' in v}
