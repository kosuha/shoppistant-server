"""
LangChain 기반 LLM 매니저: 다양한 공급자(OpenAI, Anthropic, Google) 모델을 단일 인터페이스로 제공
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List, Tuple
import logging

from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI

from core.config import settings

logger = logging.getLogger(__name__)

# 프론트/서버가 공통으로 쓸 수 있는 모델 키 매핑
# value: (provider, provider_model_name)
MODEL_REGISTRY: Dict[str, Tuple[str, str]] = {
    # Google Gemini (LangChain 경로)
    "gemini-2.5-pro": ("google", "gemini-2.5-pro"),
    "gemini-2.5-flash": ("google", "gemini-2.5-flash"),
    "gemini-2.5-flash-lite": ("google", "gemini-2.5-flash-lite"),
    "gpt-5": ("openai", "gpt-5"),
    "gpt-5-mini": ("openai", "gpt-5-mini"),
    "gpt-5-nano": ("openai", "gpt-5-nano"),
    "claude-sonnet-4": ("anthropic", "claude-sonnet-4-20250514"),
    "claude-opus-4": ("anthropic", "claude-opus-4-20250514"),
    "claude-opus-4.1": ("anthropic", "claude-opus-4-1-20250805")
}

ALLOWED_PROVIDERS = {"google", "openai", "anthropic"}

class LangChainLLMManager:
    """요청한 모델 키에 따라 적절한 LangChain 챗 모델을 반환"""

    def __init__(self):
        # 환경 변수 유효성 체크는 지연 수행
        pass

    def is_supported(self, model_key: str) -> bool:
        return model_key in MODEL_REGISTRY

    def get_llm(self, model_key: str, temperature: float = 0.6) -> Optional[BaseLanguageModel]:
        entry = MODEL_REGISTRY.get(model_key)
        if not entry:
            return None
        provider, name = entry
        try:
            if provider == "google":
                # GOOGLE_API_KEY 또는 GEMINI_API_KEY 로 지원
                api_key = settings.GEMINI_API_KEY
                if not api_key:
                    logger.warning("GEMINI_API_KEY 누락 - Google 모델 사용 불가")
                    return None
                return ChatGoogleGenerativeAI(model=name, api_key=api_key, temperature=temperature)
            elif provider == "openai":
                if not settings.OPENAI_API_KEY:
                    logger.warning("OPENAI_API_KEY 누락 - OpenAI 모델 사용 불가")
                    return None
                return ChatOpenAI(model=name, api_key=settings.OPENAI_API_KEY, temperature=temperature)
            elif provider == "anthropic":
                if not settings.ANTHROPIC_API_KEY:
                    logger.warning("ANTHROPIC_API_KEY 누락 - Anthropic 모델 사용 불가")
                    return None
                return ChatAnthropic(model=name, api_key=settings.ANTHROPIC_API_KEY, temperature=temperature)
        except Exception as e:
            logger.error(f"LLM 생성 실패 ({model_key}): {e}")
            return None

    def build_chain(self, system_prompt: str) -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", "{input}")
        ])

    async def generate_with_meta(self, model_key: str, system_prompt: str, user_input: str,
                                 temperature: float = 0.6,
                                 images: Optional[List[str]] = None) -> Tuple[Optional[str], Dict[str, Any]]:
        """
        멀티모달 입력 지원 생성 함수.
        images: data URI(예: data:image/png;base64,...) 또는 일반 URL 문자열 목록
        """
        llm = self.get_llm(model_key, temperature=temperature)
        if not llm:
            return None, {}

        try:
            # 이미지가 없으면 기존 프롬프트 체인 사용
            if not images:
                prompt = self.build_chain(system_prompt)
                chain = prompt | llm
                result = await chain.ainvoke({"input": user_input})
            else:
                # 멀티모달 메시지 구성: 공통 포맷 사용 (text + image_url)
                human_content: List[Dict[str, Any]] = [{"type": "text", "text": user_input}]
                provider, _ = MODEL_REGISTRY.get(model_key, (None, None))
                for img in images:
                    if not (isinstance(img, str) and img.strip()):
                        continue
                    url = img.strip()
                    if provider == "openai":
                        # OpenAI: image_url는 객체 형식 사용
                        human_content.append({
                            "type": "image_url",
                            "image_url": {"url": url}
                        })
                    elif provider == "google":
                        # Google: 문자열로 허용됨 (data URL 포함)
                        human_content.append({
                            "type": "image_url",
                            "image_url": url
                        })
                    elif provider == "anthropic":
                        # Anthropic: data URL -> base64 / mime 로 변환, 아니면 url 소스로 전달
                        if url.startswith("data:image/") and "," in url:
                            try:
                                header, b64 = url.split(",", 1)
                                mime = header.split(":", 1)[1].split(";", 1)[0]
                                human_content.append({
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime,
                                        "data": b64,
                                    }
                                })
                            except Exception:
                                # 실패 시 URL로 처리 시도
                                human_content.append({
                                    "type": "image",
                                    "source": {"type": "url", "url": url}
                                })
                        else:
                            human_content.append({
                                "type": "image",
                                "source": {"type": "url", "url": url}
                            })
                messages = [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=human_content),
                ]
                result = await llm.ainvoke(messages)

            text: Optional[str]
            meta: Dict[str, Any] = {}
            if isinstance(result, AIMessage):
                text = result.content if isinstance(result.content, str) else str(result.content)
                meta = getattr(result, "response_metadata", {}) or {}
            else:
                text = str(result)
            return text, meta
        except Exception as e:
            logger.error(f"LangChain 생성 실패 ({model_key}): {e}")
            return None, {}

    async def generate(self, model_key: str, system_prompt: str, user_input: str,
                        temperature: float = 0.6) -> Optional[str]:
        text, _ = await self.generate_with_meta(model_key, system_prompt, user_input, temperature)
        return text

    def get_supported_models(self) -> List[str]:
        return list(MODEL_REGISTRY.keys())
